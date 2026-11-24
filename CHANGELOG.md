# Changelog

One repo-level version; the four packages move together. A version answers
"which code built this database": the schema version, the registered data
tasks and the report surface are listed per release. Experiments, report
output and docs are not versioned.

Compatibility is stated as "requires schema ≥ N, migrates to M". The database
records its own `PRAGMA user_version`, migrations are forward-only, and
`migrate()` refuses a database newer than the code.

## Unreleased — phase 2: works for someone else

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

### Classification

- Runalyze's activity type maps Jogging, Long Slow Distance and SubThreshold to
  canonical sets on create and as a gap-filler; existing Intervals/sheet sets
  win, and `runalyze types` audits the unmapped types.

### Import

- Garmin daily wellness fills resting HR, HRV, sleep, steps, SpO2, floors and
  weight from the Personal API (fill-only; Intervals stays the owner).

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
