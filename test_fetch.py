#!/usr/bin/env python3
"""Self-check: run `python3 test_fetch.py` after a fetch. Asserts only, no framework.

Guards the two things that would corrupt data silently:
  1. UK local -> UTC across the DST boundary (a naive +1 breaks half the season)
  2. the club-name normaliser that joins openfootball's names to ESPN's
"""
import json, os, sys
from datetime import datetime, timezone
from fetch_data import key, resolve, UK

# 1. name normaliser: the two feeds spell the same club differently
assert key("Manchester United FC") == key("Manchester United")
assert key("Brighton & Hove Albion FC") == key("Brighton and Hove Albion")
assert key("AFC Bournemouth") == key("Bournemouth")
assert key("Manchester United") != key("Manchester City"), "must not collapse distinct clubs"

# 2. DST: same 15:00 UK kickoff is 14:00Z in summer and 15:00Z in winter
to_utc = lambda d, t: (datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
                       .replace(tzinfo=UK).astimezone(timezone.utc).strftime("%H:%MZ"))
assert to_utc("2026-08-22", "15:00") == "14:00Z", "August is BST (UTC+1)"
assert to_utc("2026-12-26", "15:00") == "15:00Z", "December is GMT (UTC+0)"
assert to_utc("2026-08-22", "12:30") == "11:30Z", "cross-checked against ESPN's own feed"

# 3. Kalshi label resolution: short labels must land on the right club, and an
#    ambiguous one must resolve to nothing rather than guess (wrong odds > no odds)
_t = {"manchesterunited": 0, "manchestercity": 0, "brightonandhovealbion": 0,
      "newcastleunited": 0, "tottenhamhotspur": 0, "nottinghamforest": 0}
assert resolve("Brighton", _t) == "brightonandhovealbion"
assert resolve("Newcastle", _t) == "newcastleunited"
assert resolve("Tottenham", _t) == "tottenhamhotspur"
assert resolve("Manchester United", _t) == "manchesterunited"
assert resolve("Manchester", _t) is None, "ambiguous label must not be guessed"
assert resolve("Real Madrid", _t) is None

# 4. data.json integrity (skipped if it has not been fetched yet)
if os.path.exists("data.json"):
    d = json.load(open("data.json"))
    league = [m for m in d["matches"] if m["c"] == "PL"]
    assert len(league) == 380, f"expected 380 league matches, got {len(league)}"
    assert len(d["table"]) == 20
    assert len(d["teams"]) >= 20, "cup opponents are added on top of the 20 league clubs"
    assert {m["c"] for m in d["matches"]} <= {"PL", "UCL", "FA", "EFL"}, "unknown competition tag"
    per_team = {}
    for m in league:
        for side in (m["h"], m["a"]):
            assert side in d["teams"], f"match references unknown club {side!r}"
            per_team[side] = per_team.get(side, 0) + 1
        datetime.strptime(m["utc"], "%Y-%m-%dT%H:%MZ")          # parses, or raises
        assert (m["hs"] is None) == (m["as"] is None), "half a scoreline"
    assert set(per_team.values()) == {38}, f"every club plays 38: got {sorted(set(per_team.values()))}"

    # a finished match cannot kick off in the future. This is the check that would
    # have caught 133 unplayed cup ties being shipped as completed 0-0 draws.
    future_done = [m for m in d["matches"] if m.get("done") and m["utc"] > d["updated"]]
    assert not future_done, (f"{len(future_done)} matches marked done with a future "
                             f"kickoff, e.g. {future_done[0]}")

    # an unplayed match must not carry a scoreline. ESPN reports "0" before kickoff and
    # that is how 133 phantom 0-0 results shipped once already.
    ghost = [m for m in d["matches"]
             if m.get("hs") is not None and not m.get("done") and not m.get("live")]
    assert not ghost, f"{len(ghost)} unplayed matches carry a score, e.g. {ghost[0]}"

    # every cup tie must involve a current league club — this is a Premier League tracker
    league = {r["t"] for r in d["table"]}
    stray = [m for m in d["matches"]
             if m["c"] != "PL" and m["h"] not in league and m["a"] not in league]
    assert not stray, f"{len(stray)} cup ties involve no league club, e.g. {stray[0]}"

    # every match, cups included, must reference a club the UI can name and draw
    for m in d["matches"]:
        assert m["h"] in d["teams"] and m["a"] in d["teams"], f"unnamed club in {m}"
        datetime.strptime(m["utc"], "%Y-%m-%dT%H:%MZ")

    # odds, where present: three whole percentages, plausible with Kalshi's overround
    for m in d["matches"]:
        if "o" in m:
            o = m["o"]
            assert len(o) == 3 and all(0 <= x <= 100 for x in o), f"bad odds {o}"
            assert 90 <= sum(o) <= 130, f"implied probabilities implausible: {o} sums {sum(o)}"
            assert not m.get("done"), "settled match should not carry live odds"
else:
    print("(no data.json yet — ran source checks only)")

print("all checks passed")
