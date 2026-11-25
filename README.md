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

Requirements: Linux or macOS, `git`, Python 3.12+ (or [`uv`](https://docs.astral.sh/uv/), which installs it).
Nothing else is installed globally.

Prove the install before connecting any account — this builds a synthetic
athlete and a complete static dashboard, and reads no personal data:

```bash
git clone <this-repo> hobbyjogging
cd hobbyjogging
uv sync
./demo.sh          # -> build/demo.db and build/site
```

Then point it at your own data:

```bash
cp .env.example .env          # paths and credentials; every entry is optional
$EDITOR sources.toml          # which sources are enabled; create/review/ignore
./init.sh                     # create and migrate the database
./doctor.sh                   # what is missing, and the next command
./sync.sh                     # fetch, derive, maintain, scan, render
```

`sources.toml` is the only switch for which sources run; a credential you do
not have is skipped with a warning, never a failed sync. `doctor` probes only
the sources you enabled.

The FIT files come from a Garmin GDPR export copied into
`$HOBBYJOGGING_FIT_DIR`, or from `uv run --env-file .env hobbyjogging-import
garmin fetch` (Garmin Personal API). A Strava bulk export is dropped as
`export_*.zip` into `$HOBBYJOGGING_STRAVA_DIR` (default `data/strava`); the
download stays manual. Runalyze, Intervals.icu and Garmin are fetched by
`./sync.sh` when their credentials are present.

`./dashboard.sh` regenerates and opens the dashboard; `./db.sh` opens a SQLite
shell with headers and columns enabled.

## What you do with it

- **Import.** `./sync.sh` fetches Garmin, Intervals.icu, the FIT archive,
  Runalyze and the Strava export, then the offline derivations, maintenance
  recomputes, review scan and dashboard.
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
someone else** (done — install and configure on a fresh machine), **trustworthy
data** (current: extract, audit, correct through the CLI) and **durable and
more reach** (homelab, more sources, streams, the localhost write UI). The
phase table and the structural rules are in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); the recurring data pass is
[`docs/DATA_BRUSH.md`](docs/DATA_BRUSH.md); small features and promoted lab
metrics land whenever they are ready.

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
metric cards, `docs/DATA_BRUSH.md` the recurring data pass, and
`docs/AGENTS.md` the working conventions. Experiments run
through `./lab.sh` and the private notebook at `$HOBBYJOGGING_LAB_DIR`.

## Tests

```bash
for p in core import maintenance reports; do
  (cd packages/hobbyjogging-$p/tests && uv run python -m unittest discover -q)
done
```
