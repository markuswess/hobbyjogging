# Next up: import package

No open import-package tasks. This file records what was completed and what
the package is still waiting on.

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
- Full FIT archive import and VO2max backfill have been run against the real
  DB.

## Next task: planned-events sync (schema v7)

Core is done: `events.excluded_at`, `upsert_event` replaces fields (including
NULLs) and revives excluded events, `exclude_event` / `restore_event`, and the
repository filters excluded events.

Implement in this package:

- `IntervalsImporter.sync_events(start, end, *, dry_run=False)`:
  1. fetch current events via `client.events(start, end)`;
  2. upsert each with the current fields (`duration_s` from `moving_time` with
     `duration` fallback, `training_load` from `icu_training_load`,
     `distance_m`, date/name/type/description);
  3. collect the fetched Intervals event ids;
  4. query DB events joined to `source_records` where `source='intervals'`,
     `record_type='event'`, `local_date BETWEEN start AND end`,
     `excluded_at IS NULL`;
  5. soft-exclude DB events whose external id is not in the fetched set;
  6. revive fetched events that had been excluded;
  7. report fetched / new / updated / removed / revived; `--dry-run` writes
     nothing;
  8. write an `import_runs` row with `events_sync`, start, end, `plan_days`.
- Refactor the event portion of `import_range` to call the same sync/prune
  logic with `start..plan_end`, so a regular Intervals import cannot leave
  stale plans.
- CLI: `hobbyjogging-import events sync [--plan-days 182] [--from DATE --to
  DATE] [--dry-run]`; default window today .. today + plan_days.
- Only events linked to Intervals source records are pruned; manual and other
  source events stay untouched.
- Tests: new/changed/cleared fields, moved date, deleted → excluded,
  recreated with new id, reappeared → revived, dry run, other-source event
  untouched, regular import prunes, idempotent re-sync.

Note: event `duration_s` means planned moving time; activities `duration_s`
means recording time.

## Waiting on

- **Runalyze enrichment** (blocked on API auth/endpoint details): comments
  merged into `description`, tags in `activity_tags`, gear via the
  equipment-categories endpoint, and `vo2max_runalyze`.
- **`review scan` prune mode**: resolving stale quality items whose current
  values no longer trigger them (not implemented yet).
- The dashboard is reports-package work.

## Notes / risks

- Message 140 is undocumented; Garmin can strip it. The VO2max line in the FIT
  import summary is the early warning.
- The Personal API activity FIT is byte-identical to the GDPR archive copy
  (4/4 activities tested in November 2026). The JSON `vO2MaxValue` is null;
  the type-44 `max_met_data` files are not needed.
- The manifest is a bandwidth optimization. The FIT importer is
  checksum-idempotent, so a redownload does not duplicate source records or
  laps.
