# Architecture

How hobbyjogging is put together and where it is heading. For the work queue
see [NEXT_UP.md](NEXT_UP.md); for working conventions see
[AGENTS.md](AGENTS.md).

## Goals

- One canonical training database that is the single ground truth, independent
  of any one device or service.
- Data from several sources merged into one activity, with provenance kept and
  conflicts surfaced instead of silently resolved.
- Human decisions (manual values, exclusions) that survive reimports.
- Reports and dashboards that read the canonical data only and are cheap to
  render anywhere: terminal, laptop browser, phone, wall screen.
- A deterministic data bundle for LLM coaching conversations.
- A personal research bench: implement a published method or an idea of your
  own, test it against the full history, and keep only what proves out — so the
  analysis evolves independently of the established platforms.
- Independence from hardware manufacturers and platforms for training
  planning and analysis, while still using the features they offer.

## Phases

The work is organised in three phases. The numbered queue in
[NEXT_UP.md](NEXT_UP.md) owns the items; the phases are direction and
completion criteria, not a second task list.

| phase | scope | complete when |
|---|---|---|
| **1. Complete the pipeline** | canonical DB, review, every source imported (FIT archive, Intervals.icu, Garmin Personal API, Runalyze, Strava), reports, dashboard and race pages | all imports are in and the reports/dashboard answer the daily questions |
| **2. Deepen the data** | more data and backfills (session averages, historical refurbishment, routes, extra metrics), manual editing and a rebuildable canonical layer, per-athlete import policy, stronger analysis and lab work, and a second-athlete portability test | the canonical record is as complete as the sources allow, the lab has proved the metrics worth keeping, and a second athlete can run the pipeline without code changes |
| **3. Beyond the database** | web editing interface, homelab migration, platform independence, LLM coaching, detailed per-second streams, vague ideas | deliberately dormant until phases 1–2 are complete |

Phase 1 is current: Runalyze and the Strava CSV import are landed, the
reports/dashboard are in daily use, and the optional Strava API is the only
source left. Phase 2 starts once phase 1 is complete; the data-depth and
refurbishment items are already queued. Phase 3 is deliberately dormant.

## Where the data comes from

The canonical database consolidates data that used to live in several places:

- **FIT files** — raw recordings from the devices, plus the Garmin Connect
  archive.
- **A spreadsheet** — the legacy log (2009–2021): activities, shoes, tags.
- **Runalyze** — tags, comments, equipment, and its VO2max estimate.
- **Intervals.icu** — intervals, names, zones, and the planned calendar.
- **Strava** — CSV bulk export: titles, social descriptions and gear; not used
  for training data. The API is optional and deferred.

Each source keeps its raw payload in `source_records`, so canonical values can
always be re-derived or audited.

### Import rules

`hobbyjogging_core.import_rules` owns the shared rules: field ownership,
conflict tolerances, manual-edit permissions and one `SourceProfile` per
source. The default is owner-based; a field may declare a ranked authority
where one source is a better measurement. There is no global source order.

`hobbyjogging_import.matching` owns the shared ladder: existing link →
temporal overlap (the profile may allow a contained FIT segment) → distance
agreement → same-day exact twin → `ambiguous_match` review → create only when
the policy allows it and there is nothing to review. A source that only knows
local wall time (Strava CSV) matches against the canonical window reconstructed
from `started_at_utc + tz_offset_min`.

Every source that yields activity rows may create. What an unmatched row does
is policy, not capability: per source `create | review | ignore` in
`sources.toml`, defaulting to create. A row with a rejected candidate becomes a
review item instead of a creation, so the default cannot manufacture
duplicates. The same file sets the text targets: a title or description stays
in `activity_social` (default) or is promoted to `activities.name`/
`description`; a promoted title feeds the classifier, a description does not.

Each adapter declares its payload→field mapping (`FIELD_MAP`), so the derive
check, the rebuild and the settings view read one table.

A new source is a profile plus a fetch/normalize adapter. It should not add a
branch to the writer, the matcher or the quality rules.

## Principles

1. **Three roles, one direction.** Importers write *received facts* (raw
   payloads and the fields they report). Maintenance writes *derived stored
   values* (one-time backfills and recurring recomputes). Reports compute
   *cheap metrics on read* and never mutate the database. No layer formats
   another layer's output.
2. **Placement follows cost.** A value that is cheap to derive stays in the
   report layer. A value that is expensive, or needs cross-row context
   (ownership, classification, review state), is stored and maintained — with
   manual values outranking derived ones.
3. **The database is the truth; importers are replaceable.** Reimporting is
   idempotent, manual values outrank every source, and cross-source
   disagreement becomes a review item rather than a priority-rule outcome.
4. **Delete is exclusion.** Rows are retained for audit; nothing is hard
   deleted, so a reimport cannot resurrect deleted data.
5. **Compute → render.** Metrics live in analysis code and return typed data.
   Markdown, HTML, charts, and JSON are renderers over the same values.
6. **Source-independent reads.** Reports consume the canonical model through a
   `DataSource`, never a specific API or file format.
7. **Reproducible output.** Same database and date range produce the same
   report; generation timestamps are explicit, not hidden.

### Inputs and projections

Principle 1 splits stored data into two kinds:

- **Inputs** are never rebuilt: source payloads, ownership pointers, manual
  field edits, links, exclusions, review answers and entity rows.
- **Projections** are rebuildable: canonical activity scalar fields (by
  `recompute_canonical`), classification (by its own recompute) and quality
  flags.

`recompute_canonical` rebuilds the projections from inputs without re-deciding
ownership (a no-op on the current DB); `verify_canonical` diffs the same
derivation without writing. On the real DB every owned activity field (68,001
across 4,143 activities) matched its input. Ownership is an **input** (a
recorded decision), not a projection: the first owner keeps a field, per-field
ranked authority resolves the declared exceptions, and a meaningful
disagreement becomes a review item. There is no global source order and no
virtual read path.

## Topology

Development happens on a laptop; the durable deployment target is an
always-on homelab host. The database lives on exactly one machine and clients
never hold a copy.

```text
   FIT archive      Garmin Personal API     Intervals.icu API     Runalyze API
        |                   |                     |                   |
        |            garmin fetch (FITs)          |                   |
        |                   |                     |                   |
        +-------------------+---------------------+-------------------+
                            |
                     import / sync job            manual input & computed data
                            |                               |
                            +-------------------------------+
                            |
                  canonical SQLite DB  (source of truth)
                            |
                 analysis + view models
                            |
                    markdown reports and charts
                     /                     \
            .md and PNG export       static HTML
                (terminal)        (dashboard: plotly + reports)
                    |                       |
             llm coaching             Caddy / nginx
                                           |
                                laptop browser · phone · wall screens
```

- **Homelab host**: database on local disk (never NFS/SMB), importers, review
  CLI, dashboard generator, static web server.
- **FIT archive**: synced from the laptop to the homelab (Syncthing or rsync).
  New activities are also fetched directly from the Garmin Personal API.
- **Runalyze**: synced from the Runalyze API (enrichment only).
- **Intervals.icu**: synced from the API (activities, wellness, planned
  events).
- **Clients**: browsers only. No database credentials, no JavaScript
  framework, no write access.
- **Access**: private network (Tailscale/WireGuard) or basic auth at the
  reverse proxy. Health data is not exposed publicly.

## Packages

The repo is a uv workspace with four packages.

### `hobbyjogging-core`

Canonical model, schema, and read/write access.

- `model.py` — `Activity`, `Lap`, `Interval`, `WellnessDay`, `Event`,
  `Equipment`, zone models; activities carry both VO2max values and tags.
- `sports.py` — canonical sport names, labels, groups, and the shared alias
  table for FIT/Intervals/manual entry.
- `classify.py` — the workout-category heuristic (quality/non-quality,
  intervals/fartlek/longrun/race/tempo, subT rep length), `category_for_sets`
  (the stored sets to display kind inverse), plus `work_intervals` and the
  rep-length buckets. Classified activities take their category from the
  stored sets; the heuristic runs only for unclassified ones, and the
  classification tasks call it with `use_stored=False`.
- `db/schema.py`, `db/migrations.py` — SQL schema and forward-only migrations
  (`SCHEMA_VERSION`, currently 23).
- `db/writer.py` — `TrainingWriter`: import runs, source records, activity
  upserts, field provenance, manual edits, exclusions, review items, laps,
  intervals, zone times, tags.
- `db/repository.py` — `TrainingRepository`: read queries over the canonical
  model.
- `datasource.py` — the `DataSource` protocol every report consumer depends
  on: activities, wellness, events, intervals, equipment, and the review
  queue (`review_items`, read-only).
- `db/connection.py` — database path resolution and connection setup.

Core owns the rules that must not drift between packages: field ownership,
conflict detection, sport normalization, exclusion semantics, review-item
fingerprints.

### `hobbyjogging-import`

Source ingestion and the review queue.

- `fit.py` — FIT parsing and normalization (the only module that knows raw FIT
  field names).
- `fit_import.py` — file discovery, matching, activity/lap persistence.
- `garmin.py` — Garmin Personal API client: key → bearer token, activity list,
  original FIT download into the archive, fetch manifest.
- `client.py`, `intervals.py` — Intervals.icu API access and import, including
  the planned-event horizon.
- `links.py` — Intervals/Garmin activity URL resolution for triage and
  `review show`.
- `runalyze.py` — Runalyze enrichment import (comments, tags, gear, race
  results, VO2max, wellness); never writes timing or distance.
- `matching.py` — temporal activity matching across sources.
- `quality.py` — canonical quality rules, field-conflict recording, review
  fingerprints, quality refresh after edits.
- `values.py` — parsers/formatters for manual entry (`46:20`, `8.2km`).
- `editing.py` — shared manual-edit application used by the CLI and triage.
- `triage.py` — interactive review walk.
- `review_cli.py`, `cli.py` — `hobbyjogging-import` entry point.

### `hobbyjogging-reports`

Analysis, views, and rendering.

- `sources/` — the `DataSource` implementation: the canonical database. Raw
  payloads stay in `source_records`, so reports need no live API client.
- `analysis/` (`common`, `averages`, `load`, `zones`, `subt`, `planned`,
  `recovery`), `series.py` — pure functions over canonical activities,
  intervals, and wellness; derived metrics such as load, zone distribution,
  pace/HR trends, recovery.
- `model.py` — typed view models and analysis result types.
- `classify.py` — category aggregation for display (`CategoryStat`,
  `category_breakdown`). The heuristic itself lives in
  `hobbyjogging_core.classify`.
- `daily.py`, `period_report.py`, `subt_report.py`, `overview.py`,
  `recovery_report.py` — one Markdown report per file; `report_commands.py`
  dispatches them.
- `sessions.py`, `recent.py`, `debug.py` — session detail, shared lookback
  search, and a dump of the stored raw payloads.
- `activity_list.py` — the activities table (selection, columns, rendering).
- `summary.py` — period totals, quality-session lists, recovery averages.
- `charts.py`, `chart_commands.py` — plotly figures over prepared series.
- `format.py`, `mdpretty.py` — human formatting for the terminal.
- `commands.py`, `cli.py`, `command_support.py`, `__main__.py` — command
  registry, shared CLI helpers, and entry point.

The long-term dashboard is a new renderer in this package, not a new analytics
implementation.

### `hobbyjogging-maintenance`

Schema evolution and registered data work. It depends on core and the
importers, never on the renderer, and is the composition root for one-off data
changes.

- `registry.py` — task ids, kinds (`backfill` / `recompute`), registration.
- `context.py` — `Scope` and `TaskContext` (connection, lazy repository and
  writer, counts, notes, output file).
- `runner.py` — one transaction per run, dry run = run then roll back,
  bookkeeping in `maintenance_runs`.
- `store.py` — reads and writes for `data_migrations` and `maintenance_runs`.
- `workouts.py` — classifier/sheet proposals shared by the classification
  tasks.
- `backfills/event_race_method_v1.py` — `event_race_method_v1`.
- `backfills/event_zones.py` — `event_zones_v1`.
- `backfills/remove_tempo_method_v1.py` — `remove_tempo_method_v1`.
- `backfills/drop_empty_intervals_v1.py` — `drop_empty_intervals_v1`.
- `backfills/workout_classification.py` — `workout_classification_v1`.
- `recompute/workout_sets_current.py` — `workout_sets_current`.
- `recompute/workout_classification_queue.py` —
  `workout_classification_queue`.
- `cli.py` — `list`, `status`, `run`.

## Canonical data model

SQLite, forward-only migrations. Schema version 23.

- `activities` — canonical values: dates, sport, name, description, recording
  time (`duration_s`), elapsed time, moving time (`moving_s`), distance,
  elevation gain/loss (v12), heart rate (average and maximum, v12), training
  load, subjective fields, both VO2max values (`vo2max_garmin`,
  `vo2max_runalyze`), exclusion timestamp.
- `source_records` — raw imported payloads with checksums and provenance
  (`source`, `record_type`, `external_id`, `raw_path`, `payload_json`,
  exclusion timestamp).
- `activity_sources` — links between canonical activities and source records,
  including match method, confidence, and primary flag.
- `activity_field_sources` — per-field provenance: which source wrote a value,
  the value it wrote, and whether it is a manual override.
- `routes` (v20) + `activity_routes` — a named loop or course and the
  activities that covered it. Route identity is source-scoped: the sheet keys
  by `Streckennummer`, falling back to the name's number when unambiguous and
  then to the name itself; Runalyze's `recurring_route` id is a different
  identity and never merges automatically. A run can cover several routes, so
  the link is a table.
- `event_activity_links` (v21) — a planned race and the activity that ran it.
  `race_links_current` matches date + sport + distance within 5%; an
  ambiguous match opens an `ambiguous_race` review item instead of guessing.
  A linked race, or a non-excluded official `race_results` row, makes the
  activity carry the `race` method under `race_link`; a manual link or a
  manual method set wins, and the method is dropped when neither evidence
  remains.
- `training_periods` (v18) — dated spans: seasons, plans, illness, travel,
  recovery. Intervals supplies the season starts (`SEASON_START`) and the
  sickness/travel notes (`SICK`/`NOTE`); a season ends the day before the next
  one and the latest stays open. A sickness or note keeps the source's
  inclusive `end_date_local` (falling back to the start), so the range is real
  and the recompute never invents an end. A manual row is never removed by the
  recompute.
- `devices` (v17) — the recording devices: manufacturer, product, serial,
  name and active dates. One recorder per activity, so `activities.device_id`
  is a single nullable foreign key; the serial is what a text column could not
  give. FIT owns the field (it carries the serial) and a manual assignment
  wins.
- `race_results` (v16) — official race metadata, one row per activity:
  official distance and time, `officially_measured`, places and participants
  by total/gender/age class, `priority_level`, `status` (a PB counts only
  `completed`), notes and source. Kept apart from the measured GPS values, and
  a manual row is never overwritten by an import.
- `athlete_thresholds` (v14/v15) — dated snapshots of the athlete's
  threshold settings, **per sport**: `max_hr`, `lthr`, `threshold_pace_mps`.
  Intervals stamps them on every activity; a missing value carries forward and
  one snapshot per sport and date is kept.
- `zone_configs` (filled by the import) — one row per distinct boundary set,
  with `activities.hr_zone_config_id` / `pace_zone_config_id` pointing at the
  era's config, so "Z3" means the same thing across years.
- `activity_weather` (v13) — one row per activity: temperature, feels-like,
  humidity, wind speed/degree/gust, wind chill, heat index, pressure, UV,
  clouds, condition and a night flag, in metric units. The first source owns
  the row; a later source only fills the fields it left empty.
- `activity_laps`, `activity_intervals`, `activity_zone_times` — detail data
  attached to activities, tagged by source record. Laps are device splits
  (auto-lap or manual); intervals are Intervals.icu's typed reps (`WORK` /
  `RECOVERY`, with group ids). They are complementary, not duplicates: the
  session report prints one raw segment table — intervals when there is more
  than one, otherwise laps when there is more than one — and the subT
  work-reps section is derived separately.
- `activity_tags` (v5) — activity labels with their source. The sheet writes
  its training-area code (`Trainingsgebiet`); the classification code is not a
  tag, because the method/target sets already carry it.
- `activity_workout_methods`, `activity_workout_targets` (v9) — set-based
  workout classification for completed activities (a session may carry
  several methods and targets).
- `event_workout_methods`, `event_workout_targets` (v9) — the same sets for
  planned events.
- `wellness_days` — one row per day: HRV, resting HR and sleep seconds, plus
  (v19) weight, sleep score and quality, SpO2, steps, floors climbed and
  Intervals' own CTL/ATL. Readiness, stress, respiration, mood, soreness and
  fatigue are present as payload keys but never populated, so they have no
  column.
- `equipment`, `activity_equipment`,
  `equipment_source_links`, `zone_configs` — supporting canonical data.
- `events` — planned workouts and races: local date, type, description,
  planned moving duration (`duration_s`), distance, training load, planned
  zone kind (`zone_kind`), and an exclusion timestamp. Intervals is
  authoritative for events; removed events are soft-excluded rather than
  deleted.
- `event_zone_times` — the planned zone distribution for an event
  (`zone_label`, `zone_index`, `seconds`), e.g. `Z1`–`Z7` or `SS`.
- `import_runs` — one row per import with parameters and outcome.
- `fit_scan_files` (v11) — the FIT archive scan manifest: path, size,
  modification time and the scan's verdict, so a routine scan reads only new
  or changed files whether or not they became an activity.
- `data_migrations` (v10) — which registered backfills have been applied.
- `maintenance_runs` (v10) — one row per maintenance task run, dry or real.
- `review_items` — the review queue: category, severity, detail, context,
  fingerprint, status, resolution note, activity/source links.

Workout classification is set-based and orthogonal:

- **Methods** — `continuous`, `intervals`, `fartlek`, `long_run`,
  `progression`, `race`, `strides`, `other`. A tempo run is `continuous` with a
  `threshold` target; the retired `tempo` token normalizes to `continuous`.
  `fartlek` means *never structured*: `intervals` means reps were intended,
  even when the device data is missing.
- **Targets** — `base`, `lt1`, `subthreshold`, `threshold`, `vo2max`, `speed`,
  `marathon`, `recovery`, `other`.
- **Quality** is derived: any quality method (`intervals`, `fartlek`,
  `long_run`, `progression`, `race`) or target (`lt1`, `subthreshold`,
  `threshold`,
  `vo2max`, `speed`, `marathon`) makes a session quality;
  base/recovery only is non-quality; no values is unknown. Strides never make
  a session quality by themselves.

Text fields have fixed roles:

- `name` — the session name ("easy", "3x9' subT long"), owned by the source
  that records the training intent. An auto-generated platform title
  ("Vienna Running") is a fallback, never a preferred value.
- `description` — the training notes: how the session went, the feeling, the
  intervals and paces. Intervals and the historical sheet fill it, Runalyze may
  only fill a blank, and a manual edit outranks both.
- `activity_social` (planned) — the social text: the pun title and its
  continuation, one row per source (`source` is data, so any social import can
  map into it). It never enters `description` and never reaches `classify()`.

There is one training-notes text per activity, not a list; a notes table is
added only if per-note timestamps ever become a need.

Two invariants are enforced by the writer:

- A manual field is an input row in `activity_manual_fields` (a value or an
  owner patch); a manual value is never overwritten by an import, and a manual
  owner keeps its chosen source.
- An excluded activity cannot be written to or linked to.

Beyond the ranked authority, the only exception to owner-based precedence is
an explicit human decision: `upsert_activity(..., force=True)` lets one trusted
source take ownership of every non-manual field, and the force flow records a
manual owner patch for the fields it took so a rebuild keeps the decision.
Triage `(t)` uses it to re-import a single Intervals activity; normal imports
never force.

VO2max has two independent owners: Garmin FIT writes `vo2max_garmin` and
Runalyze writes `vo2max_runalyze`. Runalyze may fill an empty
`vo2max_garmin` with its estimate as a fallback, but a later FIT value
replaces that fallback. Tags are replaced per source on reimport; manual tags
(`is_manual = 1`) are never touched.

Time fields have distinct meanings: `duration_s` is recording/timer time
(Intervals `icu_recording_time`, FIT `total_timer_time`), `moving_s` is moving
time (Intervals `moving_time`, FIT `total_moving_time` when present), and
`elapsed_s` is wall-clock elapsed time. Observed per-source differences and
the Gumpoldskirchen example are documented in
[SOURCE_NOTES.md](SOURCE_NOTES.md). Planned events only expose moving time,
so their `duration_s` is the planned moving duration. A large moving-vs-
recording gap is a review item.

Sports are normalized through `hobbyjogging_core.sports`: one alias table maps
FIT sport/sub-sport pairs, Intervals type names, and manual entry to the same
canonical names, and reports/quality rules share the same sport groups. The
writer treats placeholder sports (`generic`, `other`, `unknown`) as unknown, not
as competing claims: a specific sport fills a placeholder and never conflicts
with it. Two different specific sports still become a `field_conflict`.

## Schema evolution and data maintenance

Two tracks, one rule: never edit something that has already run.

**Schema migrations** are ordered, immutable SQL in
`hobbyjogging_core.db.migrations`, tracked by `PRAGMA user_version` (currently
10). A schema change adds a new version; `open_database()` applies pending
ones, so there is no separate migrate step.

**Data tasks** live in `hobbyjogging-maintenance` and are registered by id:

- `backfill` — a one-time transformation after a schema or logic change. It is
  recorded in `data_migrations` and skipped once applied. Changing the
  transformation means a new id (`..._v2`), never an edit.
- `recompute` — an idempotent re-derivation of stored values from their
  authoritative inputs (raw payloads or other canonical fields). It runs every
  time and is only logged.

`maintenance_runs` records every run, dry or not, with its counts and outcome.
A dry run executes the real code path and rolls the transaction back, so it
cannot drift from a real run. `--output PATH` still writes the task's findings
(the conflict review list), because that is exactly what a dry run is for.
Tasks write through `TrainingWriter`, so manual values and ownership rules
keep holding; a task never commits on its own.

Workflow for a schema change:

1. Design the target shape.
2. **Expand** — add tables/columns in the next migration; never drop or rename
   yet.
3. **Backfill** — add a registered task for existing rows, dry-run it, then
   run it on the real DB.
4. **Switch** reads and writes (model, repository, writer, importers, reports).
5. **Verify** — tests plus `hobbyjogging-maintenance status`.
6. **Contract** later — a separate migration removes what nothing reads.

```bash
uv run --env-file .env hobbyjogging-maintenance list
uv run --env-file .env hobbyjogging-maintenance status
uv run --env-file .env hobbyjogging-maintenance run workout_classification_v1 \
  --dry-run --output data/workout-classification-conflicts.txt
uv run --env-file .env hobbyjogging-maintenance run workout_classification_v1
uv run --env-file .env hobbyjogging-maintenance run --all
```

Scope flags are `--from`, `--to`, `--entity`, and `--limit`. `--force` re-runs
an applied backfill; `--all` runs every pending backfill. `sync.sh`
runs the two idempotent classification recomputes
(`workout_sets_current`, then `workout_classification_queue`) after a
successful sync; `--no-classify` skips them. Backfills stay deliberate.

## Import pipeline

1. **Ingest.** FIT files are parsed from the archive; Intervals.icu activities,
   wellness, and events are fetched from the API. Raw payloads are stored in
   `source_records` keyed by `(source, record_type, external_id)`.
2. **Match.** A FIT session is matched to a canonical activity by temporal
   overlap; ambiguous one-to-many matches are queued, not guessed. Intervals
   matches by external id, then temporally.
3. **Write with owner-based precedence.** There is no per-source priority;
   a field may declare a ranked authority where one source is a better
   measurement:
   - manual field → never written;
   - same source reimporting → refreshes its own field;
   - a ranked source (`moving_s`/`elapsed_s`: Intervals, then FIT;
     `device_id`/`vo2max_garmin`: FIT) replaces another source's value
     silently; an unranked value keeps it and is not a conflict;
   - first owner keeps every other field while other sources agree within
     tolerance (about 1%, with 2 s / 10 m floors; average HR has a wider
     5 bpm floor; 15 s for start times);
   - a blank `name`/`description` is a gap, so a later source may fill it
     (an empty incoming value never clears text);
   - a meaningful cross-source disagreement on any other field changes nothing
     and is recorded as a `field_conflict` review item;
   - an explicit trusted re-import (`force=True`, triage `(t)`) takes
     ownership of non-manual fields (this becomes a manual owner patch, item
     17).
   Conflict-tracked fields are `duration_s`, distance, average HR, start
   time/date, timezone offset, sport, and training load. `moving_s` and
   `elapsed_s` resolve to the ranked source (Intervals, then FIT) without
   review, and average HR only opens a review item beyond 5 bpm. Subjective
   fields keep their owner silently.
4. **Quality rules.** Canonical values are checked for zero duration, missing
   distance for pace sports, implausible implied pace, and a moving-time vs
   recording-time gap above `max(10 min, 25% of recording)`; findings are
   queued.
5. **Record.** Every run is an `import_runs` row; review items are idempotent
   by fingerprint and supersede older items when the underlying conflict
   changes.

### Planned event reconciliation

Intervals is authoritative for planned workouts and races in the planning
window. The `events sync` command (also run by the regular Intervals import)
fetches the current events and:

- overwrites every field from the payload, including clearing fields that are
  now NULL;
- replaces the planned zone distribution (`workout_doc.zoneTimes`, with the
  zone kind inferred from the workout targets);
- soft-excludes events that disappeared (deleted or replaced with a new id);
- revives events that reappear;
- prunes only events linked to Intervals source records; manual and other
  source events are untouched.

Reports read events through `TrainingRepository`, which filters
`excluded_at IS NULL`.

### Garmin Personal API fetch

The official Personal API is the automated source for original FIT files; it
is implemented in `hobbyjogging-import` as `garmin fetch`.

- The API key lives in `.env` (`GARMIN_PERSONAL_API_KEY`, with `GARMIN_API_KEY`
  as fallback), valid for 30/90/180/365 days. Each run exchanges it for a 24 h
  bearer token (cached at
  `~/.config/garmin/connect-personal-api-bearer-token.json`); there are no
  refresh tokens, so a 401 re-obtains the token.
- `garmin fetch [--since DATE] [--to DATE] [--days N] [--limit N] [--force]
  [--fit-dir PATH] [--dry-run]` lists activities (paged) and downloads the
  original file via `/download-service/files/activity/{id}` (a ZIP containing
  the FIT), extracts it atomically into the FIT archive, and records a
  `source_records` manifest (`source = "garmin"`, `record_type =
  "activity-file"`). The existing FIT importer then ingests the files; there is
  no separate write path.
- API-downloaded FITs are byte-identical to the GDPR archive export (verified
  on four activities in November 2026). Garmin VO2max is still in the FIT as
  undocumented message 140, field 7 (`raw * 3.5 / 65536`), so the FIT is the
  VO2max source; the JSON summary's `vO2MaxValue` is null.

### Runalyze enrichment

Runalyze is an enrichment source, not an activity source. The API provides
comments, tags, gear, and the Runalyze VO2max estimate:

- Rows are matched to existing activities temporally (Runalyze exposes no
  Garmin activity id) and stored as `source_records` with
  `external_id = runalyze:<id>`; unmatched rows create a canonical activity
  (decision: keep the history complete).
- Comments fill `activities.description` only when it is blank, idempotently
  and without taking ownership of the field.
- Tags land in `activity_tags`; gear is upserted into `equipment` and linked via
  `activity_equipment` (first shoe/bike item primary, rest secondary). The
  equipment payload has a name and category but no brand/model, so identity
  uses the name and co-occurrence with the sheet shoes.
- `activities.vo2max_runalyze` stores the effective estimate; `0` /
  `use_vo2max=false` means missing. Runalyze never writes `vo2max_garmin`; the
  raw payload keeps the variants.
- Race results land in `race_results` and the linked event in
  `event_activity_links`; weight and illness ranges fill `wellness_days` and
  `training_periods`. Phases 1–2 (read-only inventory, comments and tags)
  landed; gear identity is next.

## Review workflow

Review categories: `ambiguous_match`, `field_conflict`, `quality`,
`duplicate`, `manual_flag`, `workout_classification`, `ambiguous_equipment`.

`workout_classification` items are `info`-level: the activity's data is fine,
it just has no decided workout method/target. `ambiguous_equipment` items are
also `info`-level: the activity is fine, only the gear identity is uncertain.
Neither hides an activity from reports (unlike the other categories). Triage
`(k)` shows the classifier and sheet proposals and writes the chosen sets as
manual values (`1` classifier, `2` sheet, `m` merge, `n` leave unclassified).
A resolved decision is not reopened; changed proposals supersede the old item.

- `review list`, `show`, `resolve`, `ignore`, `flag`, `scan` — non-interactive
  queue management and backfill.
- `review edit` — manual values (`duration`, `distance`, `sport`), written as
  manual overrides and followed by a quality re-check.
- `review exclude` / `review restore` — durable soft delete of an activity and
  its source records, or undo.
- `review triage` — interactive walk with per-item decisions committed
  immediately: inspect, open every linked activity (`o`), copy the Intervals
  or Garmin Connect URL (`ci`/`cg`), edit, pick a conflicted value (`v`),
  force re-import one Intervals activity (`t`), exclude, resolve, ignore,
  note, link an ambiguous candidate, skip, quit. `review show` prints the same
  links.
- Review items dedupe by `(category, fingerprint, activity_id)`; the source
  record stays on the item for provenance but is not part of the fingerprint.

Reports hide activities with open review items by default (`--include-review`
shows them); excluded activities never appear. The queue is the quality gate:
an unresolved conflict or finding means the displayed numbers are not yet
trusted.

## Report and view layer

The rule is **compute → render**:

1. `sources/` fetches canonical data for a date range through `DataSource`.
2. `analysis/` / `series.py` compute derived metrics and return typed
   results (`model.py`), with no formatting and no I/O.
3. Renderers turn those results into output:
   - Markdown reports for the terminal (`daily.py`, `overview.py`,
     `recovery_report.py`, `period_report.py`, `subt_report.py`,
     `activity_list.py`, `mdpretty.py`);
   - plotly figures (`charts.py`): the CLI exports PNGs via kaleido and the
     dashboard embeds the same figures as HTML;
   - static HTML dashboard pages (`html.py`, `dashboard/`);
   - JSON for LLM bundles or future clients (planned).

Charts consume prepared series and return figures; they never read the
database or parse report text. Adding a report means adding analysis plus a
renderer, not a new data path.

New metrics start in the lab — `./lab.sh` for an interactive session and
`experiments/` for a runnable script — and are promoted through the gate in
[METRICS.md](METRICS.md): cheap exploration, then a card, then `analysis/`
plus a renderer, and only then the dashboard.

### Dashboard

Static-first, generated on the homelab:

- Self-contained HTML with embedded plotly charts and plain tables; no SPA,
  no client-side data fetching. `plotly.min.js` is bundled into the site.
- Views: weekly overview (7/42/182-day hard/total EWMA weekly equivalents,
  running volume by intensity group, load, plan vs actual, quality sessions),
  recovery and health (HRV, resting HR, sleep with 7-day averages), activity
  list, activity detail, data-health summary, and selected Markdown reports
  converted to HTML.
- Every page carries a generation timestamp and a data-health banner (open
  review items, missing data).
- Generation writes to a temporary directory and atomically swaps, so a
  partially written dashboard is never served. A marker file prevents
  replacing an unrelated directory.
- Data health counts review-hidden activities and missing
  load/pace-zone/HR/distance data. The individual review-item queue is
  available through `DataSource.review_items`; rendering it is a reports
  follow-up.
- Interactivity is limited to plotly zoom/pan; filters and server-rendered
  drill-down are the upgrade path.

### LLM coaching export (planned, lower priority)

A deterministic, diffable bundle generated from the same view models:

- athlete goals and constraints, planned events, recent load and recovery
  trends, weekly volume/time by zone, key sessions;
- explicit caveats: open conflicts, exclusions, missing HR/GPS;
- compact JSON facts plus a short markdown digest, bounded in size and
  reproducible for a given date range.

Coaching is an ongoing conversation, so the bundle will also include a small
append-only decision log (recommendation, decision, followed or not) to give
continuity across sessions. Export is intentionally deferred behind the
dashboard: the view models make it cheap to add later.

## Status (November 2026)

- Canonical pipeline, review workflow, manual editing, and exclusion: done.
- Sources: FIT archive, Intervals.icu, the Garmin Personal API fetch, Runalyze
  and the Strava CSV import are implemented; schema v22 adds per-source social
  text, v23 the manual input layer, and earlier versions add set-based workout
  methods/targets and the maintenance bookkeeping tables.
- Schema evolution is two-track: immutable SQL migrations plus registered
  backfills/recomputes in `hobbyjogging-maintenance`.
- Reports: Markdown reports, charts, the activities table, the year/month
  comparison, and the static dashboard; report code is split per report.
- The review queue holds the open Runalyze ambiguous-match rows; reports still
  hide activities with open items by default (`--include-review` shows them).
- Phase 1 remaining: the optional Strava API and the reports/dashboard
  follow-ups; phases 2–3 are defined above.

## Deployment

- **Sync job** on the homelab: Garmin fetch, Intervals incremental import,
  FIT archive scan, Runalyze enrichment, review scan, then dashboard
  regeneration. One command, idempotent, prints a diff summary (new activities,
  changed fields, new conflicts, new findings).
- **Static serving** via Caddy or nginx; regeneration triggered by the sync
  job, not per request. `./sync.sh` regenerates after a successful sync;
  `./dashboard.sh` is the interactive wrapper that also opens the page.
- **Refresh**: wall screens use meta-refresh; phones reload manually.
- **Backups**: periodic `sqlite3 .backup` or Litestream; the database is the
  only irreplaceable artifact.
- **Database placement**: local disk on the homelab. Do not share SQLite over
  NFS/SMB.
- **Roles**: read-only connections for the report layer; writes only from the
  import/review CLI and the maintenance tasks.

## Non-goals and deferred work

- No pandas. Plotly builds every chart; kaleido exports CLI PNGs and the
  dashboard embeds the same figures as HTML.
- No SPA or client-side analytics framework.
- No phone interactivity for now.
- No direct remote database access; clients read rendered pages.
- Generic CSV import remains optional/deferred. Runalyze is covered by its API,
  not by CSV.
- Per-second activity streams are phase 3 and are not stored as SQLite rows.
  The raw FIT archive is the stream source; a stream index and an on-demand
  reader (or Parquet materialisation) are deferred until then.
- The Runalyze Garmin-id gap means matching stays temporal; exact linking can
  be added if Runalyze ever exposes the external activity id.

## Working conventions

- Package-scoped changes happen in package sessions; cross-package contracts,
  schema, and architecture happen at the repo root. Details in
  [AGENTS.md](AGENTS.md).
- Tests are `unittest` (pytest is not installed) and run per package from its
  tests directory. All four suites must stay green for cross-package changes.
- Commits follow session scope; the user pushes manually.
