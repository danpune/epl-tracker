#!/usr/bin/env python3
"""Build scorers.json — the league's goalscorers, accumulated match by match.

ESPN's /leaders endpoint returns nothing for soccer, so the table is assembled from
each finished match's key events instead. Incremental and merge-only: a match is
fetched once, then never again, so a full season costs ~380 requests spread over
nine months rather than 380 every run.

Fail-safe: any single match that fails is skipped and retried next run; an existing
scorers.json is never truncated on failure.
"""
import json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "epl-tracker/1.0 (github.com/danpune/epl-tracker)"}
PATHS = {"PL": "eng.1", "UCL": "uefa.champions", "FA": "eng.fa", "EFL": "eng.league_cup"}
OUT = "scorers.json"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def main():
    data = json.load(open("data.json"))
    prev = {"matches": {}, "players": {}}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT))
        except Exception:
            pass
    seen = prev.get("matches", {})

    now = datetime.now(timezone.utc)
    stale_before = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%MZ")
    todo = [m for m in data["matches"]
            if m.get("done") and m.get("e") and m["e"] not in seen
            and m["utc"] <= now.strftime("%Y-%m-%dT%H:%MZ")]   # never parse the future
    print(f"{len(seen)} matches already parsed, {len(todo)} new")

    added = 0
    for m in todo[:60]:                       # cap per run; the rest catch up next time
        path = PATHS.get(m.get("c", "PL"), "eng.1")
        try:
            d = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{path}/summary?event={m['e']}")
        except Exception as e:
            print(f"  {m['e']}: {e}")
            continue

        goals = []
        for ev in d.get("keyEvents", []):
            text = ((ev.get("type") or {}).get("text") or "").lower()
            if "goal" not in text or "no goal" in text:
                continue
            own = "own" in text
            team_id = str(((ev.get("team") or {}).get("id")) or "")
            for p in (ev.get("participants") or []):
                a = p.get("athlete") or {}
                nm = a.get("displayName")
                if not nm:
                    continue
                # only the scorer is credited; ESPN lists assists in the same array
                if (p.get("type") or "").lower() in ("assist", "secondassist"):
                    continue
                goals.append({"n": nm, "i": str(a.get("id", "")), "t": team_id,
                              "own": own, "c": m.get("c", "PL")})
                break
        # Only bank the result when it is trustworthy. A 0-goal parse on a match that
        # has not kicked off (or whose events ESPN has not filled in yet) would be
        # cached forever by this merge-only file, silently losing every real goal.
        if goals or m["utc"] < stale_before:
            seen[m["e"]] = len(goals)
        added += len(goals)

        for g in goals:
            if g["own"]:
                continue                       # own goals do not credit a scorer
            k = g["i"] or g["n"]
            rec = prev.setdefault("players", {}).setdefault(
                k, {"n": g["n"], "g": 0, "l": 0, "t": g["t"]})
            rec["g"] += 1
            if g["c"] == "PL":
                rec["l"] = rec.get("l", 0) + 1     # league goals, which is what a table means
            rec["n"] = g["n"]
            if g["t"]:
                rec["t"] = g["t"]

    prev["matches"] = seen
    with open(OUT, "w") as f:
        json.dump(prev, f, separators=(",", ":"))
    top = sorted(prev.get("players", {}).values(), key=lambda x: (-x.get("l", 0), -x["g"]))[:5]
    print(f"wrote {OUT} — {len(prev.get('players', {}))} scorers, {added} goals added this run")
    for p in top:
        print(f"   {p.get('l', 0)} league ({p['g']} all)  {p['n']}")


if __name__ == "__main__":
    main()
