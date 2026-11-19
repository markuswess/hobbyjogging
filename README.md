# hobbyjogging

A personal training database that belongs to you, not to a platform. Its main
job is to reconcile diverging sources — a watch's FIT files, a training
platform, a spreadsheet — and gather the information scattered across them into
one SQLite file: every activity, its provenance and your decisions. Importers
feed it, reports read it, and no service owns the truth. The goal is a
trustworthy record of your training that outlives any app.

## Live demo dashboard 

A synthetic athlete, no personal data, rebuilt on every relevant push and
weekly: <https://markuswess.github.io/hobbyjogging/>.

```bash
./demo.sh          # -> build/demo.db and build/site
```

## The ideas

- **One canonical record.** FIT files, Intervals.icu, the Garmin Personal API,
  Runalyze, a Strava bulk export and a historical spreadsheet merge into one
  activity, with the raw source records kept beside it. Sources are
  interchangeable.
- **No automatic priority.** The first source to fill a field keeps it; a
  ranked exception exists only where one source is a better measurement
  (moving/elapsed time, the device id, Garmin VO2max). A meaningful
  disagreement becomes a review item instead of a silent overwrite. Manual
  values outrank everything and survive reimports.
- **Three roles.** Importers write facts, maintenance derives stored values,
  reports compute on read and never write. Delete means durable exclusion,
  never a hard delete.
- **Metrics earn their place.** An idea starts in the lab, passes the gate in
  [`docs/METRICS.md`](docs/METRICS.md), then gets a card, then a renderer — the
  dashboard is always last.
- **A bench for your own research.** The data and the analysis are yours to
  question: test a metric before trusting it, implement a method from a paper,
  keep what proves out and drop what does not. The lab and the gate exist so an
  experiment never leaks into a report by accident.
- **Independent by design.** Nothing here needs a platform to keep working: the
  data is a local file and the analysis runs on your machine, even if a service
  changes its pricing or disappears.


## Quick start

With no credentials at all, build the synthetic athlete's database and
dashboard — that proves the install before any account is connected:

```bash
uv sync
./demo.sh          # -> build/demo.db and build/site
```

Then point it at your own data. `.env` at the repository root holds the
credentials and optional paths:

```bash
export HOBBYJOGGING_DB=<your/path/databasefile.db>
export HOBBYJOGGING_FIT_DIR=<your/path/fit-directory>
export INTERVALS_ATHLETE_ID=<your-athlete-id>
export INTERVALS_API_KEY=<your-api-key>
export GARMIN_PERSONAL_API_KEY=<your-personal-api-key>
export RUNALYZE_API_KEY=<your-personal-token>
```

`sources.toml` (optional) selects which sources are enabled, what an unmatched
row does (create, review or ignore) and where a social title goes; without it
every source is enabled. Then run the whole loop — Garmin fetch, Intervals
import, FIT scan, review scan, dashboard:

```bash
./sync.sh
```

The FIT files come from `garmin fetch` (Garmin Personal API) or from a Garmin
GDPR export copied into the FIT directory; the historical spreadsheet and the
Strava bulk export are one-off imports.

## What you do with it

- **Import.** FIT files, Intervals.icu, the Garmin API, Runalyze, Strava and
  the historical spreadsheet; `sync.sh` keeps them current.
- **Review.** Conflicts and odd data land in a queue; the interactive walk
  fixes, resolves or excludes them.
- **Look.** A static dashboard, plus the Markdown reports and charts behind
  it.

Importing and reviewing are documented in
[`hobbyjogging-import`](packages/hobbyjogging-import/README.md), reporting in
[`hobbyjogging-reports`](packages/hobbyjogging-reports/README.md).

Peek into the database directly with `./db.sh` — a SQLite shell with headers
and columns enabled.

## Where it is going

Four phases, each with an exit test: **works for me** (done), **works for
someone else** (install and configure on a fresh machine), **trustworthy
data** (extract, audit, correct — CLI first, then a localhost UI) and
**durable and more reach** (homelab, more sources, streams). The phase table
and the structural rules are in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); small features and promoted
lab metrics land whenever they are ready.

## Layout

- `hobbyjogging-core` — canonical model, schema and migrations, sport
  vocabulary, `TrainingWriter` and `TrainingRepository`.
- `hobbyjogging-import` — FIT, Intervals.icu, Garmin, Runalyze, Strava and
  spreadsheet importers, the review queue and triage.
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
