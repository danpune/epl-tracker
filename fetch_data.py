#!/usr/bin/env python3
"""
Fetch English Premier League data into one small data.json.

Two sources, split by what each is actually good at:
  openfootball/football.json (CC0) — the whole 380-match season in one file, with
                                     kickoff times. Published months ahead; scores
                                     lag ~2 days, so it is the SCHEDULE source.
  ESPN public feed              — live table + recent results. No key, no limit.
                                  It is the RESULTS source and fills openfootball's lag.

Run by GitHub Actions. No API key. Standard library only.
Fail-safe: never overwrites a good data.json with a failed or empty fetch.
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SEASON = "2026-27"
OF = f"https://raw.githubusercontent.com/openfootball/football.json/master/{SEASON}/en.1.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1"
ESPN2 = "https://site.api.espn.com/apis/v2/sports/soccer/eng.1"
UK = ZoneInfo("Europe/London")   # openfootball times are bare UK local -> DST matters
UA = {"User-Agent": "epl-tracker/1.0 (github.com/danpune/epl-tracker)"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def key(name):
    """Stable id for a club across both feeds. 'Manchester United FC' == 'Manchester United'."""
    s = name.lower().replace("&", "and")
    s = re.sub(r"\b(fc|afc|cf)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


def fetch_season():
    """All 380 fixtures. UK local kickoff -> UTC, so the browser can localise it."""
    out = []
    for m in get(OF).get("matches", []):
        t = m.get("time") or "15:00"
        local = datetime.strptime(f"{m['date']} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=UK)
        sc = (m.get("score") or {}).get("ft")
        out.append({
            "utc": local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "md": int(re.sub(r"\D", "", m.get("round", "0")) or 0),
            "h": key(m["team1"]), "a": key(m["team2"]),
            "hs": sc[0] if sc else None, "as": sc[1] if sc else None,
        })
    out.sort(key=lambda x: x["utc"])
    return out


def fetch_table():
    """Live league table + the club metadata (logo, short name) the UI renders."""
    d = get(f"{ESPN2}/standings?season={SEASON[:4]}")
    entries = d["children"][0]["standings"]["entries"]
    table, teams = [], {}
    for e in entries:
        t = e["team"]
        k = key(t["displayName"])
        s = {x["name"]: x for x in e["stats"]}
        val = lambda n: int(float(s.get(n, {}).get("value", 0)))
        logo = (t.get("logos") or [{}])[0].get("href", "")
        if logo:  # ESPN's own resizer: 130KB source -> ~3KB. 20 crests, not 2.6MB.
            logo = ("https://a.espncdn.com/combiner/i?img="
                    + logo.split("a.espncdn.com", 1)[-1] + "&w=64&h=64")
        teams[k] = {"name": t["displayName"], "short": t.get("shortDisplayName", t["displayName"]),
                    "abbr": t.get("abbreviation", ""), "id": t.get("id", ""), "logo": logo}
        table.append({"t": k, "rank": val("rank"), "pld": val("gamesPlayed"),
                      "w": val("wins"), "d": val("ties"), "l": val("losses"),
                      "gf": val("pointsFor"), "ga": val("pointsAgainst"),
                      "gd": val("pointDifferential"), "pts": val("points")})
    table.sort(key=lambda r: r["rank"])
    return table, teams


def fetch_recent(days=16):
    """ESPN results for the last N days -> fills openfootball's ~2-day score lag."""
    today = datetime.now(timezone.utc).date()
    rng = f"{(today - timedelta(days=days)):%Y%m%d}-{(today + timedelta(days=2)):%Y%m%d}"
    out = {}
    for e in get(f"{ESPN}/scoreboard?dates={rng}&limit=500").get("events", []):
        c = (e.get("competitions") or [{}])[0]
        st = (c.get("status") or {}).get("type") or {}
        comps = c.get("competitors", [])
        if len(comps) != 2:
            continue
        home = next((x for x in comps if x.get("homeAway") == "home"), None)
        away = next((x for x in comps if x.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        hk, ak = key(home["team"]["displayName"]), key(away["team"]["displayName"])
        out[(hk, ak)] = {
            "hs": int(home["score"]) if str(home.get("score", "")).isdigit() else None,
            "as": int(away["score"]) if str(away.get("score", "")).isdigit() else None,
            "done": bool(st.get("completed")),
            "live": st.get("state") == "in",
            "clock": st.get("shortDetail", "") if st.get("state") == "in" else "",
        }
    return out


def main():
    matches = fetch_season()
    table, teams = fetch_table()
    if len(matches) < 300 or len(table) != 20:
        sys.exit(f"refusing to write: {len(matches)} matches, {len(table)} table rows")

    recent = fetch_recent()
    live = 0
    for m in matches:
        r = recent.get((m["h"], m["a"]))
        if not r:
            m["done"] = m["hs"] is not None
            continue
        if r["hs"] is not None:                 # ESPN wins: it is fresher than openfootball
            m["hs"], m["as"] = r["hs"], r["as"]
        m["done"] = r["done"]
        if r["live"]:
            m["live"], m["clock"] = True, r["clock"]
            live += 1

    data = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "season": SEASON.replace("-", "/"), "teams": teams,
            "table": table, "matches": matches}
    with open("data.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))
    played = sum(1 for m in matches if m.get("done"))
    print(f"wrote data.json — {len(matches)} matches, {played} played, {live} live, {len(table)} table rows")


if __name__ == "__main__":
    main()
