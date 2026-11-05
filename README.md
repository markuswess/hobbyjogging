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

Create `.env` at the repository root for Intervals.icu credentials and
optional database and FIT locations:

```bash
export HOBBYJOGGING_DB=<your/path/databasefile.db>
export HOBBYJOGGING_FIT_DIR=<your/path/fit-directory>
export INTERVALS_ATHLETE_ID=<your-athlete-id>
export INTERVALS_API_KEY=<your-api-key>
```

## Import

The canonical database lives at `data/hobbyjogging.db` by default. FIT files
are read from `data/fit` unless `HOBBYJOGGING_FIT_DIR` is set.

Inspect a FIT file without writing to the database:

```bash
uv run --env-file .env hobbyjogging-import fit \
  --inspect data/fit/30285-220489711.fit
```

Import FIT activity files (start with `--dry-run`):

```bash
uv run --env-file .env hobbyjogging-import fit --dry-run
uv run --env-file .env hobbyjogging-import fit
```

Import Intervals.icu data:

```bash
uv run --env-file .env hobbyjogging-import intervals --days 90
```

Import-conflicts and questionable activities land in the review workflow:

```bash
uv run --env-file .env hobbyjogging-import review list
```

The quickest way through the queue is the interactive triage walk:

```bash
uv run --env-file .env hobbyjogging-import review triage
```

Each item can be inspected, opened in a browser (Intervals), fixed by
entering valid values (``46:20``, ``8.2km``), marked resolved/ignored, or
durably excluded (soft delete). When sources disagree on a field, nothing is
overwritten automatically: both values are queued as a ``field_conflict`` and
``(v) pick value`` chooses the one that stands. Manual values outrank every
import source and survive reimports; see `packages/hobbyjogging-import/README.md`
for details, or use the non-interactive twins `review edit`, `review exclude`,
and `review restore`.

Reports exclude flagged activities until they are resolved; add
`--include-review` to see them. Excluded (deleted) activities never appear.

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

Charts use `charts.sh` and print the generated file path:

```bash
./charts.sh
./charts.sh volume --days 90
./charts.sh load --days 180
./charts.sh subt-pace --days 365
```

See `packages/hobbyjogging-reports/README.md` for report and taxonomy details.

## Tests

```bash
uv run python -m unittest discover -s packages/hobbyjogging-core/tests -v
uv run python -m unittest discover -s packages/hobbyjogging-import/tests -v
uv run python -m unittest discover -s packages/hobbyjogging-reports/tests -v
```
