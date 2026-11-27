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

The work is organised in four phases. The numbered queue in
[NEXT_UP.md](NEXT_UP.md) owns the items; the phases are direction and exit
tests, not a second task list. They order the *structural* work only: a bug
fix, a dashboard fix, a report over data already stored, or a lab metric that
passed the gate may land in its owning package at any time (see
[AGENTS.md](AGENTS.md)).

| phase | scope | complete when |
|---|---|---|
| **1. Works for me** | canonical DB, review, every source, reports, dashboard and lab | done 2026-11-19: all imports are in and the reports/dashboard answer the daily questions |
| **2. Works for someone else** | install and configuration for a second athlete (`init`/`doctor`, `sources.toml` + `.env`, first-run docs, CI, release versioning, lab detach), a declared source-capability matrix, and a usable dashboard without Intervals (source workout type, reps, thresholds/zones, wellness, fallback load) | done 2026-11-24: a fresh clone builds the demo with no credentials, `init`/`doctor`/`sync` cover every configured source, and a Runalyze+Garmin athlete's dashboard renders categories, laps/reps, zones, load, wellness and races — without editing code or SQL |
| **3. Trustworthy data** | extraction, audit, evidence-gated suggestions, duplicate cleanup and the CLI write surface | every pass in [DATA_BRUSH.md](DATA_BRUSH.md) can be done through the CLI: any activity audited and corrected without SQL, every suggestion recorded, a rebuild after the corrections yields an empty diff, and open items, duplicates and coverage gaps are trending down |
| **4. Durable and more reach** | homelab, more sources, streams, platform independence, LLM coaching, performance, and the localhost write UI | parked until phases 1–3 are complete |

**Phase 1 is complete (2026-11-19):** all sources are imported, the reports,
dashboard and race pages answer the daily questions, and the lab promotes
metrics on demand. **Phase 2 is complete (2026-11-24):** the install path (2a),
the usable Runalyze+Garmin dashboard (2b) and the capability matrix are in
place, validated by the acceptance run; its two findings (subT selection and
the derived table, threshold coverage) are fixed. **Phase 3 is current:** it
makes the stored record trustworthy and correctable through the CLI, and
closes when the [data brush](DATA_BRUSH.md) passes; the localhost write UI is
phase 4. **Phase 4** stays parked.

A platform is retired **per metadata type, never per platform**: the type gets
a DB surface first (phase 3), the historical import keeps backfilling, and the
platform stays a read-only fallback until the DB is at least as good for that
type. Superseding can mean better, not identical — the DB already beats the
platforms at race reporting and analysis; it lacks capture and editing.

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
`sources.toml`, defaulting to create. Strava and Runalyze take the policy; the
recording sources (FIT, Intervals, sheet) always create and are switched with
`enabled`. A row with a rejected candidate becomes a review item instead of a
creation, so the default cannot manufacture duplicates. The same file sets the
text targets: a title or description stays in `activity_social` (default) or is
promoted to `activities.name`/`description`; a promoted title feeds the
classifier, a description does not.

Each adapter declares its payload→field mapping (`FIELD_MAP`), so the derive
check, the rebuild and the settings view read one table.

A source that carries its **own workout type** maps it to the canonical sets at
import time — the sheet's `Trainigstyp` codes and Runalyze's `type` object — so
classification does not depend on a name the athlete never writes. An unmapped
type is reported for the audit, never guessed. A source without one leaves
classification to the classifier, tags and triage.

A new source is a profile plus a fetch/normalize adapter. It should not add a
branch to the writer, the matcher or the quality rules.

Four axes stay distinct: **capability** (the profile's record types, matching,
creation fields, detail need and request budget), **selection**
(`sources.toml`: enabled sources, the create policy, text targets and
per-capability toggles), **precedence** (owner-based, per-field ranked
authority, manual inputs) and **review** (what a disagreement does). Capability
and selection are configurable; precedence and review are not. The profile is
the one capability declaration; `settings` renders the matrix and the uncovered
record types/fields, and `doctor` warns when the enabled sources cannot supply
a visible dashboard area (wellness, load, zones, social, reps, races).

## Principles

1. **Three roles, one direction.** Importers write *received facts* (raw
   payloads and the fields they report). Maintenance writes *derived stored
   values* (one-time backfills and recurring recomputes). Reports compute
   *cheap metrics on read* and never mutate the database. No layer formats
   another layer's output. Human edits are inputs, not a fourth layer: triage
   and `activity edit` write manual values through the same `TrainingWriter`,
   and the projections are rebuilt from them.
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
derivation without writing. On the real DB every owned activity field matched
its input. Ownership is an **input** (a recorded decision), not a projection:
the first owner keeps a field, per-field ranked authority resolves the declared
exceptions, and a meaningful disagreement becomes a review item. There is no
global source order and no virtual read path.

The manual overlay protects the decisions themselves: `export-manual` writes
manual fields, owner patches, manual sets/tags/equipment, exclusions and
ignored/resolved review answers as JSONL; `import-manual` re-applies it. The
`rebuild` check copies the raw records, activity links and pointers into a
fresh schema, applies the overlay, runs `recompute_canonical`, and diffs every
canonical value and the exclusion set against the live database. It does not
re-import from the network or re-match activities; an empty diff proves the
projection from the stored inputs, not the matching decisions.

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

- `model.py` — `Activity`, `ActivityWeather`, `ActivityMetrics`, `Lap`,
  `Interval`, `WellnessDay`, `Event`, `Equipment`, zone models; activities
  carry both VO2max values and tags.
- `sports.py` — canonical sport names, labels, groups, and the shared alias
  table for FIT/Intervals/manual entry.
- `classify.py` — the workout-category heuristic (quality/non-quality,
  intervals/fartlek/longrun/race/tempo, subT rep length), `category_for_sets`
  (the stored sets to display kind inverse), plus `work_intervals` and the
  rep-length buckets. Classified activities take their category from the
  stored sets; the heuristic runs only for unclassified ones, and the
  classification tasks call it with `use_stored=False`.
- `db/schema.py`, `db/migrations.py` — SQL schema and forward-only migrations
  (`SCHEMA_VERSION`, currently 30).
- `db/writer.py` — `TrainingWriter`: import runs, source records, activity
  upserts, field provenance, manual edits and the append-only `edit_log`,
  exclusions, review items, laps, intervals, zone times, tags.
- `db/repository.py` — `TrainingRepository`: read queries over the canonical
  model.
- `datasource.py` — the `DataSource` protocol every report consumer depends
  on: activities, wellness, events, intervals, weather, session metrics,
  field provenance, equipment, and the review queue (`review_items`,
  read-only).
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
- `quality.py` — canonical quality rules (zero duration, distance, implied
  pace, moving time, start/offset vs `local_date`), field-conflict recording,
  review fingerprints, quality refresh after edits.
- `values.py` — parsers/formatters for manual entry (`46:20`, `8.2km`,
  RPE/feel/text) and the one prompt/parser table shared by triage and the edit
  command.
- `metrics.py` — session-average extraction from Intervals, Runalyze and the
  sheet payloads, normalized to the canonical units the FIT parser already
  emits; the importer and the backfill share it.
- `tag_lexicon.py` — the one tag → meaning table: workout sets, illness and
  recovery, race/trail evidence, rep lengths, sheet area codes, context and
  ignored notes. The audit, classification, illness and trail proposals read
  it; an unmapped tag stays unmapped and no rule invents a meaning.
- `duplicates.py` — the same-session pair rule (sport/day, distance 2 %,
  duration 5 %, HR 5 bpm, start within ±15 min when both carry one) and the
  stable choice of the weaker copy. A missing start on one side keeps the
  same-day fallback. Detection opens a review item; resolution is exclusion,
  never merge.
- `editing.py` — shared manual-edit application used by `review edit`,
  `activity edit` and triage: scalar values, whole sets, clears, conflict and
  classification closure, the `edit_log` row and the quality re-check.
- `history.py` — shared edit-log writer (one row per changed field) and
  renderer for the entity commands.
- `select.py` — the id / ISO date / `last` / name-substring resolver for
  activities, equipment and periods; ambiguity lists candidates and refuses to
  guess.
- `equipment_cli.py` — `equipment add|list|edit|retire|history|link|unlink`;
  a manual row is an input, retire sets `retired_on`, and `link` appends a
  primary or secondary manual link without promoting the existing primary.
- `activity_cli.py` — `activity edit`: the direct human write surface with
  explicit flags, `--clear`, `--dry-run`, `--history` and an interactive mode.
- `triage.py` — interactive review walk; the `(k)` classification decision
  lives in `workout_classification_triage.py` as a runner mixin, including the
  evidence/stored choices and the `edit_log` write.
- `review_cli.py`, `cli.py` — `hobbyjogging-import` entry point.

### `hobbyjogging-reports`

Analysis, views, and rendering.

- `sources/` — the `DataSource` implementation: the canonical database. Raw
  payloads stay in `source_records`, so reports need no live API client.
- `analysis/` (`averages`, `baseline`, `common`, `compare`, `coverage`,
  `devices`, `efficiency`, `equipment`, `load`, `pace_hr`, `planned`, `races`,
  `recovery`, `rpe`, `streaks`, `subt`, `subt_ewma`, `thresholds`, `vo2max`,
  `zones`), `series.py` — pure functions over canonical activities, intervals,
  and wellness; derived metrics such as load, zone distribution, efficiency,
  race predictions, and recovery.
- `model.py` — typed view models and analysis result types.
- `classify.py` — category aggregation for display (`CategoryStat`,
  `category_breakdown`). The heuristic itself lives in
  `hobbyjogging_core.classify`.
- `daily.py`, `period_report.py`, `subt_report.py`, `subt_ewma_report.py`,
  `overview.py`, `recovery_report.py`, `race_report.py`, `sickness_report.py`,
  `streak_report.py`, `equipment_report.py`, `health_report.py` — one Markdown
  report per file; `report_commands.py` dispatches them.
- `sessions.py`, `recent.py`, `review.py`, `debug.py` — session detail (with
  the field-provenance block), shared lookback search, the review view, and a
  dump of the stored raw payloads.
- `corrections.py` — the read-only source-side checklist from open
  `field_conflict` items and source-attributable quality findings; Markdown,
  CSV or JSON, grouped by the platform that disagrees.
- `activity_list.py` — the activities table (selection, columns, rendering).
- `summary.py` — period totals, quality-session lists, recovery averages.
- `charts/` (split by family), `chart_commands.py` — plotly figures over
  prepared series.
- `format.py`, `mdpretty.py` — human formatting for the terminal, including
  the session metrics and running-dynamics lines.
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
- `runner.py` — one transaction per run, a pre-run `VACUUM INTO` snapshot for
  a real run (last five kept), dry run = run then roll back, bookkeeping in
  `maintenance_runs`.
- `store.py` — reads and writes for `data_migrations` and `maintenance_runs`.
- `workouts.py` — classifier, sheet, Runalyze-type, tag and comment proposals
  shared by the classification tasks.
- `backfills/activity_weather_v1.py` — `activity_weather` from the stored
  payloads; `backfills/weather_ambient_v1.py` then keeps only ambient
  temperature (sheet first, Intervals `average_weather_temp` second) and
  clears the device-only rows.
- `backfills/drop_ride_shoe_links_v1.py` — remove the sheet's source shoe
  links from rides, keeping manual links and every other sport.
- `backfills/activity_metrics_v1.py` — `activity_metrics` from the stored
  payloads and the FIT archive (the archive is re-read for the old FIT rows).
- `backfills/sheet_duplicates_v1.py` — copy a sheet-only duplicate's
  description to the device row and exclude the sheet row (exclusion, never a
  merge).
- `audit*.py` — the read-only historical evidence report: coverage, raw keys,
  tags, descriptions, trail/race evidence, classification, periods and
  session-average metrics. It never opens a review item.
- `backfills/event_race_method_v1.py` — `event_race_method_v1`.
- `backfills/event_zones.py` — `event_zones_v1`.
- `backfills/remove_tempo_method_v1.py` — `remove_tempo_method_v1`.
- `backfills/drop_empty_intervals_v1.py` — `drop_empty_intervals_v1`.
- `backfills/workout_classification.py` — `workout_classification_v1`.
- `backfills/drills_from_tags_v1.py` — add the drills method to the
  non-manual sets tagged LTT/Lauftechnik.
- `backfills/workout_classification_evidence_v1.py` — accept specific tag
  evidence on classifier/backfill projections once and close the remaining
  evidence items by policy.
- `recompute/workout_sets_current.py` — `workout_sets_current` (re-derives
  classifier-sourced sets after a rename, refines a classifier/backfill
  projection from a specific tag, unions drills/strides into non-manual sets
  and fills unclassified gaps).
- `recompute/workout_classification_queue.py` —
  `workout_classification_queue` (classifier/sheet disagreements plus a
  structured comment that refines a classifier/backfill projection; tag
  refinement and input precedence happen in `workout_sets_current`).
- `recompute/evidence_candidates.py` — `illness_candidates_current` (opens
  `period_candidate` items for illness tags outside a stored period) and
  `trail_candidates_current` (opens `consistency` items suggesting
  `trail_run`). Both are non-hiding and never write the proposed value.
- `recompute/duplicate_candidates_current.py` — opens one `duplicate` item per
  same-session pair and closes stale ones; the sheet cleanup is the separate
  backfill.
- `recompute/equipment_from_tags_current.py` — links mapped equipment tags
  (Thule) as secondary when the activity already has gear and primary only
  when it has none; existing and manual links stay.
- `cli.py` — `list`, `status`, `run`.

## Canonical data model

SQLite, forward-only migrations. Schema version 30.

- `activities` — canonical values: dates, sport, name, description, recording
  time (`duration_s`), elapsed time, moving time (`moving_s`), distance,
  elevation gain/loss (v12), heart rate (average and maximum, v12), training
  load, subjective fields, both VO2max values (`vo2max_garmin`,
  `vo2max_runalyze`), exclusion timestamp. `started_at_utc` is UTC and
  `tz_offset_min` the recorded local offset; `local_date` is the local day
  used for every report bucket, and `Activity.started_local` derives the
  display time (a row without a start time has no offset).
- `source_records` — raw imported payloads with checksums and provenance
  (`source`, `record_type`, `external_id`, `raw_path`, `payload_json`,
  exclusion timestamp).
- `activity_sources` — links between canonical activities and source records,
  including match method, confidence, and primary flag.
- `activity_field_sources` — per-field provenance: which source wrote a value,
  the value it wrote, and whether it is a manual override.
- `activity_manual_fields` — the manual inputs (a value or an owner patch)
  that a rebuild replays, so a manual decision is an input rather than a
  materialized side effect.
- `edit_log` (v26) — the append-only audit trail for manual writes
  (`entity_kind`, `entity_id`, `field`, old/new JSON, source, note). It answers
  what a value was before an edit and which review items the edit resolved;
  triggers reject update and delete. `activity_field_sources` is a snapshot,
  not a history.
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
- **Device identity.** `device_id` stays FIT-first; a provider name fills it
  only when the activity has no FIT source. A serial-less provider name that
  normalises onto exactly one FIT device (same manufacturer and product, serial
  present) claims that device; two devices of the same model are ambiguous, so
  the provider id stays and nothing is guessed. A serial-less FIT upload is
  not a device. App names — `Runalyze`, `Garmin Connect`, `Strava`,
  `intervals.icu` — are never devices; the importer skips them.
  A provider row that no activity uses is soft-excluded, never hard-deleted.
  `devices.name` is display-only and set once: the first non-empty provider
  name, whitespace-collapsed and title-cased. A FIT device keeps its
  product-derived label (the reports derive it) and a provider never writes its
  name; a re-import never updates an existing name.
- `race_results` (v16) — official race metadata, one row per activity:
  official distance and time, `officially_measured`, places and participants
  by total/gender/age class, `priority_level`, `status` (a PB counts only
  `completed`), notes and source. Kept apart from the measured GPS values, and
  a manual row is never overwritten by an import.
- `athlete_thresholds` (v14/v15) — dated snapshots of the athlete's
  threshold settings, **per sport**: `max_hr`, `lthr`, `threshold_pace_mps`.
  Intervals stamps them on every activity; a missing value carries forward and
  one snapshot per sport and date is kept. `threshold add` writes a
  `source='manual'` snapshot that the Intervals recompute never removes.
- `zone_configs` (filled by the import or the threshold recompute) — one row
  per distinct boundary set, with `activities.hr_zone_config_id` /
  `pace_zone_config_id` pointing at the era's config, so "Z3" means the same
  thing across years. A local config derives from the manual threshold
  snapshot (80/89/100/110 % of LTHR, 75/85/100/110 % of threshold speed) and
  sums lap zone times; an Intervals config and its times win where present.
- `activity_weather` (v13) — one row per activity: ambient temperature,
  feels-like, humidity, wind speed/degree/gust, wind chill, heat index,
  pressure, UV, clouds, condition and a night flag, in metric units. The first
  source owns the row; a later source only fills the fields it left empty.
  `temp_c` is air temperature, never the watch reading; a device-only value
  stays in the raw payload, and a row without ambient temperature renders no
  weather line.
- `activity_metrics` (v27/v28) — one nullable row per activity for session
  averages: cadence (steps/min for runs, rpm for rides), stride (m), vertical
  oscillation (mm), stance time (ms and %), stance balance (%), vertical ratio
  (%), respiration, power (W), calories (kcal), training effect, grade-adjusted
  pace (m/s) and average/min/max altitude (m). A per-field source map (v28)
  keeps the ranked authority stable: FIT owns device-measured dynamics,
  Intervals owns altitude and fills cadence/stride/calories where FIT has none,
  and Runalyze fills the remaining gaps. Per-second streams stay in the FIT
  archive.
- `activity_laps`, `activity_intervals`, `activity_zone_times` — detail data
  attached to activities, tagged by source record. Laps are device splits
  (auto-lap or manual); intervals are typed reps (`WORK` / `RECOVERY`, with
  group ids). An interval row's `source` (v25) is `intervals` for
  Intervals.icu's measured set or `derived` for one inferred from device laps;
  a derived set never replaces a measured one, and the session report labels
  it. They are complementary, not duplicates: the session report prints one
  raw segment table — intervals when there is more than one, otherwise laps
  when there is more than one — and the subT work-reps section is derived
  separately.
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
  column. Writes are fill-only: Garmin's daily feed fills only the NULL fields
  of a day Intervals already wrote, so the first source keeps its values.
- `equipment`, `activity_equipment`,
  `equipment_source_links`, `zone_configs` — supporting canonical data. An
  equipment row carries `is_manual` (v29): a hand-created or hand-edited item
  keeps its name, brand, model, dates and notes when a later source links to
  it. The `equipment_usage` view (v30) counts every link, so a secondary
  trailer contributes its sessions and km; the link role is identity, not a
  usage filter.
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
  `progression`, `race`, `strides`, `drills`, `other`. A tempo run is
  `continuous` with a `threshold` target; the retired `tempo` token normalizes
  to `continuous`. `fartlek` means *never structured*: `intervals` means reps
  were intended, even when the device data is missing. `strides` and `drills`
  are additive, never a replacement.
- **Targets** — `base`, `lt1`, `subthreshold`, `threshold`, `vo2max`, `speed`,
  `marathon`, `recovery`, `other`.
- **Quality** is derived: any quality method (`intervals`, `fartlek`,
  `long_run`, `progression`, `race`) or target (`lt1`, `subthreshold`,
  `threshold`,
  `vo2max`, `speed`, `marathon`) makes a session quality;
  base/recovery only is non-quality; no values is unknown. Strides or drills
  never make a session quality by themselves.
- **Sources and evidence** — importer, sheet and Runalyze-type sets are
  inputs; a classifier/backfill set is a re-derivable projection. A specific
  tag refines a projection in place (`source='tag'`); a structured comment on
  a projection opens one review item, while a comment otherwise only fills an
  empty classification. A sheet or manual set wins over tag and comment
  evidence; generic `other` never overrides a specific target. Strides and
  drills are unioned into any non-manual set, never replacing the run method.

Text fields have fixed roles:

- `name` — the session name ("easy", "3x9' subT long"), owned by the source
  that records the training intent. An auto-generated platform title
  ("Vienna Running") is a fallback, never a preferred value.
- `description` — the training notes: how the session went, the feeling, the
  intervals and paces. Intervals and the historical sheet fill it, Runalyze may
  only fill a blank, and a manual edit outranks both.
- `activity_social` (v22) — the social text: the pun title and its
  continuation, one row per source (`source` is data, so any social import can
  map into it). A source refreshes only its own row and a manual row survives
  imports. The default target keeps it social; a per-source target
  (`sources.toml`) may promote a title to `name` or a description to
  `description`, and a promoted title feeds `classify()`.

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
24). A schema change adds a new version; `open_database()` applies pending
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
(`workout_sets_current`, which re-derives classifier-sourced sets and fills
the remaining gaps, then `workout_classification_queue`) after a
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
- Wellness (resting HR, HRV, sleep, steps) is a separate feed, not part of an
  activity FIT: the Personal API's daily summaries supply resting HR, sleep
  seconds, steps, floors, SpO2 and weight, and the HRV service supplies the
  last-night average. Sleep detail and sleep score stay empty. The import is
  fill-only, so Intervals keeps the values where both run; the GDPR export is
  the fallback for a missing feed. Runalyze derives its wellness from Garmin,
  so it is not a substitute source.

### Runalyze enrichment

Runalyze is an enrichment source by default: comments, tags, gear and the
Runalyze VO2max estimate. It yields activity rows, so the per-source policy
decides what an unmatched row does (`create | review | ignore`); this athlete
keeps it at `review`, so an unmatched row becomes an `ambiguous_match` item
instead of a duplicate.

- Rows are matched to existing activities temporally (Runalyze exposes no
  Garmin activity id) and stored as `source_records` with
  `external_id = runalyze:<id>`; unmatched rows follow the create policy.
- Comments fill `activities.description` only when it is blank, idempotently
  and without taking ownership of the field.
- Tags land in `activity_tags`; a new gear record creates an `equipment` row and
  links activities via `activity_equipment` (first shoe/bike item primary, rest
  secondary). A record that matches an existing item only adds a source link
  and never rewrites its name, brand, model or dates. The equipment payload has
  a name and category but no brand/model, so identity uses the name
  (colour-stripped, acquisition date as the tiebreak) and co-occurrence with
  the sheet shoes.
- `activities.vo2max_runalyze` stores the effective estimate; `0` /
  `use_vo2max=false` means missing. Runalyze never writes `vo2max_garmin`; the
  raw payload keeps the variants.
- The activity `type` object (`Jogging`, `SubThreshold`, `Long Slow Distance`)
  maps to the canonical workout sets, and `fit_trimp`/`trimp` can stand in for
  `training_load` when no Intervals source exists. Both are phase-2 work: a
  name-less athlete has no other classification signal, and no other load.
- Race results land in `race_results` and the linked event in
  `event_activity_links`; weight and illness ranges fill `wellness_days` and
  `training_periods`. Phases 1–5 (inventory, comments/tags, gear, race
  results, `vo2max_runalyze`) are landed and applied; the reports phase is
  reports item 15.

## Review workflow

Review categories: `ambiguous_match`, `ambiguous_race`,
`ambiguous_equipment`, `create_activity`, `consistency`, `field_conflict`,
`period_candidate`, `quality`, `duplicate`, `manual_flag`,
`workout_classification`.

`workout_classification`, `ambiguous_equipment`, `consistency` and
`period_candidate` items are `info`-level: the activity's data is fine, it
just has no decided workout method/target, an uncertain gear identity, a
trail-evidence suggestion, or an illness range that is not yet a stored
period. None hides an activity from reports (unlike the other categories).
`duplicate` links the likely weaker copy and is hiding until a human excludes
one row; resolution is exclusion, never a merge. Triage `(a)ccept suggestion`
writes a `consistency` item's suggested sport as
a manual value. `create_activity` holds a summary row the policy chose to
review rather than create. Triage
`(k)` shows the classifier and sheet proposals; a legacy evidence item also
carries its tag/comment evidence and the stored set. It writes the chosen
sets as manual values (`1` classifier, `2` sheet, `4` evidence, `m` merge,
`n` leave unclassified) and resolves `s` kept stored without a write. A
resolved decision is not reopened; changed proposals supersede the old item.

- `review list`, `show`, `resolve`, `ignore`, `flag`, `scan` — non-interactive
  queue management and backfill.
- `review edit` — manual values (`duration`, `distance`, `sport`), written as
  manual overrides and followed by a quality re-check.
- `activity edit <id>` — the direct human write surface, with no review item
  required: name, description, duration, distance, sport, sub-sport, RPE,
  feel, tags, methods, targets and equipment. Every change is a manual input
  through the same `editing` functions as triage, appends an `edit_log` row,
  and closes the open `field_conflict` for a touched field or the
  `workout_classification` item after a set change. `--clear` removes a manual
  value and its ownership; `--dry-run` rolls everything back; `--history`
  reads the log; with no flags it prompts field by field, current value as the
  default, and a blank answer keeps it. This is the reference write surface:
  the later localhost UI binds to the same functions rather than reimplementing
  them.
- `race-result`, `threshold`, `period add|remove` and
  `equipment add|edit|retire` write their own entity rows and append one
  `edit_log` row per changed field; their `history` command shows old/new.
  `equipment` writes `is_manual=1`, so a later sheet or gear import only links
  and never rewrites the row; retire sets `retired_on`. These commands, plus
  `activity edit` and the review commands that take an activity, resolve an id,
  ISO date, `last` or a name substring; an ambiguous selector lists the
  candidates and refuses to guess.
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
   - plotly figures (`charts/`, split by family): the CLI exports PNGs via
     kaleido and the dashboard embeds the same figures as HTML;
   - static HTML dashboard pages (`html.py`, `dashboard/`);
   - JSON for LLM bundles or future clients (planned).

Charts consume prepared series and return figures; they never read the
database or parse report text. Adding a report means adding analysis plus a
renderer, not a new data path.

New metrics start in the lab — `./lab.sh` for an interactive session and the
private notebook (`$HOBBYJOGGING_LAB_DIR`, default `experiments/`) for a
runnable script — and are promoted through the gate in
[METRICS.md](METRICS.md): cheap exploration, then a card, then `analysis/`
plus a renderer, and only then the dashboard.

The athlete-tuned numbers — the quality RPE, the long-run and efficiency
bands, the subT buckets, the conflict tolerances, the compare window and the
dashboard lookbacks — live in
[`hobbyjogging_report/defaults.py`](../packages/hobbyjogging-reports/src/hobbyjogging_report/defaults.py)
with the evidence in the metric cards. They are defaults, not laws.

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
  load/pace-zone/HR/distance data, and renders the open review queue itself
  (severity, category, detail, and links to the activity and its candidates)
  from `DataSource.review_items`.
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

- **Phase 1 complete; phase 2 code complete (2026-11-24).** All sources are
  imported and applied on the real DB; the optional Strava API stays deferred
  to phase 4. The install path (`init`/`doctor`, full-source `sync`, minimal
  licence, CI) and the Runalyze+Garmin profile (type mapping, derived reps,
  TRIMP load, manual thresholds/zones, Garmin wellness, name labels) are in
  place; the real second-athlete acceptance run remains.
- Canonical pipeline, review workflow, manual editing and exclusion: done.
  Schema v26 adds the append-only `edit_log`; v25 interval provenance; v24
  soft-excludes retired device rows; v23 is the manual input layer
  (`activity_manual_fields`), v22 per-source social text, and earlier versions
  add set-based workout methods/targets and the maintenance bookkeeping.
- Sources: FIT archive, Intervals.icu, the Garmin Personal API fetch, Runalyze
  (inventory, comments/tags, gear, race results, VO2max) and the Strava CSV.
- Device identity is FIT-first and generic: a provider name fills `device_id`
  only when the activity has no FIT source and claims the unique FIT device of
  its model; app names are never devices, and an unused provider row is
  soft-excluded.
- The canonical row is a checked projection: `verify_canonical` reports 0
  drift, 0 dangling and 0 unmapped over 68,001 owned fields, and
  `recompute_canonical` is a no-op on the real DB.
- Import policy is per athlete: `sources.toml` plus `.env`; this athlete keeps
  Runalyze at `review`, Strava at `ignore` and the sheet disabled.
- Schema evolution is two-track: immutable SQL migrations plus registered
  backfills/recomputes in `hobbyjogging-maintenance`.
- Reports: Markdown reports, charts, the activities table, the year/month and
  period comparisons, the race and event pages, and the static dashboard. The
  overview and the Performance "VO2max methods" card draw the promoted
  effective VO2max estimate (all runs and the steady 40–75 band) beside Garmin
  by device, Runalyze and race VDOT; report code is split per report, and
  every dashboard card has a CLI equivalent.
- The review queue holds the 19 Runalyze `ambiguous_match` rows; that is user
  triage, not a pipeline gap. Reports still hide activities with open items by
  default (`--include-review` shows them).
- The phase-2 worklist and the phase-3 order live in
  [NEXT_UP.md](NEXT_UP.md).

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
- Per-second activity streams are phase 4 and are not stored as SQLite rows.
  The raw FIT archive is the stream source; a stream index and an on-demand
  reader (or Parquet materialisation) are deferred until then.
- The Runalyze Garmin-id gap means matching stays temporal; exact linking can
  be added if Runalyze ever exposes the external activity id.

## Working conventions

- Package-scoped changes happen in package sessions (core is handled at the
  root); cross-package contracts, schema, and architecture happen at the repo
  root. Details in [AGENTS.md](AGENTS.md).
- Tests are `unittest` (pytest is not installed) and run per package from its
  tests directory. All four suites must stay green for cross-package changes.
- Commits follow session scope; the user pushes manually.
