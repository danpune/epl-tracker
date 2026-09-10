# Daily tracker health check

Checklist for the scheduled cloud agent. Editing this file changes what the daily
check does — the routine itself just points here.

**Sites** (all `https://danpune.github.io/REPO/`):
`epl-tracker`, `wrexham-tracker`, `tennis-slams-tracker`, `india-cricket-tracker`,
`worldcup2026`

Each is a no-build static site: a Python fetcher writes JSON, a GitHub Actions cron
commits it, one `index.html` renders it. No server, no database.

**You run unattended with no browser.** Verify by curling the live files and running
each repo's own Python. **Report only — do not commit, push or edit anything.**

## Per site, in order

**1. Up.** curl the live URL and its main JSON (find the filename in the repo —
`data.json`, `scores.json`…). Non-200 or unparseable content is CRITICAL.

**2. Fresh.** The data file carries an `updated` UTC timestamp. Report its age.
Over 12h is a WARNING, over 24h is CRITICAL — it means the cron has silently stopped
committing. *This is the highest-value check here: a real 21-hour freeze went
unnoticed until a human happened to look.*

**3. Cron.** `curl https://api.github.com/repos/danpune/REPO/actions/runs?per_page=10`
and report recent conclusions. Consecutive failures are CRITICAL — quote the actual
error from the failed job. A fetcher crash caused by an upstream feed changing shape
is the known failure mode.

**4. Self-check.** If the repo has `test_fetch.py` (or similar), run it against the
**live** data file. Report the exact assertion text on failure.

**5. Data sanity.** For any site with fixtures/results, confirm none of these:
- a match marked finished whose kickoff is *after* the file's `updated` time
- an unplayed match carrying a score (upstream feeds send `0` before kickoff)
- two matches sharing one upstream event id
- a settled match still carrying pre-match odds
- for league sites: points = 3·W + D, GD = GF − GA, played = W + D + L on every row

**6. Page renders.** curl `index.html` and confirm it is intact HTML, references its
JSON files, and has no obviously truncated script. You cannot execute JS — do not
claim the UI "works", only that the page and its assets are served and well-formed.

**7. Code drift** *(only for repos whose HEAD moved in the last 24h)*: skim the diff
for the recurring hazards — a match keyed without its competition, a score read
without checking the upstream `state`, an edit that silently no-oped, a CSS override
declared before the rule it overrides.

## Report

Lead with anything CRITICAL, then WARNINGs, then a one-line-per-site all-clear.
Be specific: numbers, ages in hours, quoted errors. If everything is healthy, say so
plainly and keep it short. Never claim something is verified that you did not verify —
say what you could not check and why.
