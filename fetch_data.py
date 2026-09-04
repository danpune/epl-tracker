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
import json, os, re, sys, urllib.parse, urllib.request
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


def fetch_colors():
    """Club colours, so the page can wear whichever club you follow."""
    try:
        d = get(f"{ESPN}/teams")
        out = {}
        for x in d["sports"][0]["leagues"][0]["teams"]:
            t = x["team"]
            out[key(t["displayName"])] = ("#" + (t.get("color") or "3d195b"),
                                          "#" + (t.get("alternateColor") or "1d1526"))
        return out
    except Exception as e:
        print(f"  colours: {e} — falling back to the league palette")
        return {}


def fetch_table():
    """Live league table + the club metadata (logo, colours, short name) the UI renders."""
    colors = fetch_colors()
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
        col = colors.get(k, ("#3d195b", "#1d1526"))
        teams[k] = {"name": t["displayName"], "short": t.get("shortDisplayName", t["displayName"]),
                    "abbr": t.get("abbreviation", ""), "id": t.get("id", ""), "logo": logo,
                    "col": col[0], "col2": col[1]}
        table.append({"t": k, "rank": val("rank"), "pld": val("gamesPlayed"),
                      "w": val("wins"), "d": val("ties"), "l": val("losses"),
                      "gf": val("pointsFor"), "ga": val("pointsAgainst"),
                      "gd": val("pointDifferential"), "pts": val("points")})
    table.sort(key=lambda r: r["rank"])
    return table, teams


def fetch_event_ids():
    """ESPN's event id AND the US broadcaster for every league fixture, in one pass.
    The id lets the page pull lineups/stats on demand; the broadcaster answers the
    question a schedule alone cannot — where do I actually watch this."""
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
                tv = []
                for b in (c.get("broadcasts") or []):
                    tv += [n for n in (b.get("names") or []) if n]
                seen = set()
                tv = [x for x in tv if not (x in seen or seen.add(x))]
                v = c.get("venue") or {}
                # keyed by competition too: Forest v Leeds happens in BOTH the league
                # and the EFL Cup, and without this the cup tie inherits the league id
                ids[("PL", key(h["team"]["displayName"]), key(a["team"]["displayName"]))] = {
                    "e": str(e.get("id", "")), "tv": tv[:3],
                    "utc": (e.get("date") or "")[:16] + "Z" if e.get("date") else "",
                    "v": v.get("fullName", ""),
                    "vc": ((v.get("address") or {}).get("city") or "")}
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
        started = st.get("state") != "pre"          # ESPN sends "0" for scheduled matches
        out[("PL", hk, ak)] = {
            "hs": int(home["score"]) if started and str(home.get("score", "")).isdigit() else None,
            "as": int(away["score"]) if started and str(away.get("score", "")).isdigit() else None,
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

    league = set(teams)          # snapshot: the loop below ADDS to `teams`, and filtering
    out = []                     # against the growing set let every opponent's own ties in
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
        if hk not in league and ak not in league:
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
        started = st.get("state") != "pre"      # ESPN sends "0" for scheduled matches
        num = lambda x: (int(x["score"]) if started and str(x.get("score", "")).isdigit()
                         else None)
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

    def cents(m):
        """Kalshi returns decimal-dollar STRINGS ("0.2500"), not integer cents, and
        names them *_dollars. Reading the older yes_bid/yes_ask returned None for
        every market, which looked exactly like an empty order book."""
        def f(key):
            v = m.get(key)
            try:
                return float(v) * 100 if v not in (None, "") else None
            except (TypeError, ValueError):
                return None
        bid, ask = f("yes_bid_dollars"), f("yes_ask_dollars")
        if bid is not None and ask is not None:
            return (bid + ask) / 2                       # mid of the book
        return bid if bid is not None else ask if ask is not None else f("last_price_dollars")

    odds = {}
    for legs in events.values():
        pick, when = {}, ""
        for m in legs:
            when = when or (m.get("occurrence_datetime") or "")[:10]
            lab = (m.get("yes_sub_title") or "").strip()
            price = cents(m)
            if price is None:
                continue                                 # genuinely no quote yet
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
            # keyed with the DATE as well: the same two clubs meet twice a season and
            # home advantage is exactly what the price encodes, so the legs must not
            # share one entry.
            odds[(frozenset(sides), when)] = {"sides": pick}
    if unmatched:
        print(f"  kalshi: could not map {sorted(unmatched)} — those fixtures get no odds")
    return odds


def ics_escape(t):
    return t.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", " ")


def geocode_venues(data):
    """Lat/lon per stadium, so the page can show the kickoff forecast.

    Cached in venues.json and only ever looked up once per ground — Open-Meteo's
    geocoder is free but there is no reason to ask it the same question weekly.
    Results are constrained to the UK: "Old Trafford" also matches a park in Australia.
    """
    cache = {}
    if os.path.exists("venues.json"):
        try:
            cache = json.load(open("venues.json"))
        except Exception:
            pass

    names = {}
    for m in data["matches"]:
        if m.get("v") and m["v"] not in cache:
            names[m["v"]] = m.get("vc", "")

    for name, city in list(names.items())[:25]:          # a few per run; they persist
        # ESPN hyphenates some cities ("Newcastle-upon-Tyne"); the geocoder wants spaces
        city_q = city.replace("-", " ").strip() if city else None
        plain = re.sub(r"[^\w\s]", "", name).strip()

        def lookup(q):
            """First UK hit for a query. The API ignores its own country= filter, so
            the country_code check below is what actually constrains it."""
            if not q:
                return None
            try:
                u = ("https://geocoding-api.open-meteo.com/v1/search?name="
                     + urllib.parse.quote(q) + "&count=5&language=en&country=GB")
                res = get(u).get("results") or []
            except Exception:
                return None
            for r in res:
                if r.get("country_code") in ("GB", "IE"):
                    return [round(r["latitude"], 4), round(r["longitude"], 4)]
            return None

        # Anchor on the city, then only accept a stadium hit that is near it.
        # "Stamford Bridge" is also a village in East Yorkshire, 250km from Chelsea;
        # without this check the ground pins there and the forecast is for nowhere.
        anchor = lookup(city_q)
        got = None
        for q in (name, plain if plain != name else None):
            hit = lookup(q)
            if not hit:
                continue
            if anchor:
                dlat = (hit[0] - anchor[0]) * 111.0
                dlon = (hit[1] - anchor[1]) * 111.0 * 0.63      # cos(53 deg), UK-ish
                if (dlat * dlat + dlon * dlon) ** 0.5 > 30:     # km from its own city
                    continue                                     # wrong Stamford Bridge
            got = hit
            break
        got = got or anchor
        cache[name] = got                                 # None is cached too: do not retry forever

    with open("venues.json", "w") as f:
        json.dump(cache, f, separators=(",", ":"), sort_keys=True)
    found = sum(1 for v in cache.values() if v)
    print(f"  venues: {found}/{len(cache)} geocoded")
    return {k: v for k, v in cache.items() if v}


def write_calendars(data):
    """One .ics per club, committed to the repo.

    A downloaded file is a snapshot; a SUBSCRIBED url keeps updating, which matters
    here because broadcasters move fixtures for TV all season.
    """
    os.makedirs("ics", exist_ok=True)
    stamp = data["updated"].replace("-", "").replace(":", "")
    league = {r["t"] for r in data["table"]}        # only the 20 clubs; a cup opponent
    for k, t in data["teams"].items():                 # was getting its own ics file
        if k not in league:
            continue
        ms = [m for m in data["matches"] if k in (m["h"], m["a"])]
        out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//epl-tracker//EN",
               "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
               f"X-WR-CALNAME:{ics_escape(t['name'])} {data['season']}",
               "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
        for m in ms:
            st = datetime.strptime(m["utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            en = st + timedelta(hours=2)
            comp = {"PL": "Premier League", "UCL": "Champions League",
                    "FA": "FA Cup", "EFL": "EFL Cup"}.get(m.get("c", "PL"), "")
            title = f"{data['teams'][m['h']]['name']} v {data['teams'][m['a']]['name']}"
            if m.get("c") and m["c"] != "PL":
                title += f" ({comp})"
            desc = comp + (f" matchday {m['md']}" if m.get("c") == "PL" and m.get("md") else "")
            if m.get("tv"):
                desc += " — TV (US): " + ", ".join(m["tv"])
            out += ["BEGIN:VEVENT",
                    f"UID:{m.get('e') or (m['h'] + m['a'] + m['utc'])}@epl-tracker",
                    f"DTSTAMP:{stamp}", f"DTSTART:{st:%Y%m%dT%H%M%SZ}", f"DTEND:{en:%Y%m%dT%H%M%SZ}",
                    f"SUMMARY:{ics_escape(title)}", f"DESCRIPTION:{ics_escape(desc)}", "END:VEVENT"]
        out.append("END:VCALENDAR")
        with open(f"ics/{k}.ics", "w") as f:
            f.write("\r\n".join(out) + "\r\n")
    print(f"  wrote {len(os.listdir('ics'))} subscribable calendars")


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
    linked = tv_n = moved = 0
    for m in matches:
        i = eids.get((m.get("c", "PL"), m["h"], m["a"]))
        if i:
            m["e"] = i["e"]
            linked += 1
            # TV moves fixtures and openfootball lags weeks behind; ESPN carries the
            # real kickoff. Without this the schedule (and every calendar feed) is wrong.
            if i.get("utc") and i["utc"] != m["utc"]:
                m["utc"], moved = i["utc"], moved + 1
            if i["tv"]:
                m["tv"] = i["tv"]
                tv_n += 1
            if i.get("v"):
                m["v"] = i["v"]
                m["vc"] = i.get("vc", "")
    print(f"  linked {linked}/{len(matches)} to ESPN event ids, {tv_n} with a US "
          f"broadcaster, {moved} rescheduled by TV since openfootball published")

    matches.sort(key=lambda x: x["utc"])

    odds = fetch_odds(teams)
    priced = 0
    for m in matches:
        o = odds.get((frozenset((m["h"], m["a"])), m["utc"][:10]))
        if o and not m.get("done"):
            p = o["sides"]
            if m["h"] in p and m["a"] in p:
                m["o"] = [round(p[m["h"]]), round(p["d"]), round(p[m["a"]])]
                priced += 1

    recent = fetch_recent()
    live = 0
    for m in matches:
        r = recent.get((m.get("c", "PL"), m["h"], m["a"]))
        if not r:
            # never clobber a `done` the source already computed (fetch_cup does)
            m.setdefault("done", m["hs"] is not None)
            continue
        if r["hs"] is not None:                 # ESPN wins: it is fresher than openfootball
            m["hs"], m["as"] = r["hs"], r["as"]
        m["done"] = r["done"]
        if r["live"]:
            m["live"], m["clock"] = True, r["clock"]
            live += 1

    pre = {"matches": matches}
    venues = geocode_venues(pre)

    data = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "venues": venues,
            "season": SEASON.replace("-", "/"), "teams": teams,
            "paths": {"PL": "eng.1", "UCL": "uefa.champions", "FA": "eng.fa", "EFL": "eng.league_cup"},
            "table": table, "matches": matches}
    with open("data.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))
    write_calendars(data)
    played = sum(1 for m in matches if m.get("done"))
    print(f"wrote data.json — {len(matches)} matches, {played} played, {live} live, "
          f"{priced} with odds, {len(table)} table rows")


if __name__ == "__main__":
    main()
