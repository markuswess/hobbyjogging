# Next up: import package

This file records what was completed and what the package is still waiting
on.

## Done

- **Quality review dedupe.** Quality fingerprints no longer include
  `source_record_id`; `record_review_item` dedupes by
  `(category, fingerprint, activity_id)`. The source record stays on the item
  for provenance.
- **`garmin fetch`.** Personal API client with shared bearer-token cache,
  paged activity list, ZIP download, atomic FIT extraction into
  `HOBBYJOGGING_FIT_DIR/garmin`, a `source_records` manifest, `--dry-run`,
  `--limit`, `--force`, `--fit-dir`, and `--since`/`--to`/`--days`.
- **Garmin VO2max.** `fit.py` reads undocumented message 140 field 7
  (`raw * 3.5 / 65536`) into `FitSession.vo2max_garmin`; `fit_import.py`
  writes `vo2max_garmin` at full precision; the FIT summary reports coverage.
- **Intervals plan horizon.** Planned calendar events are fetched through
  `max(--to, today + --plan-days)` (default 182 days); activities and wellness
  keep the original range.
- **Triage links.** `o` opens every available link; `ci` copies the Intervals
  URL and `cg` the Garmin Connect URL (resolved from the fetch manifest by
  file path, then by start-time match). `review show` prints both.
- **Time fields.** Intervals `moving_time` is stored as `moving_s` (recording
  time stays `duration_s`); FIT `total_moving_time` is parsed when present.
  Planned events get `duration_s` from `moving_time` and `training_load` from
  `icu_training_load`. The `moving_time_mismatch` quality rule flags a gap
  larger than `max(10 min, 25% of recording)`.
- **Triage Intervals re-import.** `(t)rust Intervals` re-fetches one linked
  activity with `force=True`: Intervals takes ownership of non-manual fields,
  conflicts on those fields resolve, and quality rules re-run.
- **Recording-time duration.** Intervals `duration_s` now uses
  `icu_recording_time` (falling back to `moving_time`). A duration difference
  within either source's pause gap is agreement, so Garmin/Intervals stop-time
  accounting no longer creates review items.
- **No-distance sports.** The writer forces canonical distance to zero for
  `treadmill_run`, `virtual_run`, `soccer`, `racket`, `training`, `other`, and
  `workout`; manual distance wins, and the quality rules skip
  `zero_distance` for them.
- **Planned-events sync.** `events sync` and the regular Intervals import
  reconcile planned events: fields are replaced (including NULLs), events
  that disappeared are soft-excluded, returning events are revived,
  manual/other-source events are untouched, and the summary reports
  fetched/new/updated/unchanged/removed/revived/skipped. `--dry-run` writes
  nothing.
- **Planned-event zone times (schema v8).** Event sync parses
  `workout_doc.zoneTimes` (`Z1`–`Z7`, `SS`, zero seconds kept), infers
  `zone_kind` from the dominant step target (`pace`/`hr`/`power`) or the
  sport's natural kind, and writes via `set_event_zone_times`. An event
  without a workout document clears its kind and rows. A zone-only change
  counts as `updated`. The `event_zones_v1` backfill in
  `hobbyjogging-maintenance` repairs stored events from their saved Intervals
  payloads without network access and is idempotent.
- **Incremental `sync`.** Runs Garmin fetch, Intervals import, FIT archive
  import with `skip_known`, and the shared quality scan. `--no-*` flags skip
  sources, `--full` reimports all FIT paths, failures are reported per source
  and the command exits non-zero after continuing with the rest. The scan core
  is shared with `review scan`.
- **Field-conflict prune.** `review prune [--dry-run]` resolves open field
  conflicts whose recorded values now agree under the current core
  tolerances. FIT/Intervals reimports also resolve a field's old conflict
  automatically when that field agrees again.
- **Quality prune.** `review scan --prune` resolves open `quality` items whose
  rule no longer triggers for the activity's current values (or whose activity
  is excluded). It reuses the fingerprint identity of
  `record_quality_findings`, reports `checked/resolved/kept` with
  `--dry-run`, leaves the other review categories alone, and is idempotent.
- **Conflict causes and bulk triage.** New `field_conflict` items carry a
  `cause`/`cause_note` computed from the stored source summaries (`causes.py`).
  Advisory causes (`elapsed_definition`, `moving_estimate`, `small_difference`,
  `start_offset`) are `info`; the rest stay `warn` and need a per-activity
  decision. `review causes`, `review classify [--dry-run]`, `--cause` filters
  on `list`/`triage`, and `review resolve --cause <cause> [--dry-run]` support
  the workflow.
- **Race categories.** `event_methods` maps Intervals `RACE_A`/`RACE_B`/
  `RACE_C` onto the canonical `race` method during event sync. It is public so
  the maintenance `event_race_method_v1` backfill can re-derive the method for
  events that predate the mapping.
- **Spreadsheet import.** `sheet` reads the hand-maintained `.ods` log with a
  standard-library ODS reader (`ods.py`), maps the German columns
  (`Rohdaten`, `Alternativtraining`, `Material`), links shoes, and keeps the
  raw row in `source_records.payload_json`. Start times are matched at
  minute precision; matched activities keep their precise start, and rows
  without a start create dated activities. Imports are stable and idempotent.
- **Empty Intervals artifact.** `is_empty_interval` in `intervals.py` drops the
  trailing 1 s / 0 m `RECOVERY` row Intervals appends when building the stored
  interval list; genuine short segments (2 s or any distance) survive. The raw
  payload keeps the original rows. The maintenance `drop_empty_intervals_v1`
  backfill reused the predicate and removed the existing rows (239 across 235
  activities).
- Full FIT archive import, VO2max backfill, and the historical spreadsheet
  import have been run against the real DB.

## Next

- **Activity edit command.** The human write surface next to triage: a general
  `hobbyjogging activity edit <id>` that edits name, description, RPE, feel,
  sub-sport, tags, classification and equipment without a review item, with
  `--clear`, `--dry-run`, `--history`, and an interactive mode. Every field
  writes manual provenance, reuses `apply_manual_edit` for the quality
  re-check, and records an `edit_log` row. It shares triage's write path, so it
  must also close the open `field_conflict` for a touched field and the
  `workout_classification` item when the sets change; move `_VALUE_PROMPTS`
  into `values.py` so both use one prompt table. See root item 1; the logic
  stays in this package until a front end justifies an app package.
- **Consistency audit** (`review scan --rules consistency`). A dataset-wide
  scan for contradictions between the stored classification and the evidence,
  producing `consistency` review items (info, non-hiding) with a suggestion in
  `context_json` and a triage `(a)ccept` action that writes the suggestion as
  manual. Evidence-gated and conservative.
  **The exact rule set and thresholds are still to be determined** — the rules
  below are measured candidates, not a committed set; settle them (and the
  90% / 40 m/km / 5 min / 150 bpm / 90 min thresholds) before implementing.
  **Prerequisites**: the trail rule needs elevation (root item 5) and the
  vo2max rule needs the per-sport VO2max fix (root bug) — without them the
  evidence is wrong (482 rides carry a running VO2max), so implement the audit
  after those land.
  Measured yields:
  - `intervals` but the WORK reps cover >90% of the activity → suggest
    `continuous` (38), or `fartlek` when the reps are irregular.
  - `intervals` with **no usable WORK reps** (170) → a `missing_reps`
    data-gap item (info), **not** a reclassification: the session was
    structured, the device data is absent. Only suggest `fartlek` when the
    name or the sheet `fs` code says so.
  - `run` with ≥40 m/km lap elevation → suggest `trail_run` (9); also use
    `sub_sport` (`trail`, `mountain`, `treadmill`) as evidence.
  - `race` but no event within ±1 day, inside calendar coverage → suggest
    dropping `race` (1); `sub_sport='RACE'` is supporting evidence.
  - `vo2max` but no WORK rep ≤5 min → suggest `threshold` (6).
  - `recovery` target with avg HR ≥150 → suggest `base` (3).
  - `long_run` under 90 min → suggest dropping it (2).
  - `intervals`+`threshold` without a sustained WORK block → suggest `tempo`
    (1).
  Rules fire only when the evidence exists; ungated, the counts explode with
  history artefacts (162 / 45 / 69). A changed suggestion supersedes the old
  item.
- **Duplicate/overlap detection.** Flag two activities that are the same
  session: same sport, overlapping start (±15 min) or same day, distance
  within ~2%, and HR within 5 bpm when both have it. Emit a `duplicate` review
  item carrying both activity ids; resolve by excluding one. Runs in the
  quality scan, idempotent by a fingerprint over the sorted pair.
- **Fartlek instead of intervals for the sheet `fs` code.** `SHEET_TYPE_CODES`
  maps `fs` to `intervals` with no target today, which is how 54 historical
  fartleks ended up in the intervals bucket (38 with zero WORK reps). Map it to
  `fartlek` + `vo2max` once the core method exists, and add the
  `fahrtspiel` / `fartlek_run` aliases.
- **Athlete thresholds and zone configs.** Write `athlete_thresholds`
  snapshots and `zone_configs` rows (reusing identical boundaries) and set the
  activity FKs, from `athlete_max_hr`, `lthr`, `LTHRdetected`,
  `threshold_pace`, `icu_hr_zones` and `pace_zones`. Treat zero and
  implausible threshold paces as absent.
- **VO2max by sport.** FIT message 140 field 7 is written to every activity
  regardless of sport; a ride file carries ~60 fields (`unknown_43..67`) where
  a run file carries ~30, so the sport-specific value should be identifiable
  there. Detect the sport the value describes, write it only to a matching
  activity, and stop stamping the running value onto rides and swims. See the
  root VO2max bug.
- **Max HR and weather capture.** Write the FIT session max HR, Intervals
  `max_heartrate`, the sheet's `max. Hf`, and the Intervals weather block
  (`average_temp`, `average_feels_like`, `average_wind_speed`,
  `average_wind_gust`, `average_clouds`) plus the sheet's `Temperatur in °C`.
  Depends on the core `activities.max_hr` column and the `activity_weather`
  table.
- **Wellness extras and routes.** Map the selected wellness keys into the new
  columns and the sheet's `Strecke`/`Streckennummer` into routes, once the core
  migrations land.
- **Device capture.** Parse FIT `file_id` (manufacturer, product, serial) into
  the core device registry and link the activity as `recorder`; normalize
  Intervals `device_name` (`GARMIN ENDURO` / `Garmin Enduro`, `EDGE_540` /
  `Edge 540`) to the same product and link with `source='intervals'`, letting
  the FIT link win. Depends on the core `devices` / `activity_devices`
  migration.

- **Committed FIT fixture.** `test_fit` reads `data/fit/*.fit`, which is
  gitignored, so on CI every real-file test skips (they now guard with
  `skipUnless`) and the parser is only covered by synthetic messages. Commit
  one sample under `tests/fixtures/` and point the tests at it, so CI parses a
  real file. A FIT carries timestamps, HR and possibly GPS, so this is a
  privacy call even in a private repo; the alternative is a synthetic encoder
  for the test only.
- **`init` and `doctor`.** `hobbyjogging-import init` creates and migrates a
  fresh database explicitly (today the first import does it implicitly), and
  `doctor` checks the DB path and writability, the schema version, the FIT
  directory and the credentials, printing what is missing. See root item 23.
- **Move `SHEET_TYPE_CODES` here.** The German `Trainigstyp` mapping for one
  personal ODS lives in `hobbyjogging_core.workouts`; move it into this
  package so the canonical vocabulary is not shaped by one spreadsheet.
  Maintenance already depends on import, so its backfills keep working.

**Runalyze enrichment** is still waiting on the API details (below).

## Waiting on

- **Runalyze enrichment** (blocked on API auth/endpoint details): comments
  merged into `description`, tags in `activity_tags`, gear via the
  equipment-categories endpoint, and `vo2max_runalyze`.
  - **Gear / equipment**: gear records become
    `source_records(record_type='gear')` plus `equipment` rows, and activities
    link through `activity_equipment` with `source='runalyze'`. Cross-source
    identity reuses `equipment_source_links`: link a gear record to an
    existing item when its activities consistently carry the same sheet shoe
    (co-occurrence), else on a unique normalized brand+model match, else open
    an `ambiguous_equipment` review item — never guess (the two "Lunge C-Dur"
    pairs differ only by colour and date). 2022+ gear has no sheet
    counterpart and simply creates new rows.
  - **Race results**: Runalyze `race_result` supplies placing, category,
    participants, conditions and often the proper race name (today's rows are
    generically named "10k Race"). Store it on the race link/event; the
    activity already holds time and distance.
- The dashboard is reports-package work.
- The planned-event zone display is reports-package work.

## Notes / risks

- Message 140 is undocumented; Garmin can strip it. The VO2max line in the FIT
  import summary is the early warning.
- The Personal API activity FIT is byte-identical to the GDPR archive copy
  (4/4 activities tested in November 2026). The JSON `vO2MaxValue` is null;
  the type-44 `max_met_data` files are not needed.
- The manifest is a bandwidth optimization. The FIT importer is
  checksum-idempotent, so a redownload does not duplicate source records or
  laps.
