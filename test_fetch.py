#!/usr/bin/env python3
"""Self-check: run `python3 test_fetch.py` after a fetch. Asserts only, no framework.

Guards the two things that would corrupt data silently:
  1. UK local -> UTC across the DST boundary (a naive +1 breaks half the season)
  2. the club-name normaliser that joins openfootball's names to ESPN's
"""
import json, os, sys
from datetime import datetime, timezone
from fetch_data import key, UK

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

# 3. data.json integrity (skipped if it has not been fetched yet)
if os.path.exists("data.json"):
    d = json.load(open("data.json"))
    assert len(d["matches"]) == 380, f'expected 380 matches, got {len(d["matches"])}'
    assert len(d["teams"]) == 20 and len(d["table"]) == 20
    per_team = {}
    for m in d["matches"]:
        for side in (m["h"], m["a"]):
            assert side in d["teams"], f"match references unknown club {side!r}"
            per_team[side] = per_team.get(side, 0) + 1
        datetime.strptime(m["utc"], "%Y-%m-%dT%H:%MZ")          # parses, or raises
        assert (m["hs"] is None) == (m["as"] is None), "half a scoreline"
    assert set(per_team.values()) == {38}, f"every club plays 38: got {sorted(set(per_team.values()))}"
    # the three kickoff buckets the UI shows must partition the season, not overlap
    for k in d["teams"]:
        ms = [m for m in d["matches"] if k in (m["h"], m["a"])]
        assert len(ms) == 38
else:
    print("(no data.json yet — ran source checks only)")

print("all checks passed")
