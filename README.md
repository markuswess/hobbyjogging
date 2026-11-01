# hobbyjogging

Training data, imports, and reports.

## Packages

- `packages/hobbyjogging-core` — canonical training model, database schema,
  and shared helpers.
- `packages/hobbyjogging-import` — importers for FIT files, Intervals.icu,
  Runalyze, and spreadsheet data.
- `packages/hobbyjogging-reports` — analysis, charts, and Markdown reports.

## Setup

```bash
uv sync
```

Create `.env` at the repository root for Intervals.icu credentials and an
optional database location:

```bash
export HOBBYJOGGING_DB=~/projects/laufen_private/data/db/hobbyjogging.db
export INTERVALS_ATHLETE_ID=<your-athlete-id>
export INTERVALS_API_KEY=<your-api-key>
```

## Import

The canonical database lives at
`data/hobbyjogging.db` by default.

```bash
uv run --env-file .env hobbyjogging-import intervals --days 90
```

## Inspect the database

`db.sh` uses `HOBBYJOGGING_DB` from `.env` and opens the database with
SQLite headers and columns enabled.

```bash
./db.sh
./db.sh ".tables"
./db.sh ".schema activities"
./db.sh "SELECT local_date, sport, name FROM activities ORDER BY local_date DESC LIMIT 10;"
```

## Reports

Reports read the canonical database by default.

```bash
./reports.sh
./reports.sh daily
./reports.sh report --days 90
./reports.sh report --from 2026-01-01 --to 2026-03-31
./reports.sh weekly --source intervals
```

See `packages/hobbyjogging-reports/README.md` for report and taxonomy details.

## Tests

```bash
uv run python -m unittest discover -s packages/hobbyjogging-core/tests -v
uv run python -m unittest discover -s packages/hobbyjogging-import/tests -v
uv run python -m unittest discover -s packages/hobbyjogging-reports/tests -v
```
