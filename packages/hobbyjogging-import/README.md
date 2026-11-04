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
matches are reported rather than merged. Laps are stored per activity,
tentatively merged by source.

## Source precedence

There is no automatic per-source priority. For every field, the source that
wrote it keeps ownership; a later source may refresh its own fields, and a
field nobody has written yet is simply filled. When two sources report a
measurably different value for the same field, nothing is overwritten: the
disagreement is recorded as a `field_conflict` review item and the human
decides (see below). Values that agree within tolerance (about 1%, with small
absolute floors) are not conflicts. Manual edits always outrank every source
and survive reimports.

Conflict-tracked fields are `duration_s`, `elapsed_s`, `distance_m`, `avg_hr`,
`started_at_utc`, `local_date`, `tz_offset_min`, `sport`, and
`training_load`. Subjective fields (`name`, `description`, `feel`, `rpe`, ...)
keep their current owner silently — two devices naming the same run
differently is not worth a review item.

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
implied pace outside a plausible per-sport window), persists ambiguous
matches with their candidate lists, and records cross-source field
disagreements (`field_conflict`) without touching the stored value. Detection
is idempotent by fingerprint: reimporting never duplicates items and never
reopens resolved ones. A changed conflict supersedes its older open item.

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

### Interactive triage

`review triage` walks the open queue one item at a time. Every decision is
written to the database immediately; quitting (or Ctrl-C) prints a summary.

```
#10 warn field_conflict/open  2026-03-14  Gumpoldskirchen Running
  (v) pick value  (i)nspect  (o)pen  (c)opy URL  (e)nter value
  (d)elete  (r)esolve  (x)ignore  (n)ote  (s)kip  (h)elp  (q)uit > _
```

- `(i)` shows the full item: activity values, all linked source records with
  raw paths, and the item context.
- `(v)` appears on `field_conflict` items and shows the competing values, e.g.
  `1) fit: 56:55` vs `2) intervals: 17:35`. Whichever value you pick is
  written as a manual value, so the decision takes ownership of the field and
  later reimports cannot re-open the same conflict. The other conflict items
  for that activity stay in the queue.
- `(o)` opens the Intervals activity (`https://intervals.icu/activities/<id>`)
  in a browser; `(c)` copies the URL via `wl-copy`/`xclip`/`xsel` and echoes
  it. Items linked only to FIT say "no Intervals activity".
- `(e)` manually fixes one value. The field prompt suggests the rule's field
  (`zero_duration` → duration, `zero_distance` → distance, `implied_pace` →
  sport); values parse as `46:20`, `1:02:03`, or seconds / `8.2km`, `8200m`,
  or plain km. The item is resolved, the quality rules re-run, and the fair
  verdict ("quality: ok" or what still stands) is printed. Manual values
  outrank every import source and survive reimports.
- `(d)` durably excludes (soft-deletes) the activity and its linked source
  records: hidden from reports, skipped by reimports, review items resolved.
  `review restore <activity-id>` undoes it.
- `(r)`/`(x)` resolve or ignore; `(n)` attaches a note to the next
  close action.
- Ambiguous matches list numbered candidates: `1-9` links the record to that
  canonical activity (then re-run its importer), `(e)` asks you to link first.

The non-interactive twin is `review edit <activity-id> --duration 46:20
--distance 8.2km --sport trail_running [--item <id>] [--note]`.

Reports exclude activities with open review items by default and print an
"excluded (import review)" note; `--include-review` shows them. Excluded
(soft-deleted) activities never appear.
