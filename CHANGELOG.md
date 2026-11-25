# Changelog

One repo-level version; the four packages move together. A version answers
"which code built this database": the schema version, the registered data
tasks and the report surface are listed per release. Experiments, report
output and docs are not versioned.

Compatibility is stated as "requires schema ≥ N, migrates to M". The database
records its own `PRAGMA user_version`, migrations are forward-only, and
`migrate()` refuses a database newer than the code.

## Unreleased — phase 3: trustworthy data

Schema: **28**. Compatibility: requires schema ≥ 1, migrates to 28.

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
