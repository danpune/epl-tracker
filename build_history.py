#!/usr/bin/env python3
"""Build history.json — head-to-head records between clubs, from 16 seasons of
openfootball (the same CC0 source as the fixture list).

Run rarely: past seasons never change, so this is a one-off that only needs rerunning
when a new season starts. Output is trimmed to pairs involving a current Premier
League club, which keeps the file small enough to ship with the page.
"""
import json, re, sys, urllib.request

SEASONS = [f"{y}-{str(y+1)[2:]}" for y in range(2011, 2027)]
UA = {"User-Agent": "epl-tracker/1.0 (github.com/danpune/epl-tracker)"}


def key(name):
    s = name.lower().replace("&", "and")
    s = re.sub(r"\b(fc|afc|cf)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


def main():
    # only the 20 league clubs: cup opponents would add hundreds of pairs nobody opens
    current = {r["t"] for r in json.load(open("data.json"))["table"]}
    pairs, seasons_ok = {}, 0

    for s in SEASONS:
        url = f"https://raw.githubusercontent.com/openfootball/football.json/master/{s}/en.1.json"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                d = json.load(r)
        except Exception as e:
            print(f"  {s}: {e}")
            continue
        seasons_ok += 1

        for m in d.get("matches", []):
            # openfootball is not uniform across 15 seasons: `score` is usually
            # {"ft":[h,a]} but some entries carry the pair directly, or score1/score2.
            sc = m.get("score")
            if isinstance(sc, dict):
                ft = sc.get("ft")
            elif isinstance(sc, list):
                ft = sc
            elif m.get("score1") is not None:
                ft = [m.get("score1"), m.get("score2")]
            else:
                ft = None
            if not ft or len(ft) != 2 or ft[0] is None or ft[1] is None:
                continue
            h, a = key(m["team1"]), key(m["team2"])
            if h not in current or a not in current:
                continue
            pk = "|".join(sorted((h, a)))
            rec = pairs.setdefault(pk, {"n": 0, "w": {}, "d": 0, "last": []})
            rec["n"] += 1
            if ft[0] > ft[1]:
                rec["w"][h] = rec["w"].get(h, 0) + 1
            elif ft[1] > ft[0]:
                rec["w"][a] = rec["w"].get(a, 0) + 1
            else:
                rec["d"] += 1
            rec["last"].append({"s": s, "h": h, "a": a, "hs": ft[0], "as": ft[1], "d": m["date"]})

    for rec in pairs.values():
        rec["last"] = sorted(rec["last"], key=lambda x: x["d"])[-5:]   # five most recent meetings

    with open("history.json", "w") as f:
        json.dump({"seasons": seasons_ok, "from": SEASONS[0], "to": SEASONS[-1],
                   "pairs": pairs}, f, separators=(",", ":"))
    print(f"wrote history.json — {seasons_ok} seasons, {len(pairs)} club pairs")


if __name__ == "__main__":
    main()
