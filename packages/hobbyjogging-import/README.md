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

Garmin's current VO2max is read from undocumented activity message 140, field
7 (`raw * 3.5 / 65536`), and stored as `vo2max_garmin` at full precision.
`fit --inspect` prints it, and the import summary reports how many activities
carried a Garmin value. Runalyze's own estimate will be stored separately as
`vo2max_runalyze`; the two are never merged or treated as a conflict.

## Garmin Personal API

Create a Personal API key on
[Garmin Connect](https://connect.garmin.com/app/settings/personalApiToken)
(valid 30/90/180/365 days) and put it in `.env`:

```bash
export GARMIN_PERSONAL_API_KEY=<your-personal-api-key>
```

`GARMIN_API_KEY` is accepted as a fallback. Each run exchanges the key for a
24 h bearer token with no refresh token; the token is cached at
`~/.config/garmin/connect-personal-api-bearer-token.json` (the same file
Garmin's official Python client uses) and re-obtained automatically on 401.

Fetch missing activity FITs for the last 30 days:

```bash
uv run --env-file .env hobbyjogging-import garmin fetch
```

Or for an explicit range:

```bash
uv run --env-file .env hobbyjogging-import garmin fetch \
  --since 2026-01-01 --to 2026-06-30
```

Useful options:

- `--days N` — default range length when only `--to` is given (default 30).
- `--fit-dir PATH` — destination directory (default
  `HOBBYJOGGING_FIT_DIR/garmin`).
- `--limit N` — download at most N new activities.
- `--force` — re-download activity ids already in the manifest.
- `--dry-run` — list what would be fetched without writing.

Each downloaded ZIP contains one `*_ACTIVITY.fit`; it is extracted atomically
to `<fit-dir>/<activity_id>.fit`. A fetch manifest is kept in `source_records`
(`source = "garmin"`, `record_type = "activity-file"`, `external_id =
<activity_id>`), so known ids are skipped without assuming anything about the
archive filenames. Then run the normal importer:

```bash
uv run --env-file .env hobbyjogging-import fit --recursive
```

The Personal API activity file is currently byte-identical to the file in a
GDPR archive export (verified on four activities in November 2026). Garmin's
JSON activity summary exposes `vO2MaxValue` but leaves it null; the FIT still
carries message 140, so the FIT is the VO2max source. The separate type-44
`max_met_data` files are only present in GDPR exports and are not needed.

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

Planned workouts are Intervals calendar events. They are fetched from the
activity start through `max(--to, today + --plan-days)`, while activities and
wellness stop at `--to`/today. The default horizon is 182 days, so the daily
report can show tomorrow's planned session. Event source records are keyed by
the Intervals event id, so extending the horizon is idempotent.

Useful options:

- `--plan-days N` — fetch planned events N days ahead (default 182; `0`
  disables the future horizon).
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
  (v) pick value  (i)nspect  (t)rust Intervals  (o)pen
  (ci) Intervals  (cg) Garmin  (e)nter value  (d)elete  (r)esolve
  (x)ignore  (n)ote  (s)kip  (h)elp  (q)uit > _
```

- `(i)` shows the full item: activity values, all linked source records with
  raw paths, and the item context.
- `(v)` appears on `field_conflict` items and shows the competing values, e.g.
  `1) fit: 56:55` vs `2) intervals: 17:35`. Whichever value you pick is
  written as a manual value, so the decision takes ownership of the field and
  later reimports cannot re-open the same conflict. The other conflict items
  for that activity stay in the queue.
- `(t)` force re-imports the linked Intervals activity (one activity, not the
  whole range) and lets Intervals take ownership of every non-manual field it
  provides. Manual fields are kept. Open `field_conflict` items on fields
  Intervals now owns are resolved, the quality rules re-run, and the changed
  fields are printed. This differs from `(v)`, which applies a single chosen
  value as a manual override.
- `(o)` opens every available activity link in the browser. `(ci)` copies
  the Intervals URL (`https://intervals.icu/activities/<id>`); `(cg)` copies
  the Garmin Connect URL
  (`https://connect.garmin.com/app/activity/<id>`). Both copy actions use
  `wl-copy`/`xclip`/`xsel` and echo the URL. The Garmin link is resolved from
  the `garmin fetch` manifest by file path or, for archive-imported
  activities, by matching the manifest's `beginTimestamp` to the canonical
  start; items without a manifest say "no Garmin activity linked".
  `review show` prints the same links.
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
