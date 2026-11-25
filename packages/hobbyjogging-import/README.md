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
- Runalyze: since the last successful run minus 14 days
- planned events: today through today + `--plan-days` (default 182)

Order is deliberate:

1. Garmin fetch
2. Intervals import (activities, wellness, events; events are reconciled)
3. FIT archive import (recursive, new paths only unless `--full`)
4. Runalyze enrichment (budgeted; a `429` is a warning, never a failed sync)
5. offline Runalyze derivations: gear, VO2max and race results
6. the newest unimported Strava `export_*.zip`
7. quality review scan

`sync.sh` adds the maintenance recomputes, a second scan and the dashboard, so
it is the daily command:

```bash
./sync.sh
```

A source that is disabled in `sources.toml` or has no credential is skipped
with a warning; only a configured source that fails makes the command exit
non-zero. The summary prints every skip and failure, plus per-phase timing.

Useful options:

- `--no-garmin`, `--no-intervals`, `--no-fit`, `--no-runalyze`, `--no-strava`,
  `--no-derive`, `--no-scan` — skip a step.
- `--strava-dir PATH` — the drop directory for `export_*.zip`
  (default `data/strava`, or `HOBBYJOGGING_STRAVA_DIR`).
- `--full` — re-import every FIT file instead of skipping paths already in
  `source_records`.
- `--database PATH` — use a database other than `HOBBYJOGGING_DB`.

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
mileage, and remarks in `equipment.notes`. These stay provenance text rather
than typed columns: no report or rule consumes them, and the canonical
mileage is derived from linked activities; the sheet's `gesamt km` is only a
legacy total. Usage is derived from linked activities.

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

### Daily wellness

```bash
uv run --env-file .env hobbyjogging-import garmin wellness --days 30
```

One request per day for the daily summary (resting HR, sleep seconds, steps,
floors, SpO2) and one for the HRV summary, plus one weight-range request.
Sleep detail and sleep score are not exposed by the Personal API and stay
empty; the GDPR export remains the fallback. The import is fill-only: it
writes only the fields a stored day leaves NULL, so Intervals stays the owner
where both sources run. `./sync.sh` runs it after the activity fetch, and a
missing feed is a warning, not a failed sync.

## Runalyze

The read-only inventory proves what the personal API exposes before comments,
tags, gear or race results are imported. Set the personal token:

```bash
export RUNALYZE_API_KEY=<your-personal-token>
```

The header is `token: <key>` (not `Authorization: Bearer`, which is for the MCP
server). The API budget is 240 requests per rate-limit window; the response
headers carry the reset time, and the client stops with a clear message when
the budget is exhausted. `RUNALYZE_TOKEN` is accepted as a fallback, and
`RUNALYZE_API_BASE_URL` overrides the default `https://runalyze.com/api/v1`.

```bash
uv run --env-file .env hobbyjogging-import runalyze inventory --dry-run
```

The inventory writes nothing. It probes the known endpoints and prints the
activity-field coverage per year (counts of non-null values). The collection
is `/api/v1/activity` (singular); the API ignores its date filters, so the
client reads all pages and applies `--since`/`--to` locally.

```text
Runalyze inventory (dry run)
Base: https://runalyze.com/api/v1

Endpoints:
  ping             200  (pong)
  activities       200
  equipment        200
  sport            403  (blocked)
  recurring-route  403  (blocked)
  planned-race     403  (blocked)
  device-profile   403  (blocked)
  activity detail  200  (88 fields)
  blocked: sport, recurring-route, planned-race, device-profile (expected; the nested activity payload covers them)

Activities: 2841 (2019-2026)

                                   2019   2020   ...   2026   total
  activities                        227    369   ...    379    2841
  hr_avg                            ...
  vo2max                            ...
```

Options: `--since`/`--to` limit the activity range, `--limit N` caps the
sample, and `--per-page N` sets the page size. The four 403 endpoints are
expected; the nested activity payload carries the route and device name. Tests
use recorded JSON fixtures under `tests/fixtures/runalyze/` and never call the
live API.

### Enrichment (comments and tags)

The enrichment imports the two fields Runalyze holds that the canonical record
has no better source for. Both live in the activity **detail** payload:

- `note` fills `activities.description` **only when it is blank** (Intervals,
  the sheet, and manual edits keep their text);
- `tags` replace Runalyze's own tag set in `activity_tags` (`source='runalyze'`);
  manual tags survive.

```bash
uv run --env-file .env hobbyjogging-import runalyze enrich --dry-run
```

Matching is temporal plus distance (Runalyze exposes no Garmin id). A row the
temporal matcher rejects is checked once more for a **perfect twin**: same day,
duration within 2 s and distance within 10 m, exactly one candidate. That
covers start-time drift without guessing; everything else is never linked.
The exception is a twin that is a **sheet-only duplicate** of a device row —
enriching the duplicate would put tags on a row that should be retired, so that
day goes to review and suggests the device row.

An unresolved row is not discarded: its detail is stored (unlinked) and an
`ambiguous_match` review item lists the same-day candidates. Triage links one
with `(1-N)`, and the stored note and tags are applied on the spot — the
matcher is not re-run, because it would reject the distance again. Runalyze
never writes `name`, timing, or distance. A row that matches nothing follows
the per-source create policy; this athlete keeps Runalyze at `review`, so it
opens a review item instead of creating a duplicate.
`--output PATH` still writes the unresolved rows with their reason and
suggestion.

```text
Runalyze enrich dry run: 9 activities
  processed: 9
  not processed: 0
  matched: 9
  refreshed: 0
  already enriched: 0
  unmatched: 0
  ambiguous: 0
  review items: 0 (0 already)
  comments filled: 0
  comments kept (not blank): 0
  activities tagged: 3 (5 tags)
  detail requests: 9
```

Options: `--since`/`--to`, `--limit N`, `--per-page N`, `--dry-run`,
`--refresh`, `--refresh-before TIMESTAMP`, `--wait`, `--output PATH`,
`--ids 1,2,3`, and `--database PATH`.
`--ids` is the repair path for a detail whose fetch failed (HTTP 5xx): it reads
those activities directly instead of the collection, using the detail's own
date, duration and distance for the match — three requests instead of a full
window. Enrichment is
idempotent and resumable: each detail is stored in `source_records`, and a
re-run skips any activity whose stored detail is already linked to the same
canonical row. After a mid-run 429, the next run continues with the remainder.
`--refresh` re-fetches the stored details (use it to pick up edits made on the
Runalyze side); a fully current run reports `already enriched: N` and
`activities tagged: 0`. The 240-request window means a full history needs
several runs; a stopped run lists `processed`/`not processed` and is marked
`partial`.

The stored payload is a snapshot, so a field Runalyze only starts serving
later stays absent. `--refresh-before TIMESTAMP` re-reads every detail stored
before that moment and nothing newer: a refreshed row gets a fresh
`fetched_at`, so under `--wait` the sweep advances window by window and stops
when none remain. This is how the 2026-11 payload gap was repaired — the
detail endpoint began returning `hr_avg`, `vo2max`, `trimp` and the `fit_*`
fields for FIT-backed activities at 2026-11-17 22:00 UTC, and everything
fetched earlier had been frozen without them:

```bash
uv run --env-file .env hobbyjogging-import runalyze enrich \
  --refresh-before 2026-11-18T09:58:00Z --wait
```

At ~240 requests per hour this takes one window per ~240 rows (~12 h for the
full history); it is resumable, so a restart with the same cutoff continues
where it stopped.

Run the whole history unattended; `--wait` fetches the collection once, sleeps
until each reset, and resumes:

```bash
uv run --env-file .env hobbyjogging-import runalyze enrich --wait \
  --output ~/projects/laufen_private/data/runalyze-unmatched.json
```

It prints a progress line per window (`window: N details, M skipped, K not
processed; sleeping Ns`) and finishes with one summary. At 240 requests per
window, 2,841 activities take roughly a dozen windows, so run it in
`tmux`/`nohup` if the terminal may close. `--wait` cannot be combined with
`--dry-run` or a bare `--refresh` (both defeat the stored-detail resume); use
`--refresh-before` for a sweep.

### Gear

Gear is resolved **offline** from the stored detail payloads — no API request:

```bash
uv run --env-file .env hobbyjogging-import runalyze gear --dry-run
```

Each Runalyze gear record resolves in this order:

1. **Co-occurrence** with the sheet shoes on its matched activities (at least
   3 activities, one sheet item on at least 80% of them). Runalyze only tracks
   gear from 2023 on, so no sheet-linked activity before that carries one and
   the older shoes never match this way.
2. **Name**: exact normalized match against existing `equipment.name` or
   `brand + model`, then the same comparison with a trailing colour/size
   parenthetical removed (`Lunge Fis (dunkelblau)` → `Lunge Fis`). The sheet
   names carry no colour, so this is the bridge for the pre-2023 shoes. If
   several rows share that name, the one whose `acquired_on` equals the
   gear's `date_start` wins; no date match (or still several) stays
   ambiguous.
3. **New row** `runalyze:equipment:<id>`: type from the category (78697 shoe,
   78699 bike, else other), dates and notes from the payload, brand/model empty.

Clothing (category 78698: T-shirt, jacket, gloves, hat, ...) is skipped — it is
kit, not equipment. A split co-occurrence or several name matches opens a
non-hiding `ambiguous_equipment` review item; nothing is guessed. Rows the
importer created for another gear record are never name candidates, so two
Runalyze gear ids stay two items.

For each activity the first shoe/bike item is primary and the rest secondary;
sheet and manual links win, and a matched row is never rewritten. When a row
the importer created earlier now resolves to an existing row (the sheet shoe
whose name matches once the colour is gone), its links move there and the
duplicate row is removed; a row with manual links or another source link is
left alone. Re-runs are idempotent; scope with `--since`/`--to`/`--limit` and
write the ambiguous cases with `--output PATH`.

```text
Runalyze gear: 2823 payloads, 26 gear records
  skipped clothing: 6
  created: 0
  linked existing: 2
  already linked: 22
  reconciled duplicates: 1
  ambiguous: 1
  ambiguous resolved: 0
  review items recorded: 1
  activity links: 491 (442 primary, 49 secondary, 966 already present)
```

### VO2max

Runalyze writes the **second** VO2max owner, offline from the stored details:

```bash
uv run --env-file .env hobbyjogging-import runalyze vo2max --dry-run
```

`vo2max` is Runalyze's *effective* estimate; `vo2max_by_time` and
`vo2max_with_elevation` sit beside it and are not stored. `vo2max_garmin` is
never touched, an activity the import has no Runalyze link for is skipped, and
a re-run reports `unchanged` instead of rewriting. On the real data the
payloads carry **2,225 values (2019-01-22 → 2026-11-16)** after the detail
refresh repaired the stale snapshots; before it they carried 843, all from
2019–2022.

```text
Runalyze VO2max: 2823 payloads, 2225 with a value
  written: 2225
  unchanged: 0
  skipped excluded: 0
```

The reports use these values only as a comparison series; the promoted
effective VO2max estimate is computed from HR and pace in the reports package
(see [`docs/METRICS.md`](../../docs/METRICS.md)).

### Race results

Official race metadata comes from `/api/v1/raceresult`, one row per activity
Runalyze marks as a race:

```bash
uv run --env-file .env hobbyjogging-import runalyze races --dry-run
```

The row carries Runalyze's activity id, which is the stored payload's
`external_id`, so a result is written only where the activity is already
linked — never guessed from a date. Distance is converted from km, placement
and participant counts are copied as-is, `officially_measured` becomes a
boolean, and `priority_level`/`status` are kept verbatim. A manual
`race-result` row is never overwritten, and `--output PATH` lists the results
with no linked activity. `official_ascent`/`official_descent` have no column
and `race_event_id` is Runalyze's own identity, so `event_id` stays empty
(events are Intervals-authoritative).

```text
Runalyze races: 37 race results
  written: 37
  unchanged: 0
  kept manual: 0
  unmatched: 0
```

### Workout types

Runalyze's own activity type is a classification signal when the athlete has
no Intervals sets, name or RPE. The mapping is small and evidence-based:

| Runalyze type | canonical sets |
|---|---|
| `Jogging` / `JOG` | `continuous` + `base` |
| `Long Slow Distance` / `LSD` | `long_run` + `base` |
| `SubThreshold` / `ST` | `intervals` + `subthreshold` |

It is written on create and used by `workout_sets_current` only when the
classifier and the sheet propose nothing; existing sets always win. Audit the
stored types, and see which ones are unmapped, without writing:

```bash
uv run --env-file .env hobbyjogging-import runalyze types
```

An unknown type is listed, never guessed.

## Strava

The bulk export is a ZIP or an extracted directory. It needs no API app,
OAuth token or Strava subscription.

```bash
uv run --env-file .env hobbyjogging-import strava ~/Downloads/export_123456.zip --dry-run
uv run --env-file .env hobbyjogging-import strava ~/Downloads/export_123456.zip
```

Options: `--from` / `--to`, `--distance-unit {km,m}` (default `km`),
`--date-zone {auto,local,utc}` (default `auto`), `--dry-run`, `--database`.

The import reads `activities.csv`, `bikes.csv` and `shoes.csv`; the
`activities/` files are ignored because the FIT archive already covers them.
The 2026 export is wide: `Distance` and `Elapsed Time` appear twice, and the
second `Distance` is always metres (the first is km for runs and rides, metres
for swims); gear lives in `Activity Gear`, not `Gear`. The parser reads by
column index and prefers the metres column, so `--distance-unit` only applies
to a single-column export.

`Activity Date` carries the account's timezone, not necessarily the activity's
local time; this account is UTC. `--date-zone auto` matches each export under
both readings and uses the one that matches more activities (the choice is
printed and recorded in the run); `local` and `utc` force one. Matching then
uses the canonical window or the exact-twin rule. A row that matches nothing
follows the per-source create policy: this athlete keeps Strava at `ignore`, so
it writes nothing and the row is reported.

On the real 2026 export: 2,554 of 2,590 activities matched, 35 unmatched
(mostly other sports — alpine ski, swim, hike — or genuine distance
disagreements) and 1 ambiguous. Gear: 5 bikes, 0 shoes, 3 new equipment rows,
2 linked to sheet rows, 64 activity links.

Social text goes to `activity_social(source='strava')`; the default target is
social only, and a per-source setting may promote it to `name`/`description`.
Gear is matched by exact normalized name; an existing
equipment row is only linked, never rewritten, and an unknown name creates
`strava:gear:<slug>` with the CSV brand/model. A re-run refreshes the same
rows instead of duplicating them.

The API is deferred: creating a Strava app now requires a Strava
subscription, and single-player reads are limited to 100 per 15 minutes and
1,000 per day.

## Sources and policy

`sources.toml` (or `HOBBYJOGGING_SOURCES`) sets `enabled`, `create`
(`create | review | ignore` for Strava and Runalyze), the social text
targets, and the optional capabilities. The file is optional; without it
every source is enabled, creates when nothing matches, and runs every
declared capability.

```bash
uv run --env-file .env hobbyjogging-import sources   # effective policy
uv run --env-file .env hobbyjogging-import settings  # matrix, rules, mapping
./reports.sh settings                                # the same, via reports
```

FIT, Intervals and the sheet always create when nothing matches; use `enabled`
to leave one out. Garmin yields files and the daily wellness feed, not activity
rows. `--create` and `--no-create` override one Strava or Runalyze run.

### Capability selection

Capability is declared by the source profile; this file only selects it. Every
toggle defaults to on:

```toml
[sources.runalyze]
create = "review"
tags = true          # enrich: comments + tags
gear = true
races = true         # race results
vo2max = true
workout_type = true  # Jogging/SubThreshold/LSD -> canonical sets
trimp = true         # training_load fallback

[sources.garmin]
wellness = true      # daily resting HR, HRV, sleep, steps, SpO2, weight
```

A disabled capability skips only its step in `sync`; it never changes field
ownership or the review rules. Unknown keys and non-booleans fail loudly.
`settings` renders the capability matrix, the selection, the record types and
activity fields no enabled source can supply (distinguishing a disabled
source from a disabled capability), and the visible dashboard coverage.
`doctor` warns when the enabled sources cannot provide wellness, load, zones,
social, reps/intervals or race results.

### Device identity

`device_id` is FIT-first. A FIT file's `manufacturer/product/serial_number` is
its identity, and a serial-less FIT upload is not a device. A provider name
may create a serial-less device row when no FIT device matches. It fills
`device_id` only when the activity has no FIT source, and it maps onto the
single FIT device of the same manufacturer and product instead of creating an
alias. Two devices of the same model stay ambiguous and keep the provider id.
App names (`Runalyze`, `Garmin Connect`, `Strava`, `intervals.icu`) are never
devices. `devices.name` is display-only, set once and title-cased; a FIT device
keeps its product-derived label, and a provider never overwrites an existing
name. A provider row that no activity uses is soft-excluded, never deleted.

## Source precedence

Field rules live in `hobbyjogging_core.import_rules`; the writer applies
them. The default is owner-based: the source that wrote a field keeps it, a
later source refreshes only its own fields, and a field nobody has written yet
is simply filled (a blank `name`/`description` counts as unwritten, but an
empty incoming value never clears text). When two sources report a measurably
different value for the same field, nothing is overwritten: the disagreement
is recorded as a `field_conflict` review item and the human decides. Values
that agree within tolerance (about 1%, with small absolute floors) are not
conflicts; average HR uses a wider 5 bpm floor. Manual edits always outrank
every source and survive reimports.

A field may declare a ranked authority where one source is a better
measurement:

- `moving_s` and `elapsed_s`: Intervals, then FIT (the second athlete has no
  Intervals);
- `device_id` and `vo2max_garmin`: FIT, which carries the serial and the
  Garmin estimate.

The authoritative value replaces another source's value silently and never
opens a review item; manual values still win.

Creation is policy-driven: `sources.toml` sets `create`
(`create | review | ignore`) for Strava and Runalyze, while FIT, Intervals and
the sheet always create and are switched with `enabled`. Creation happens only
when there is nothing to review.

Conflict-tracked fields are `duration_s`, `elapsed_s`, `moving_s`,
`distance_m`, `elevation_gain_m`, `elevation_loss_m`, `max_hr`, `avg_hr`,
`started_at_utc`, `local_date`, `tz_offset_min`, `sport`, and
`training_load`. Subjective fields (`name`, `description`, `feel`, `rpe`, ...)
keep their current owner silently — two devices naming the same run
differently is not worth a review item.

### Time and distance semantics

- `duration_s` is **recording/timer time**: FIT `total_timer_time`,
  Intervals `icu_recording_time` (falling back to `moving_time` for old
  payloads). A duration difference that fits inside either source's pause gap
  (`elapsed - duration`) is treated as agreement, not a conflict.
- `elapsed_s` is total elapsed time and `moving_s` is moving time; both have a
  ranked authority (Intervals, then FIT) and never open a conflict item.
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

Beyond the ranked authority, the only exception to owner-based precedence is
an explicit human decision: triage `(t)` re-imports a single Intervals
activity with `force=True`, letting Intervals take ownership of every
non-manual field it provides. Normal imports never force.

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

## Manual thresholds

An Intervals-less athlete enters their own dated thresholds; the automatic
recompute never removes a manual snapshot:

```bash
uv run --env-file .env hobbyjogging-import threshold add \
  --sport run --from 2026-01-01 --max-hr 190 --lthr 170 --threshold-pace 4:30
uv run --env-file .env hobbyjogging-import threshold list --sport run
```

`--threshold-pace` takes minutes per kilometre (`4:30`, `4:30/km`) or a speed
(`3.70mps`). `--from first` anchors the snapshot on the earliest activity of
that sport, so the whole history gets a zone config. After saving, the command
names the effective date and how many earlier activities of that sport stay
unzoned; it never backfills them silently.

`derived_zone_configs_current` builds local HR/pace zone configs and lap zone
times from the snapshot in force on each activity's date; an Intervals config
always wins. When some activities predate the first snapshot, the recompute
prints that count and the first snapshot date, so the gap is visible in the
run summary.

```text
threshold saved: run from 2019-01-22
Zones apply from 2019-01-22; no earlier run activity stays unzoned.
```

## Activity editing

`activity edit <id>` is the direct human write surface. It needs no review
item; every value becomes a manual override through the same functions triage
uses, so a reimport cannot undo it. It edits the activity's own fields
(`name`, `description`, `duration`, `distance`, `sport`, `sub-sport`, `rpe`,
`feel`), the manual tag set (`--tag`, repeatable) and the whole-set workout
classification (`--method`, `--target`), and the manual equipment links
(`--equipment`, repeatable).

```bash
uv run --env-file .env hobbyjogging-import activity edit <id> \
  --name "Long run" --rpe 7 --feel 2 --sub-sport trail \
  --tag "long" --method long_run --target base

# show the append-only history (old value, new value, source, resolved items)
uv run --env-file .env hobbyjogging-import activity edit <id> --history

# see what a change would do without writing it
uv run --env-file .env hobbyjogging-import activity edit <id> \
  --duration 46:20 --dry-run
```

- `--clear <field>` removes the manual value and its ownership, restoring the
  source snapshot or the column default. It accepts the scalar fields and
  `tags`, `methods`, `targets`, `equipment`.
- `--item <review-item-id>` also resolves an explicit review item. It is a
  convenience, not a requirement: a manual edit automatically resolves the
  open `field_conflict` for a touched field and, after a method/target change,
  the open `workout_classification` item. Other fields' items stay open.
- Every change appends one `edit_log` row in the same transaction
  (`old_json`, `new_json`, source and note). `--history` reads it. The log is
  append-only; it is the audit trail a platform would keep, while
  `activity_field_sources` is only the current snapshot.
- With no edit flags the command is interactive: it prompts field by field with
  the current value as the default, and a blank answer keeps it. `-` clears
  the field, and sets accept comma-separated values.
- The quality rules re-run after every scalar edit and print what still stands
  (`quality: ok` or the findings). A set change does not affect the quality
  rules.
- `--dry-run` applies the whole edit, prints it, and rolls the transaction
  back; nothing is written.

## Session metrics

`activity_metrics` stores one nullable row per activity with the session
averages the payloads already carry; per-second streams stay in the FIT
archive. The importers write it, and
`hobbyjogging-maintenance run activity_metrics_v1` backfills the existing rows
from the stored payloads (and re-reads the FIT archive for the older FIT
records). `maintenance audit --fit-sample N` reports the per-source coverage
and the cross-source disagreements.

Units and ownership:

| field | unit | primary source |
|---|---|---|
| `cadence` | steps/min for runs, rpm for rides | FIT, then Intervals/Runalyze/sheet |
| `stride_m` | m | FIT, then Intervals/Runalyze |
| `vertical_oscillation_mm` | mm | FIT, then Intervals/Runalyze/sheet |
| `stance_time_ms` / `stance_time_pct` | ms / % | FIT, then Intervals |
| `stance_balance_pct` | % | FIT, then Intervals/Runalyze |
| `vertical_ratio_pct` | % | FIT, then Intervals/Runalyze/sheet |
| `respiration_bpm` | breaths/min | FIT, then Runalyze |
| `power_w` | W | FIT, then Runalyze |
| `calories_kcal` | kcal | FIT, then Intervals/Runalyze |
| `training_effect` | 0-5 | FIT, then Intervals/Runalyze |
| `gap_mps` | m/s | Intervals, then Runalyze |
| `altitude_avg_m` / `min` / `max` | m | Intervals |

Run cadence is one-leg in FIT, Intervals and Runalyze (86) and steps/min in
the sheet (172), so a run value at or below 120 is doubled. Runalyze's stride
is centimetres, its GAP is km/h, its balance is hundredths of a percent and
its vertical ratio is tenths of a percent; the extractor normalizes all four.
If two sources disagree, the per-field authority above wins; a reimport from
the row's first source cannot undo a higher-authority value.

`fit --inspect FILE` prints the same metrics line the session report uses:

```text
Metrics: cadence 172, stride 1.29 m, VO 94 mm, GCT 239 ms (35 %), balance 48.2 %, VR 7.4 %, respiration 33.7, TE 3.7
```

## Tags and evidence

`hobbyjogging_import.tag_lexicon` is the one table that turns a stored tag into
a meaning: a workout set (`sub threshold` → intervals + subthreshold, `LT1`,
`Longjog`, `Regeneration`, `strides`, `Intervalle`, `Tempolauf`, …), illness
and recovery, a race or trail marker, a rep length (`6'`, `400m`, `1km`), a
sheet area code, context (gear, weather, fatigue, people) or a deliberate
ignore (`schlapp`). The audit's tag table lists every stored tag as mapped or
`unmapped`; an unmapped tag is never guessed. Adding a meaning is one entry in
`TAG_MEANINGS` plus a test. Unmapped place and person tags are expected.

The lexicon feeds the evidence proposals:

- `workout_sets_current` fills an **empty** run classification from a mapped
  tag (`source='tag'`) or an explicit description (`source='comment'`, e.g.
  `5x1000 interval` or `3-6-9-6-3min Intervalle`). A tag wins over a
  description, a classifier/sheet/Runalyze-type proposal wins over both, and a
  manual, sheet, Runalyze-type or imported set is never overwritten. A
  generic note ("easy run") or an ambiguous rep such as `3x15 Liegestütz` is
  not enough.
- `illness_candidates_current` groups illness-tagged days, lets
  `wieder gesund` close a range, and opens a non-hiding `period_candidate`
  item when the range is not covered by a stored illness period. It never
  writes a period; use `period add`.
- `trail_candidates_current` combines session/lap elevation (≥40 m/km),
  `sub_sport` trail/mountain, the `Trail` tag and a supporting route name into
  a non-hiding `consistency` item suggesting `trail_run`; a route name alone is
  not enough. It never changes the sport.

Both recomputes run in `sync.sh` (`--no-classify` also skips them) and close
their items when the underlying evidence disappears or the period/sport is
decided.

## Import review

Import conflicts and questionable activities are recorded as *review items*
in the canonical `review_items` table. Categories are `ambiguous_match`,
`ambiguous_race`, `ambiguous_equipment`, `create_activity`, `consistency`,
`field_conflict`, `period_candidate`, `quality`, `duplicate`, `manual_flag`,
and `workout_classification`. `consistency` and `period_candidate` are
non-hiding suggestions: they never remove an activity from reports. Every importer
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
then re-run the importer over that record so its field values are applied.
Triage `(i)` shows the incoming source row (date, start in local time and
UTC, sport, duration, distance, ascent, heart rate, description) and each
candidate in full (start, duration, distance, pace, name, description,
sources), which is usually enough to pick the right one.

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
- `(a)` appears on `consistency` items and writes the suggested value (for
  example `trail_run`) as a manual sport, resolving the item and re-running
  the quality rules. A `period_candidate` item carries an illness range; add
  it with `period add --kind illness --start ... --end ...` and then resolve
  the item.
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
