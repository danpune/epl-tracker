# Premier League Tracker ⚽

**Live site: https://danpune.github.io/epl-tracker/**

The table, the full 380-match season, and every kickoff converted to **your** timezone.
Static site, no build step, no API key, no database. Runs on GitHub Pages for $0.

## Why two data sources

| Source | Used for | Why |
| --- | --- | --- |
| [openfootball/football.json](https://github.com/openfootball/football.json) (CC0) | the 380-match schedule | Whole season in one 53KB file, published months ahead. Scores lag ~2 days. |
| ESPN public feed | league table, live results | Always current, no key, no rate limit. |

The schedule source is public domain; the table source is free and unauthenticated.
Nothing here depends on a paid tier that can lapse.

## How often it actually updates

Two different clocks, deliberately:

- **Live scores** are fetched by the page itself, straight from ESPN, roughly once a
  minute while a match is in play (and not at all when nothing is on). They do not
  wait for a build.
- **Everything else** — table, fixtures, scorers, highlights, calendars — comes from
  the scheduled workflow.

The workflow's cron asks for every 30 minutes. **GitHub does not honour that**: it
deprioritises scheduled runs on low-traffic repos and in practice fires this one every
~3.4 hours (measured median over two days; the odd-minute `:13/:43` trick is already
applied and is not enough). That cadence is fine for a fixture list and a league table,
and it is exactly why live scores are fetched client-side instead.

## Timezone handling

openfootball publishes bare UK local times (`"15:00"`) with no offset, so they are
converted to UTC through `zoneinfo` at fetch time. That matters: a 3pm kickoff is
`14:00Z` in August but `15:00Z` in December. The browser then renders UTC in the
viewer's own zone via `toLocaleString` — no timezone picker, no server work.

**Later fixtures are provisional.** Broadcasters move matches for TV about five weeks
out; the fetch runs every 30 minutes, so reschedules flow through as they are announced.

## What it does

- **Table** with a computed form guide (last 5), CL and relegation zones.
- **Fixtures** across the league *and* the cups — tap any match for lineups
  (formation + XI + bench), match stats, and goalscorers, pulled live from ESPN
  on click so the page itself stays small.
- **My Kickoff Times** — every match converted to your timezone and split into
  three mutually exclusive buckets: easy, clashes with work, and set-an-alarm.
- **Calendar** — one `.ics` for your club's whole season, or a single match, plus
  a Google Calendar link. Built in the browser; there is no backend.
- **Odds** — Kalshi's market-implied win/draw/win where a market is quoted.
- **Highlights** — official Premier League YouTube uploads, each verified through
  oEmbed against the channel URL (not the channel *name*: a spoofed name burned the
  sibling World Cup project). Clips stamped with a previous season are rejected, and
  anything unmatched falls back to a YouTube search.
- **Kickoff weather** — temperature and rain chance at the ground, for matches inside
  Open-Meteo's ~16-day window. Free, keyless; venues geocoded once into `venues.json`.
- **Squads** — full club roster, grouped by position, loaded on demand.
- **Share cards** — a 1200x630 result or fixture card drawn on a canvas in the browser
  (Web Share on mobile, download on desktop). No dependency, nothing uploaded.
- **Head to head** — 16 seasons of meetings between the two clubs, on every match.
- **Dark mode**, and installable to a phone home screen (web manifest).
- **Top scorers**, built match by match from key events (ESPN's leaders endpoint is
  empty for soccer), league and cup goals counted separately.
- **Where to watch** — the US broadcaster per fixture, straight from ESPN.
- **Subscribable calendars** — `ics/<club>.ics` per club, so a subscription keeps up
  when TV moves a fixture; a one-off download cannot.

## Competitions

Premier League from openfootball; FA Cup, Champions League and EFL Cup from the same
free ESPN feed, filtered to ties involving a Premier League club. The two cups return
nothing until their draws are made — an empty competition is expected, not a failure.

## Prediction markets

Kalshi's `KXEPLGAME` series carries a home / away / tie market per fixture, public and
unauthenticated. Kalshi lists fixtures weeks ahead but quotes nothing until close to
kickoff, so most fixtures legitimately carry no price. Their short labels ("Brighton",
"Newcastle") are resolved to clubs by exact-then-unique-prefix match; anything ambiguous
is dropped rather than guessed, because wrong odds are worse than no odds. Polymarket
carries no Premier League markets at all.

## Files

    fetch_data.py     both feeds -> data.json + ics/*.ics   (stdlib only)
    build_scorers.py    goalscorers, accumulated match by match (merge-only)
    build_highlights.py official YouTube clips, oEmbed-verified (merge-only)
    build_history.py    16 seasons of head-to-head; rerun only when a season starts
    test_fetch.py   self-check: DST + name matching + data integrity
    index.html      the whole UI, one file, no framework
    data.json       generated, ~90KB

## Run locally

```bash
python3 fetch_data.py && python3 test_fetch.py && python3 -m http.server
```

## The share card

`make_preview.py` renders `preview.jpg` (1200x630) from the live `data.json`, so a link
pasted into WhatsApp, iMessage or Slack shows the **current table and matchday** rather
than a logo. ESPN, BBC Sport, FotMob and the Premier League's own site all share a
static image (the PL site sets no `og:image` at all) — this one is regenerated on every
data update.

Note `og:image` must be an absolute `https://` URL; a relative path renders no card.
Chat apps also cache aggressively, so an already-shared link keeps its old preview until
their scraper refetches.

## Licence

MIT — see [LICENSE](LICENSE).
