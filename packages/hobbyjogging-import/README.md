# hobbyjogging-import

Import and normalize training data from external sources into the canonical
hobbyjogging database.

## FIT files

FIT files are read from `data/fit` by default. Set `HOBBYJOGGING_FIT_DIR` to
use another directory:

```bash
export HOBBYJOGGING_FIT_DIR=~/projects/laufen_private/data/fit
```

Inspect one FIT file without writing to the database:

```bash
uv run --env-file .env hobbyjogging-import fit \
  --inspect data/fit/30285-220489711.fit
```

Add `--json` to print the normalized summary as JSON. The inspector shows the
device, sport mapping, start times, duration, distance, pace, heart rate,
ascent, calories, and laps. A bare filename is resolved under
`HOBBYJOGGING_FIT_DIR`.

Import FIT activity files:

```bash
uv run --env-file .env hobbyjogging-import fit --dry-run
uv run --env-file .env hobbyjogging-import fit
```

Options:

- `paths`: files or directories (default `HOBBYJOGGING_FIT_DIR` or `data/fit`).
- `--recursive`: search directories recursively.
- `--from DATE` / `--to DATE`: filter sessions by local date.
- `--limit N`: process at most N activity files.
- `--dry-run`: report matches, creations, and ambiguity without writing.

Files are prefiltered by `file_id.type == activity` before full parsing. Each
session is matched to a canonical activity by temporal overlap, counted with
`elapsed_s`. Several FIT files may link to one activity; ambiguous one-to-many
matches are reported rather than merged. FIT wins for timing, distance, and
heart-rate fields; Intervals.icu keeps subjective and derived fields; manual
edits always win. Laps are stored per activity, tentatively merged by source.

## Intervals.icu

Set credentials at the repository root:

```bash
export INTERVALS_ATHLETE_ID=<your-athlete-id>
export INTERVALS_API_KEY=<your-api-key>
```

Import the last 90 days:

```bash
uv run --env-file .env hobbyjogging-import intervals --days 90
```

Import an explicit range:

```bash
uv run --env-file .env hobbyjogging-import intervals \
  --from 2026-01-01 --to 2026-03-31
```

Useful options:

- `--no-intervals` — skip per-activity interval downloads.
- `--database PATH` — write to a database other than `HOBBYJOGGING_DB` or
  `data/hobbyjogging.db`.

The importer writes:

- raw Intervals.icu payloads to `source_records`
- canonical activities, wellness days, and events
- activity source links and field provenance
- zone times and structured activity intervals
- one `import_runs` row per import

Re-importing is idempotent: source records are matched by
`(source, record_type, external_id)`, and canonical activities use stable
UUIDs derived from the Intervals.icu activity ID. Manual field overrides are
not overwritten.

## Import review

Import conflicts and questionable activities are recorded as *review items*
in the canonical `review_items` table. Every importer runs a small canonical
quality rule set (zero duration, missing distance for run/ride sports,
implied pace outside a plausible per-sport window) and persists ambiguous
matches with their candidate lists. Detection is idempotent by fingerprint:
reimporting never duplicates items and never reopens resolved ones.

```bash
uv run --env-file .env hobbyjogging-import review list
uv run --env-file .env hobbyjogging-import review list \
  --category ambiguous_match
uv run --env-file .env hobbyjogging-import review show 3
```

Resolving an ambiguous match links the source record to the chosen activity;
then re-run the importer over that record so its field values are applied:

```bash
uv run --env-file .env hobbyjogging-import review resolve 3 --activity <id>

# pick up the field values of the resolved record
uv run --env-file .env hobbyjogging-import fit <file>   # or intervals --from ...
```

Other commands:

- `review ignore <id> [--note]` — keep the item but stop surfacing it.
- `review flag <activity-id> [--category quality|duplicate|manual_flag]
  [--severity] [--note]` — manually flag an activity.
- `review scan [--activity <id>] [--dry-run]` — run the quality rule set
  over existing activities and record findings; useful for backfilling after
  the rules change.

Reports exclude activities with open review items by default and print an
"excluded (import review)" note; `--include-review` shows them.
