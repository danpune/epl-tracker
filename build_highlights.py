#!/usr/bin/env python3
"""Fill highlights.json: finished matches -> OFFICIAL Premier League YouTube videos.

Scrapes the official channel's /videos page for the latest ~30 uploads, then resolves
each id through YouTube's oEmbed endpoint, which returns the title AND the channel.
Every candidate is verified on author_url (NOT author_name — on the sibling World Cup
project a spam channel renamed itself to spoof the name check).

Reality of Premier League rights: the league does not post classic full-match
highlight reels to YouTube worldwide. What it does post is per-match analysis
("How Hull City Outplayed Man United") and matchweek round-ups ("ALL The Goals From
Matchweek 1"). Both are matched here; anything unmatched falls back in the UI to a
YouTube search, exactly like the World Cup site.

Merge-only and fail-safe: never removes entries, exits 0 on any fetch failure.
Standard library only, no API key.
"""
import json, os, re, sys, unicodedata, urllib.request

CHANNEL = "https://www.youtube.com/@premierleague"
OUT = "highlights.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "en"}


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def video_ids():
    """Latest uploads from the channel page. Only ids are taken from the scrape —
    titles come from oEmbed, which does not change shape when YouTube reskins."""
    html = fetch(CHANNEL + "/videos")
    out, seen = [], set()
    for m in re.finditer(r'"contentId":"([\w-]{11})"', html):
        v = m.group(1)
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out[:40]


def verify(vid):
    """oEmbed -> (title, ok). ok only when the upload really is the official channel."""
    u = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
    d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20))
    return d.get("title", ""), (d.get("author_url", "").rstrip("/").lower() == CHANNEL.lower())


# A title naming both clubs is not enough: the channel also posts last season's
# drama and all-time compilations, which would attach the wrong video to a fixture.
OLD_SEASON = re.compile(r"\b(?:19|20)?(\d\d)\s*/\s*(\d\d)\b")  # only a/b season form, not "15-16 August"
COMPILATION = re.compile(r"\b(great|incredible|best|greatest|classic|iconic|shocking|"
                         r"unforgettable|record|ever|all[- ]time|underdog|top \d+|\d+ goals)\b")


def season_ok(title, season):
    """Reject a title stamped with a season that is not the current one.

    Tested on the RAW title: norm() rewrites "2025/26" to "2025 26", which no
    slash-based pattern would ever match.
    """
    cur = (season[2:4], season[5:7])            # "2026/27" -> ("26", "27")
    for m in OLD_SEASON.finditer(title):
        if (m.group(1), m.group(2)) != cur:
            return False
    return True


def aliases(t):
    """Every way the channel might name this club in a title."""
    out = {norm(t["name"]), norm(t["short"])}
    n = norm(t["name"])
    out.add(n.replace("manchester", "man"))
    out.add(n.replace(" fc", "").replace(" afc", "").strip())
    for drop in (" united", " city", " hove albion", " and hove albion", " hotspur", " wanderers"):
        if n.endswith(drop):
            out.add(n[: -len(drop)].strip())
    if "tottenham" in n:
        out.add("spurs")
    if "wolverhampton" in n:
        out.add("wolves")
    return {a for a in out if len(a) > 3}


def main():
    data = json.load(open("data.json"))
    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT)).get("highlights", {})
        except Exception:
            pass

    try:
        ids = video_ids()
    except Exception as e:
        print(f"channel scrape failed ({e}) — keeping {len(prev)} existing entries")
        return

    vids = []
    for v in ids:
        try:
            title, ok = verify(v)
        except Exception:
            continue
        if ok and title:
            vids.append((v, title, norm(title)))
    print(f"{len(ids)} ids scraped, {len(vids)} verified as official uploads")

    teams = data["teams"]
    season = data["season"]                       # e.g. "2026/27"
    finished = [m for m in data["matches"] if m.get("done")]
    added = skipped = 0

    keep = []
    for v, title, nt in vids:
        if not season_ok(title, season):
            skipped += 1
            continue
        keep.append((v, title, nt, bool(COMPILATION.search(nt))))
    vids = keep
    print(f"  {skipped} rejected as a previous season, "
          f"{sum(1 for x in vids if x[3])} flagged as compilations")

    for m in finished:
        mk = m.get("e") or (m["h"] + m["a"] + m["utc"])
        if mk in prev:
            continue
        ha, aa = aliases(teams[m["h"]]), aliases(teams[m["a"]])
        for v, title, nt, comp in vids:
            if comp:
                continue                          # all-time compilation, not this match
            if any(a in nt for a in ha) and any(a in nt for a in aa):
                prev[mk] = {"yt": v, "t": title}
                added += 1
                break

    # matchweek round-ups apply to every league match of that matchday
    for v, title, nt, comp in vids:
        r = re.search(r"matchweek (\d+)", nt)
        if not r:
            continue
        md = int(r.group(1))
        for m in finished:
            if m.get("c") != "PL" or m.get("md") != md:
                continue
            mk = m.get("e") or (m["h"] + m["a"] + m["utc"])
            if mk not in prev:
                prev[mk] = {"yt": v, "t": title, "round": True}
                added += 1

    with open(OUT, "w") as f:
        json.dump({"_howto": "match key (ESPN event id) -> official Premier League YouTube video. "
                             "Every entry verified via oEmbed author_url. Merge-only.",
                   "channel": CHANNEL, "highlights": prev}, f, indent=1)
    print(f"wrote {OUT} — {len(prev)} matches with official video ({added} new)")


if __name__ == "__main__":
    main()
