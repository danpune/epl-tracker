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
ESPN_SOCCER = "https://site.api.espn.com/apis/site/v2/sports/soccer"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
# The cups run on the same free ESPN feed. They return nothing until each draw is
# made (UCL league phase, FA Cup rounds), so an empty list here is expected, not a bug.
CUPS = [("uefa.champions", "UCL"), ("eng.fa", "FA"), ("eng.league_cup", "EFL")]
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
            "c": "PL", "h": key(m["team1"]), "a": key(m["team2"]),
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


def fetch_event_ids():
    """ESPN's event id for every league fixture, so the page can pull lineups and
    match stats on demand. Fetched a month at a time — the scoreboard caps a range."""
    ids, y = {}, int(SEASON[:4])
    months = [(y, m) for m in range(7, 13)] + [(y + 1, m) for m in range(1, 8)]
    for yy, mm in months:
        last = (datetime(yy + (mm == 12), (mm % 12) + 1, 1) - timedelta(days=1)).day
        rng = f"{yy}{mm:02d}01-{yy}{mm:02d}{last:02d}"
        try:
            d = get(f"{ESPN}/scoreboard?dates={rng}&limit=500")
        except Exception as e:
            print(f"  event ids {rng}: {e}")
            continue
        for e in d.get("events", []):
            c = (e.get("competitions") or [{}])[0]
            comps = c.get("competitors", [])
            if len(comps) != 2:
                continue
            h = next((x for x in comps if x.get("homeAway") == "home"), None)
            a = next((x for x in comps if x.get("homeAway") == "away"), None)
            if h and a:
                ids[(key(h["team"]["displayName"]), key(a["team"]["displayName"]))] = str(e.get("id", ""))
    return ids


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



def fetch_cup(code, tag, teams):
    """One knockout/cup competition off the same ESPN feed.

    Kept only where a current Premier League club is involved — the point is your
    club's calendar, not every qualifying-round tie. Adds any non-league opponent
    (and its crest) to the team map so the UI can render it.
    """
    rng = f"{SEASON[:4]}0701-{int(SEASON[:4]) + 1}0701"
    try:
        d = get(f"{ESPN_SOCCER}/{code}/scoreboard?dates={rng}&limit=1000")
    except Exception as e:
        print(f"  {tag}: fetch failed ({e}) — skipping, keeping the rest")
        return []

    out = []
    for e in d.get("events", []):
        c = (e.get("competitions") or [{}])[0]
        comps = c.get("competitors", [])
        if len(comps) != 2:
            continue
        home = next((x for x in comps if x.get("homeAway") == "home"), None)
        away = next((x for x in comps if x.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        hk, ak = key(home["team"]["displayName"]), key(away["team"]["displayName"])
        if hk not in teams and ak not in teams:
            continue                                    # neither side is a PL club

        for side, k in ((home, hk), (away, ak)):
            if k not in teams:                          # e.g. a League Two cup opponent
                t = side["team"]
                logo = t.get("logo") or ""
                if logo:
                    logo = ("https://a.espncdn.com/combiner/i?img="
                            + logo.split("a.espncdn.com", 1)[-1] + "&w=64&h=64")
                teams[k] = {"name": t.get("displayName", k), "short": t.get("shortDisplayName", k),
                            "abbr": t.get("abbreviation", ""), "id": t.get("id", ""), "logo": logo}

        st = (c.get("status") or {}).get("type") or {}
        num = lambda x: int(x["score"]) if str(x.get("score", "")).isdigit() else None
        note = next((n.get("headline", "") for n in (c.get("notes") or []) if n.get("headline")), "")
        out.append({"utc": e.get("date", "")[:16].replace(" ", "T") + "Z" if e.get("date") else "",
                    "c": tag, "md": 0, "e": str(e.get("id", "")), "h": hk, "a": ak,
                    "hs": num(home), "as": num(away),
                    "done": bool(st.get("completed")),
                    "live": st.get("state") == "in",
                    "clock": st.get("shortDetail", "") if st.get("state") == "in" else "",
                    "note": note})
    return [m for m in out if m["utc"]]


def resolve(label, teams):
    """Kalshi's short label ('Brighton', 'Spurs') -> our club key.

    Exact match first, then a unique prefix. Ambiguity is dropped rather than guessed:
    a wrong club here would put the wrong odds on a fixture.
    """
    k = key(label)
    if k in teams:
        return k
    hits = [t for t in teams if t.startswith(k) or k.startswith(t)]
    return hits[0] if len(hits) == 1 else None


def fetch_odds(teams):
    """Kalshi's per-match EPL markets (series KXEPLGAME) -> implied win/draw/win %.

    Three markets per fixture (home / away / Tie). Kalshi lists fixtures weeks out but
    quotes nothing until near kickoff, so most events legitimately carry no price.
    """
    markets, cursor = [], ""
    try:
        for _ in range(10):
            u = f"{KALSHI}/markets?series_ticker=KXEPLGAME&limit=1000&status=open"
            d = get(u + (f"&cursor={cursor}" if cursor else ""))
            markets += d.get("markets", [])
            cursor = d.get("cursor") or ""
            if not cursor:
                break
    except Exception as e:
        print(f"  kalshi: fetch failed ({e}) — continuing without odds")
        return {}

    events, unmatched = {}, set()
    for m in markets:
        events.setdefault(m.get("event_ticker"), []).append(m)

    odds = {}
    for legs in events.values():
        pick = {}
        for m in legs:
            lab = (m.get("yes_sub_title") or "").strip()
            bid, ask = m.get("yes_bid"), m.get("yes_ask")
            price = ((bid + ask) / 2 if bid is not None and ask is not None
                     else bid if bid is not None else ask)
            if price is None:
                continue                                 # no quote yet — normal weeks out
            if lab.lower() == "tie":
                pick["d"] = price
            else:
                k = resolve(lab, teams)
                if k:
                    pick[k] = price
                else:
                    unmatched.add(lab)
        sides = [k for k in pick if k != "d"]
        if len(sides) == 2 and "d" in pick:
            odds[frozenset(sides)] = {"sides": pick}
    if unmatched:
        print(f"  kalshi: could not map {sorted(unmatched)} — those fixtures get no odds")
    return odds


def main():
    matches = fetch_season()
    table, teams = fetch_table()
    if len(matches) < 300 or len(table) != 20:   # league only at this point
        sys.exit(f"refusing to write: {len(matches)} matches, {len(table)} table rows")

    for code, tag in CUPS:
        cup = fetch_cup(code, tag, teams)
        print(f"  {tag}: {len(cup)} matches involving a PL club")
        matches += cup
    matches.sort(key=lambda x: x["utc"])

    eids = fetch_event_ids()
    linked = 0
    for m in matches:
        i = eids.get((m["h"], m["a"]))
        if i:
            m["e"] = i
            linked += 1
    print(f"  linked {linked}/{len(matches)} matches to ESPN event ids (lineups + stats)")

    odds = fetch_odds(teams)
    priced = 0
    for m in matches:
        o = odds.get(frozenset((m["h"], m["a"])))
        if o and not m.get("done"):
            p = o["sides"]
            if m["h"] in p and m["a"] in p:
                m["o"] = [round(p[m["h"]]), round(p["d"]), round(p[m["a"]])]
                priced += 1

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
            "paths": {"PL": "eng.1", "UCL": "uefa.champions", "FA": "eng.fa", "EFL": "eng.league_cup"},
            "table": table, "matches": matches}
    with open("data.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))
    played = sum(1 for m in matches if m.get("done"))
    print(f"wrote data.json — {len(matches)} matches, {played} played, {live} live, "
          f"{priced} with odds, {len(table)} table rows")


if __name__ == "__main__":
    main()
