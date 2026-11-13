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

Nothing package-local is queued; **Runalyze enrichment** is still waiting on
the API details (below).

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
