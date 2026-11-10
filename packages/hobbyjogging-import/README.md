# hobbyjogging-import

Import and normalize training data from external sources into the canonical
hobbyjogging database. Observed FIT/Intervals field differences (elapsed,
moving, recording time and average HR) are documented in
[../../docs/SOURCE_NOTES.md](../../docs/SOURCE_NOTES.md).

## Sync

Run the incremental sync job:

```bash
uv run --env-file .env hobbyjogging-import sync
```

Default windows:

- activities, wellness, and Garmin: last 30 days (`--days`), or since
  `--since DATE`
- planned events: today through today + `--plan-days` (default 182)

Order is deliberate:

1. Garmin fetch
2. Intervals import (activities, wellness, events; events are reconciled)
3. FIT archive import (recursive, new paths only unless `--full`)
4. quality review scan

Useful options:

- `--no-garmin`, `--no-intervals`, `--no-fit`, `--no-scan` — skip a source.
- `--full` — re-import every FIT file instead of skipping paths already in
  `source_records`.
- `--database PATH` — use a database other than `HOBBYJOGGING_DB`.

Each source is wrapped independently: a failure is reported, the remaining
sources still run, and the command exits with status 1. The final summary
shows the window, per-source counts, and failures.

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

FIT timer time (`total_timer_time`) is stored as `duration_s`. When the file
contains `total_moving_time`, it is stored separately as `moving_s`; the
inspector prints `Timer` and `Moving` lines. Files without the field leave
`moving_s` empty (reports fall back to `duration_s`).

## Historical spreadsheet

Import the hand-maintained OpenDocument training log (`data/laufen.ods`,
gitignored user data):

```bash
hobbyjogging-import sheet data/laufen.ods --sheet Material
hobbyjogging-import sheet data/laufen.ods --sheet Rohdaten
hobbyjogging-import sheet data/laufen.ods --sheet Alternativtraining
hobbyjogging-import sheet --inspect data/laufen.ods
```

Options: `--sheet NAME`, `--timezone` (default `Europe/Vienna`), `--from` /
`--to`, `--limit`, `--dry-run`, and `--database`. Import `Material` first so
the shoe ids referenced by `Rohdaten` resolve.

The reader (`ods.py`) uses only the standard library: it expands repeated
rows/columns, drops LibreOffice's trailing padding, preserves merged-cell
positions as empty, and reads typed values (numbers, percentages, dates,
ISO-duration times, booleans, strings, cached formula results).

### Rohdaten

| Sheet column | Canonical |
|---|---|
| `Datum` | `local_date` |
| `Datum` + `Startzeit` | `started_at_utc` + `tz_offset_min` (Europe/Vienna) |
| `Strecke` | `name` |
| `Distanz in m` | `distance_m` |
| `Zeit` | `duration_s` and `elapsed_s` |
| `d. Hf` | `avg_hr` |
| `Beschreibung` | `description` |
| `Trainigstyp`, `Trainingsgebiet` | `activity_tags` (source `sheet`) |
| `Schuhe` | equipment link (Material id or name) |

`Startzeit` is minute-precision. It is used to match an existing FIT/Intervals
activity temporally; a matched activity keeps its second-precision start time,
so the log does not open a timing review item on every row. Rows without a
start time create a dated activity and are never matched. The raw row (max HR,
ascent, cadence, contact time, oscillation, temperature, meters/beat, map link)
is kept in `source_records.payload_json`.

### Alternativtraining

`Datum` + `Uhrzeit` → date/start, `Zeit` → `duration_s`, `Puls Durchschnitt` →
`avg_hr`, `Beschreibung` → description. `Distanz` is kilometres. `Was` maps
through the core sport aliases (`Kicken` → soccer, `Badminton`/`Padel`/
`Tischtennis` → racket, `Radfahren`/`Lastenrad` → ride, `Mountainbike` →
mtb_ride, `Schwimmen` → swim, `Wandern` → hike, `Laufband` → treadmill_run,
`Kraft` → training, `SUP` → sup); anything else becomes `other`.

### Material

Upserts equipment keyed by the sheet id (`sheet:equipment:<id>`), parses
`Kaufdatum`/`Entsorgungsdatum` (`D.M.YYYY`), and keeps size, price, colour,
mileage, and remarks in `equipment.notes`. Mileage is descriptive; usage is
derived from linked activities.

Activity ids are stable: date + start time + route, with a content-hash suffix
for duplicate keys. Reimports update the same source records and follow the
normal owner/manual/conflict rules; disagreements become `field_conflict`
review items.

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

There is one fixed source rule: `moving_s` and `elapsed_s` are always
Intervals-authoritative. An Intervals value replaces another source's value
silently, and a non-Intervals value never overrides it or creates a review
item. Manual edits still win.

For every other field there is no automatic per-source priority. The source
that wrote it keeps ownership; a later source may refresh its own fields, and
a field nobody has written yet is simply filled (a blank `name`/`description`
counts as unwritten, but an empty incoming value never clears text). When two
sources report a measurably different value for the same field, nothing is
overwritten: the disagreement is recorded as a `field_conflict` review item
and the human decides (see below). Values that agree within tolerance (about
1%, with small absolute floors) are not conflicts; average HR uses a wider
5 bpm floor, since a watch's session average and a stream average
legitimately drift by a few bpm. Manual edits always outrank every source
and survive reimports.

Conflict-tracked fields are `duration_s`, `distance_m`, `avg_hr`,
`started_at_utc`, `local_date`, `tz_offset_min`, `sport`, and
`training_load`. Subjective fields (`name`, `description`, `feel`, `rpe`, ...)
keep their current owner silently — two devices naming the same run
differently is not worth a review item.

### Time and distance semantics

- `duration_s` is **recording/timer time**: FIT `total_timer_time`,
  Intervals `icu_recording_time` (falling back to `moving_time` for old
  payloads). A duration difference that fits inside either source's pause gap
  (`elapsed - duration`) is treated as agreement, not a conflict.
- `elapsed_s` is total elapsed time and `moving_s` is moving time; both are
  Intervals-authoritative on any cross-source disagreement.
- Distance is forced to zero for sports where it is not recorded or not
  meaningful: `treadmill_run`, `virtual_run`, `soccer`, `racket`, `training`,
  `other`, and `workout`. A manual distance still wins. Raw FIT/Intervals
  payloads keep the reported distance; only the canonical value is zeroed.
- The quality rules do not raise `zero_distance` for those sports.

Sports are normalized through `hobbyjogging_core.sports` before writing, so
FIT sub-sports and Intervals types map to the same canonical names (for
example `cycling/gravel_cycling` and `GravelRide` both become `gravel_ride`).
Placeholder sports (`generic`, `other`, `unknown`) never conflict with a
specific sport; a specific value fills the placeholder.

Beyond the fixed Intervals authority for moving and elapsed time, the only
exception to owner-based precedence is an explicit human decision: triage
`(t)` re-imports a single Intervals activity with `force=True`, letting
Intervals take ownership of every non-manual field it provides. Normal imports
never force.

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

Intervals provides recording time (`icu_recording_time`), moving time
(`moving_time`), and elapsed time. They are stored as `duration_s` (recording),
`moving_s` (moving), and `elapsed_s` (elapsed). Planned events only expose
moving time, so their `duration_s` is the planned moving duration and
`training_load` comes from `icu_training_load`.

### Planned event sync

Intervals is authoritative for calendar events. Reconcile the plan without
re-importing activities or wellness:

```bash
uv run --env-file .env hobbyjogging-import events sync
uv run --env-file .env hobbyjogging-import events sync --dry-run
uv run --env-file .env hobbyjogging-import events sync \
  --from 2026-01-01 --to 2027-05-06
```

The default window is today through today + `--plan-days` (182). The sync:

- replaces every event field with the current Intervals value, including
  clearing fields that were removed;
- stores the planned zone distribution (`workout_doc.zoneTimes`) and infers
  `zone_kind` from the dominant step target (`pace`, `hr`, or `power`); a
  workout with no targets falls back to the sport's natural kind
  (run/trail → pace, ride family → power);
- clears an event's zone kind and rows when its workout document disappears;
- soft-excludes events that disappeared from the window;
- revives events that reappear;
- leaves manual and other-source events alone;
- reports fetched/new/updated/unchanged/removed/revived/skipped. A change to
  only the zone distribution counts as `updated`.

Stored payloads can repair zone data for the whole plan without touching the
network. That is a registered backfill in `hobbyjogging-maintenance`:

```bash
uv run --env-file .env hobbyjogging-maintenance run event_zones_v1 --dry-run
uv run --env-file .env hobbyjogging-maintenance run event_zones_v1
```

It reads the saved Intervals event payloads, skips soft-excluded events,
writes only rows that differ, and is idempotent.

The regular `intervals` import runs the same reconciliation over its event
range, so it cannot leave stale plans behind.

## Import review

Import conflicts and questionable activities are recorded as *review items*
in the canonical `review_items` table. Categories are `ambiguous_match`,
`field_conflict`, `quality`, `duplicate`, `manual_flag`, and
`workout_classification`. Every importer
runs a small canonical quality rule set (zero duration, missing distance for
run/ride sports, implied pace outside a plausible per-sport window, and
moving time differing from recording time by more than
`max(10 min, 25% of recording)`), persists ambiguous matches with their
candidate lists, and records cross-source field disagreements
(`field_conflict`) without touching the stored value. Detection is idempotent
by `(category, fingerprint, activity_id)`: reimporting never duplicates items
and never reopens resolved ones. The source record stays on the item for
provenance but is not part of the fingerprint. A changed conflict supersedes
its older open item.

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
- `review scan [--activity <id>] [--dry-run] [--prune]` — run the quality rule
  set over existing activities and record findings; useful for backfilling
  after the rules change. `--prune` also resolves open quality items whose
  rule no longer triggers for the current values (or whose activity is
  excluded); `--dry-run` reports checked/resolved/kept without writing.
- `review prune [--dry-run]` — resolve open field conflicts whose recorded
  values now agree under the current core tolerances. Reimports also resolve
  a field's old conflict automatically when that field agrees again.
- `review causes [--status open|all]` — count field conflicts by classified
  cause, severity, and field. Causes are stored on new items and can be
  backfilled with `review classify [--activity <id>] [--dry-run]`.
- `workout_classification` items come from the maintenance queue sync
  (`hobbyjogging-maintenance run workout_classification_queue`). Triage `(k)`
  resolves one: `1` classifier, `2` sheet, `m` merge, `n` leave unclassified,
  or `3` to type method/target tokens by hand (aliases accepted, unknown
  tokens rejected).
  They are `info`-level and never hide an activity from reports.
- `review resolve --cause <cause> [--dry-run]` — bulk-resolve every open
  conflict with one advisory cause (`elapsed_definition`, `small_difference`,
  `start_offset`, `moving_estimate`). Causes that need a per-activity decision
  (`activity_trimmed`, `hr_sensor_anomaly`, `sport_vocabulary`,
  `distance_estimate`) are rejected; triage them instead.

Conflict causes are advisory:

| cause | meaning | action |
|---|---|---|
| `elapsed_definition` | Garmin elapsed is start-to-save (trailing stop), Intervals is last-record offset | bulk resolve |
| `moving_estimate` | each source's own auto-pause estimate | bulk resolve |
| `small_difference` | at most 5% (or 5 bpm) apart | bulk resolve |
| `start_offset` | start timestamps within a minute | bulk resolve |
| `activity_trimmed` | one upload covers only part of the activity | triage |
| `hr_sensor_anomaly` | implausible max HR (spikes/dropouts) | triage |
| `sport_vocabulary` | the sources map to different sports | triage |
| `distance_estimate` | distance differs beyond 5% without a duration mismatch | triage |
| `duration_estimate` | timer/recording time differs beyond 5% | triage |
| `unknown` | no summary-level explanation | triage |

`review list` and `review triage` accept `--cause <cause>`; the cause and its
note are printed on each conflict item.

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
