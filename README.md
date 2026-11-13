# hobbyjogging

A personal training database that belongs to you, not to a platform. Its main
job is to reconcile diverging sources — a watch's FIT files, a training
platform, a spreadsheet — and gather the information scattered across them into
one SQLite file: every activity, its provenance and your decisions. Importers
feed it, reports read it, and no service owns the truth. The goal is a
trustworthy record of your training that outlives any app.

## The ideas

- **One canonical record.** FIT files, Intervals.icu, the Garmin Personal API
  and a historical spreadsheet merge into one activity, with the raw source
  records kept beside it. Sources are interchangeable.
- **No automatic priority.** The first source to fill a field keeps it; a
  meaningful disagreement becomes a review item instead of a silent overwrite.
  Manual values outrank everything and survive reimports.
- **Three roles.** Importers write facts, maintenance derives stored values,
  reports compute on read and never write. Delete means durable exclusion,
  never a hard delete.
- **Metrics earn their place.** An idea starts in the lab, passes the gate in
  [`docs/METRICS.md`](docs/METRICS.md), then gets a card, then a renderer — the
  dashboard is always last.
- **Independent by design.** The analysis and the data stay yours even if a
  platform changes its pricing or disappears.

## Live demo

A synthetic athlete, no personal data, rebuilt on every relevant push and
weekly: <https://markuswess.github.io/hobbyjogging/>.

```bash
./demo.sh          # -> build/demo.db and build/site
```

## Quick start

```bash
uv sync
```

`.env` at the repository root holds the credentials and optional paths:

```bash
export HOBBYJOGGING_DB=<your/path/databasefile.db>
export HOBBYJOGGING_FIT_DIR=<your/path/fit-directory>
export INTERVALS_ATHLETE_ID=<your-athlete-id>
export INTERVALS_API_KEY=<your-api-key>
export GARMIN_PERSONAL_API_KEY=<your-personal-api-key>
```

Then run the whole loop — Garmin fetch, Intervals import, FIT scan, review
scan, dashboard:

```bash
./sync.sh
```

## What you do with it

- **Import.** FIT files, Intervals.icu, the Garmin API and the spreadsheet;
  `sync.sh` keeps them current.
- **Review.** Conflicts and odd data land in a queue; the interactive walk
  fixes, resolves or excludes them.
- **Look.** A static dashboard, plus the Markdown reports and charts behind
  it.

Importing and reviewing are documented in
[`hobbyjogging-import`](packages/hobbyjogging-import/README.md), reporting in
[`hobbyjogging-reports`](packages/hobbyjogging-reports/README.md).

Peek into the database directly with `./db.sh` — a SQLite shell with headers
and columns enabled.

## Layout

- `hobbyjogging-core` — canonical model, schema and migrations, sport
  vocabulary, `TrainingWriter` and `TrainingRepository`.
- `hobbyjogging-import` — FIT, Intervals.icu, Garmin and spreadsheet importers,
  the review queue and triage.
- `hobbyjogging-maintenance` — the schema-evolution runner and registered
  backfills/recomputes.
- `hobbyjogging-reports` — analysis, Markdown reports, charts, the dashboard.

`docs/ARCHITECTURE.md` holds the design and the rules,
`docs/SOURCE_NOTES.md` the source-specific field quirks, `docs/METRICS.md` the
metric cards, and `docs/AGENTS.md` the working conventions. Experiments run
through `./lab.sh` and the scripts in `experiments/`.

## Tests

```bash
for p in core import maintenance reports; do
  (cd packages/hobbyjogging-$p/tests && uv run python -m unittest discover -q)
done
```
