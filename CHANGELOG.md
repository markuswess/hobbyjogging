# Changelog

One repo-level version; the four packages move together. A version answers
"which code built this database": the schema version, the registered data
tasks and the report surface are listed per release. Experiments, report
output and docs are not versioned.

Compatibility is stated as "requires schema ≥ N, migrates to M". The database
records its own `PRAGMA user_version`, migrations are forward-only, and
`migrate()` refuses a database newer than the code.

## Unreleased — 0.3.1

Schema: **30**. Compatibility: requires schema ≥ 1, migrates to 30.

### Brush bug fixes

- Duplicate detection requires starts within ±15 min when both rows carry
  one; a missing start on one side keeps the same-day fallback. The
  eight-hour-apart pairs no longer open.
- The sheet importer skips `Schuhe` when the stored activity is a ride;
  `drop_ride_shoe_links_v1` removes the existing source shoe links on rides
  and keeps manual links and every other sport.
- `activity_weather.temp_c` is ambient air only. Intervals writes
  `average_weather_temp` when `has_weather` and never `average_temp`; the sheet
  writes its value through `set_activity_ambient_temperature`, and
  `weather_ambient_v1` restores the sheet values and clears the device-only
  rows. A weather row without ambient temperature renders no weather line;
  health coverage counts ambient temperature only.

### Classification

- `drills` is a workout method beside `strides`; it never makes a session
  quality by itself and is additive. `LTT`, `Lauftechnik` and `Lauf-ABC` map
  to drills instead of threshold.
- `drills_from_tags_v1` adds drills to the non-manual sets of LTT/Lauftechnik
  activities. On the real-DB copy: 32 tagged, 31 added, 1 manual set skipped.
- Evidence policy: a specific tag refines a classifier/backfill projection in
  place (`source='tag'`); a sheet or manual set wins over tag and comment
  evidence; a comment only fills an empty classification; generic `other`
  never overrides a specific target; `Raceday` is context, not a race method.
  The queue no longer opens evidence items.
- `workout_classification_evidence_v1` applies that policy once. On the copy
  it accepted 276 tag refinements, closed 273 items by policy, and left 0
  open `workout_classification` items; a second run is a no-op.

### Routes and comments

- Geographic tags now carry the `place` kind. `routes_from_place_tags_v1`
  creates one source-scoped route per canonical place (`runalyze:tag:<slug>`,
  aliases `kanal`/`donaukanal` and `Wienerberg`/`Wienerbergteich` merge) and
  links the activity with `source='tag'`; an existing manual or sheet route
  wins. On the real-DB copy: 387 tagged activities, 439 links, 28 routes; a
  re-run is a no-op, and the session report shows the place.
- `description_proposal` now ignores recap/PB sentences, negated or
  alternative clauses (`statt`, `instead of`, `not`, `ohne`, `zu hügelig`),
  and race-as-a-verb; Wechseltempo/Fahrtspiel is fartlek, a structured
  interval with a target is intervals, and `Wohlfühltempo` is not a threshold
  session.
- Comment evidence reads the per-source `activity_social.description` as well
  as the canonical field. A structured comment on a classifier/backfill
  projection opens one review item; a manual or sheet set never changes. On
  the copy the queue opened 11 material comment items and kept prior decisions.

### Gear

- `equipment link <activity> <equipment> [--role primary|secondary]` appends a
  manual link without promoting the existing primary; `equipment unlink`
  removes one link. Both accept an activity id/date/`last`/name, write an
  `edit_log` row and support `--dry-run`.
- `equipment_from_tags_current` links mapped equipment tags (Thule) as
  secondary when the activity already has gear and primary only when it has
  none; existing and manual links are untouched, and the task notes unmapped
  gear-like tags.
- Schema 30 drops the `role = 'primary'` filter from the `equipment_usage`
  view, so a secondary trailer contributes its sessions and km. The gear
  report already reads all activity links; the view now agrees.

## 0.3.0 — 2026-11-25 (phase 3: trustworthy data)

Schema: **29**. Compatibility: requires schema ≥ 1, migrates to 29.

### Surface

- Schema 26–29: `edit_log`, `activity_metrics` (and its per-field source map),
  and `equipment.is_manual`.
- New data tasks: `activity_metrics_v1`; the classification/evidence tasks
  `workout_classification_v1`, `workout_sets_current` and
  `workout_classification_queue`; duplicate detection and cleanup
  (`duplicate_candidates_current`, `sheet_duplicates_v1`); and the evidence
  candidates `illness_candidates_current` and `trail_candidates_current`.
- New write surface: `activity edit`, `equipment`, `race-result`, `threshold`,
  `period`, the shared id/date/`last`/name resolver, and an `edit_log` row for
  every manual write.
- New report surface: field provenance in the session report and the
  read-only `reports.sh corrections` checklist (Markdown, CSV, JSON).

### Provenance and corrections

- The session report (CLI and dashboard) now explains each owned field:
  distance, duration, average/max HR, elevation, sport, load, both VO2max
  owners and device, with the owner source and its value. An open
  `field_conflict` adds the losing source, its value, the cause and a review
  link; a single-source activity collapses to one line. The block reads
  `activity_field_sources` through the new `DataSource.activity_field_sources`
  method; no schema change.
- `reports.sh corrections [--days|--from|--to] [--format markdown|csv|json]`
  is the read-only source-side checklist. It groups open conflicts by the
  platform whose value disagrees and also lists source-attributable quality
  findings: date, activity, field, canonical value and owner, source value,
  cause, suggested action and a deep link where one exists. It never writes,
  calls an API or resolves an item.

### Evidence conflicts
- `workout_classification_queue` compares a mapped tag or explicit description
  with the stored sets of a classified activity. It opens one
  `workout_classification` item only when the evidence names a method or
  target the stored set lacks; agreeing or absent evidence resolves stale
  items. Nothing is written automatically.
- The item context carries `evidence_source`, the evidence sets and the stored
  sets. Triage `(k)` offers `4) evidence` and `s) kept stored` alongside the
  classifier/sheet choices; a chosen set is written as manual values and logs
  old/new in `edit_log`, while `kept stored` resolves without a write.

### Manual write coverage

- `race-result`, `threshold`, `period` and `equipment` now append one
  `edit_log` row per changed field, in the same transaction; `--dry-run` writes
  none and each has a `history` command. Triage `(v)` and `(t)` log their
  manual value and owner patch too.
- `equipment add|list|edit|retire|history` is the manual gear surface. Schema
  29 adds `equipment.is_manual`; a manual row keeps its fields when a later
  sheet, Runalyze or Strava import links to it. Retire sets `retired_on`; a
  duplicate normalized name is refused with the existing row named.
- `activity edit`, `race-result`, `threshold history`, `period remove|history`,
  `equipment edit|retire|history` and the review commands that take an activity
  accept an id, ISO date, `last` or a name substring. An ambiguous date or name
  lists the candidates and refuses to guess; interactive `activity edit`
  prompts for the choice.

### Session metrics

- `activity_metrics` (v27/v28) stores one nullable row per activity for the
  session averages already in FIT, Intervals, Runalyze and the sheet: cadence
  (steps/min for runs, rpm for rides), stride, vertical oscillation, stance
  time and percent, stance balance, vertical ratio, respiration, power,
  calories, training effect, grade-adjusted pace and average/min/max altitude.
  FIT owns device-measured dynamics, Intervals owns altitude and fills
  cadence/stride/calories where FIT has none, and Runalyze fills the remaining
  gaps; a per-field source map keeps that authority stable across reimports.
- The FIT parser extracts the averages (calories was already parsed and
  dropped), the Intervals/Runalyze/sheet imports write them through one
  extractor, and `activity_metrics_v1` backfills the existing rows (re-reading
  the FIT archive for the old FIT payloads). Per-second streams stay in the
  archive.
- The session report and dashboard show a `Metrics` line and a running
  `Dynamics` line; `maintenance audit --fit-sample N` reports coverage, units
  and cross-source disagreements.
- On a copy of the real database the backfill produced 2,917 rows (cadence
  2,416, stride 2,356, dynamics 2,146, calories 2,877, GAP 2,234, altitude
  2,811) with `verify_canonical` still at 0 drift.

### Editing

- `activity edit <id>` is the direct human write surface: name, description,
  duration, distance, sport, sub-sport, RPE, feel, tags, workout methods and
  targets, and equipment. It needs no review item; every change is a manual
  input written through the same path as triage, and a reimport cannot undo
  it. `--clear` removes a manual value and its ownership, `--dry-run` rolls
  the whole edit back, `--history` reads the audit trail, and no edit flags
  starts an interactive field-by-field mode.
- `edit_log` (schema 26) is the append-only audit trail for manual writes
  (entity, field, old/new JSON, source, note). An item-less edit resolves the
  open `field_conflict` for a touched field and the `workout_classification`
  item after a set change; the log records which items closed.
- Manual editing now covers `name`, `description`, `sub_sport`, `rpe` and
  `feel`; clearing a manual text value restores the column default.

### Classification

- `workout_sets_current` now re-derives sets whose rows are entirely
  classifier-sourced from the current name, RPE, intensity and work reps, so
  a rename cannot leave a stale classification. Manual, sheet, Runalyze-type
  and imported sets are inputs and stay untouched; a sheet-only or merged
  sheet proposal is written as `source='sheet'` so it cannot be overwritten.
  With no classifier evidence the stored set is kept (`stale_no_evidence`).
  A reclassification opens no review item; it is a projection update.

### Duplicates

- `duplicate_candidates_current` scans the whole database for the same session
  recorded twice (same sport/day, distance within 2 %, duration within 5 %,
  average HR within 5 bpm) and opens one `duplicate` review item per pair with
  both ids. The start time is recorded but is not a gate: the sheet's minute
  time is approximate. The item is hiding until resolved.
- `sheet_duplicates_v1` is the deliberate historical cleanup: for a unique
  device candidate it copies the sheet description to a blank device row (as a
  manual value with an `edit_log` entry) and excludes the sheet row. It never
  touches a non-sheet pair; ambiguous candidates stay in review. Resolution is
  exclusion, never a merge.
- On a copy: 33 pairs (30 sheet/device, 3 other); the sheet cleanup filled 23
  descriptions, kept the device text where present, excluded 30 sheet rows and
  left 3 non-sheet duplicates for review. `verify_canonical` stayed at 0 drift.

### Historical evidence

- `hobbyjogging_import.tag_lexicon` is the one normalized tag → meaning table:
  workout sets, illness/recovery, race/trail evidence, rep lengths, sheet area
  codes, context and deliberate ignores. The audit now accounts for every
  stored tag as mapped or unmapped (157 mapped / 59 unmapped on the real DB;
  the rest are places and people), and adding a meaning is one entry.
- `workout_sets_current` fills an empty run classification from a mapped tag
  (`source='tag'`) or an explicit description (`source='comment'`) after the
  classifier/sheet/Runalyze-type proposals; a tag wins over a comment, and
  generic notes or ambiguous strength reps do not propose. On a copy this
  filled 32 historical descriptions, none of the false `3x15 Liegestütz` or
  non-run kinds.
- `illness_candidates_current` opens non-hiding `period_candidate` items for
  illness tags not covered by a stored period; `wieder gesund` closes the
  range and overlapping ranges merge. On a copy: 7 candidates from the
  `verkühlt` tags, none written as a period.
- `trail_candidates_current` opens non-hiding `consistency` items suggesting
  `trail_run` from elevation (≥40 m/km), sub-sport, the `Trail` tag and a
  supporting route name; a route name alone is not enough. On a copy: 41
  candidates. Triage `(a)ccept suggestion` writes the sport as manual.
- `consistency` and `period_candidate` are new review categories; both are
  non-hiding, so a suggestion never removes an activity from reports.

### Time and gear

- The canonical quality rules check that `started_at_utc` plus
  `tz_offset_min` lands on `local_date` and that the offset is within
  −12..+14 h. A mismatch opens one `quality` item and rewrites nothing; FIT,
  Intervals, the sheet, `review scan` and the post-edit refresh all run it.
- The activity table and session report display the recorded local start
  (`started_at_utc` + `tz_offset_min`) instead of UTC; `local_date` remains the
  local day used by every chart and range. Every started activity on the real
  DB has an offset.
- The sheet's equipment size, price, colour, legacy total km and remarks stay
  provenance text in `equipment.notes`; no typed columns, because no report or
  rule consumes them and canonical mileage comes from activity links.

### Safety

- A real maintenance run first writes a `VACUUM INTO` snapshot beside the
  database (`<db>.bak-YYYYmmddTHHMMSSZ`), keeps the last five and prints the
  path; a dry run writes no snapshot. It protects the minutes around one task,
  not the machine, and a snapshot failure aborts the run.
- `maintenance export-manual`/`import-manual` move the manual decisions as
  JSONL (manual fields, sets, tags, equipment links, exclusions, review
  answers); `maintenance rebuild --source DB` proves the canonical projection
  on a fresh schema and reports drift, missing/extra activities and the
  exclusion set.
- `maintenance audit` is the read-only historical evidence report: field and
  year coverage, unmapped raw keys and tags, interval-like descriptions, trail
  and race evidence, classification gaps and illness/season periods.

## 0.2.0 — 2026-11-24 (phase 2: works for someone else)

Schema: **25**. Compatibility: requires schema ≥ 1, migrates to 25.

### Install

- `init` creates and migrates a fresh database and the FIT directory; a second
  run only checks the schema.
- `doctor` checks `uv`, the database path and permissions, the schema version,
  the FIT directory, each configured credential, bounded API liveness probes,
  pending backfills, source freshness and `sources.toml`, and prints the next
  command.
- `sync.sh` skips a disabled source or a missing credential with a warning;
  only a configured source that fails makes it exit non-zero.
- `sync.sh` covers every configured source: Garmin, Intervals, the FIT
  archive, a budgeted Runalyze window, the offline Runalyze derivations, the
  newest unimported Strava export, the maintenance recomputes, the review scan
  and the dashboard.
- `./demo.sh` remains the zero-credential first run; `.env.example`, an MIT
  licence, a pull-request workflow (four suites plus the demo build) and
  Python 3.12+ are in place. The athlete-tuned numbers live in
  `hobbyjogging_report/defaults.py`.

### Schema and data tasks

- v25 adds `activity_intervals.source` (`intervals` or `derived`); a derived
  set from device laps never replaces a measured one.
- v24 adds `devices.excluded_at`; `TrainingRepository.devices()` lists only
  active rows.
- `device_identity_v1` re-points provider fallback devices at the FIT device
  they claim; `device_identity_orphans_v1` soft-excludes the provider rows no
  activity uses.
- `interval_source_v1` stamps the pre-v25 interval rows with
  `source='intervals'`; `derived_intervals_current` infers WORK/RECOVERY reps
  from device laps for runs with no measured set.
- `runalyze_load_current` fills an empty `training_load` from Runalyze's
  `fit_trimp`/`trimp`; Intervals outranks it in a mixed database.
- `derived_zone_configs_current` builds local HR/pace zone configs and lap
  zone times from the dated threshold snapshots; Intervals wins.

### Reports

- Device labels come from a stored name or the FIT product; the device report
  hides the soft-excluded provider rows.
- A nameless activity renders as sport plus distance ("Run 10.00 km") in the
  activity tables, race tables and the session header.
- SubT/LT1 sessions are selected from the stored targets, with the name only
  as a fallback, so a name-less athlete reaches the subT report and work reps.
- A derived interval set and its work-reps list render correctly in the
  dashboard; the subT report labels derived reps.

### Classification

- Runalyze's activity type maps Jogging, Long Slow Distance and SubThreshold to
  canonical sets on create and as a gap-filler; existing Intervals/sheet sets
  win, and `runalyze types` audits the unmapped types.

### Import

- Garmin daily wellness fills resting HR, HRV, sleep, steps, SpO2, floors and
  weight from the Personal API (fill-only; Intervals stays the owner).

### Configuration

- The source profiles declare the phase-2 capabilities (Runalyze
  `workout_type`, `trimp`; Garmin `wellness`; Intervals `intervals`), and
  `settings` renders the capability matrix, the selection, the uncovered
  record types/fields and the dashboard coverage.
- `sources.toml` can disable each optional capability (`tags`, `gear`, `races`,
  `vo2max`, `workout_type`, `trimp`, `wellness`); unknown keys fail loudly and
  a disabled capability skips only its step. `doctor` warns when the enabled
  sources cannot supply wellness, load, zones, social, reps or races.
- `threshold add --from first` anchors the snapshot on the earliest activity of
  the sport and reports how many earlier activities stay unzoned;
  `derived_zone_configs_current` prints the `no_threshold` count and the first
  snapshot date.

## 0.1.0 — 2026-11-19 (phase 1: works for me)

Schema: **23**. Compatibility: requires schema ≥ 1, migrates to 23.

- Canonical pipeline complete: FIT archive, Intervals.icu, the Garmin Personal
  API, Runalyze (activities, gear, race results, VO2max) and the Strava CSV.
- Inputs vs projections: `activity_manual_fields` (v23), a declared per-source
  mapping, `verify_canonical` (0 drift on the real database) and
  `recompute_canonical`.
- Import policy and settings (`sources.toml`, create/review/ignore, text
  targets), social text per source (v22) and race evidence.
- Reports and lab: one session renderer, the review queue, max HR/elevation,
  race pairs and Riegel anchoring; the efficiency and running-load cards.
- Four suites green; the demo deploys from GitHub Actions.
