# Premier League Tracker

The table, the full 380-match season, and every kickoff converted to **your** timezone.
Static site, no build step, no API key, no database. Runs on GitHub Pages for $0.

## Why two data sources

| Source | Used for | Why |
| --- | --- | --- |
| [openfootball/football.json](https://github.com/openfootball/football.json) (CC0) | the 380-match schedule | Whole season in one 53KB file, published months ahead. Scores lag ~2 days. |
| ESPN public feed | league table, live results | Always current, no key, no rate limit. |

The schedule source is public domain; the table source is free and unauthenticated.
Nothing here depends on a paid tier that can lapse.

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
- **Comments** — GitHub Discussions via giscus, loaded only when that tab is opened.
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
    build_scorers.py  goalscorers, accumulated match by match (merge-only)
    test_fetch.py   self-check: DST + name matching + data integrity
    index.html      the whole UI, one file, no framework
    data.json       generated, ~50KB

## Run locally

```bash
python3 fetch_data.py && python3 test_fetch.py && python3 -m http.server
```
