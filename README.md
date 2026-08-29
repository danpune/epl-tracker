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

## Files

    fetch_data.py   both feeds -> data.json   (stdlib only)
    test_fetch.py   self-check: DST + name matching + data integrity
    index.html      the whole UI, one file, no framework
    data.json       generated, ~45KB

## Run locally

```bash
python3 fetch_data.py && python3 test_fetch.py && python3 -m http.server
```
