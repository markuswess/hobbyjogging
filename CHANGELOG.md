# Changelog

One repo-level version; the four packages move together. A version answers
"which code built this database": the schema version, the registered data
tasks and the report surface are listed per release. Experiments, report
output and docs are not versioned.

Compatibility is stated as "requires schema ≥ N, migrates to M". The database
records its own `PRAGMA user_version`, migrations are forward-only, and
`migrate()` refuses a database newer than the code.

## Unreleased — phase 3: trustworthy data

Schema: **26**. Compatibility: requires schema ≥ 1, migrates to 26.

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

### Safety

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
