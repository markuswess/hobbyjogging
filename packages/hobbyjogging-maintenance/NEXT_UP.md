# Next up: maintenance package

This file records what the package is still waiting on.

## Done

- **Recurring workout-set derivation.** `workout_sets_current` is a
  `recompute` task that derives methods/targets for activities that have none,
  using the same classifier/sheet helpers as the backfill. It fills gaps only:
  any activity with sets from any source (manual, backfill, classifier) is
  skipped, so triage decisions and the one-time backfill are never fought.
  Disagreements stay empty and are left to `workout_classification_queue`.
  `sync.sh` runs both after a successful sync (`--no-classify` skips them);
  the full-DB run takes about half a second.
- **`event_race_method_v1`.** Re-derives the `race` method for every event
  linked to an Intervals record, adding it where the payload category is
  `RACE_A/B/C` and removing a stale non-manual row otherwise; manual rows win.
  Applied to the real DB: 2 events gained the method (Baden Stadtlauf, Linz
  Marathon 2026), 648 unchanged.
- **`drop_empty_intervals_v1`.** Drops the 1 s / 0 m `RECOVERY` artifact
  Intervals appends (and the rare `WORK` one) from every stored interval set,
  reusing `hobbyjogging_import.intervals.is_empty_interval` so it cannot drift
  from the import filter. It keeps the set's existing interval source record,
  is idempotent, and leaves excluded activities and activities without
  intervals alone. Validated on a copy and applied to the real DB: 239 rows
  dropped across 235 of 2,836 activities with intervals, no activity cleared,
  and a forced rerun changed nothing.

## Next

- **`wellness_extras_v1`** (backfill). Fill the new wellness columns from
  the stored Intervals wellness payloads (3,022 days), idempotent, dry-run.
- **`activity_routes_v1`** (backfill). Map the sheet's `Strecke` /
  `Streckennummer` to routes and link the activities.
- **`activity_max_hr_v1`** (backfill). Fill `activities.max_hr` from the
  stored payloads (FIT session, Intervals `max_heartrate`, sheet `max. Hf`),
  owner-based with a 2 bpm tolerance, manual untouched. Idempotent, dry-run,
  and it reports coverage per source and year.
- **`activity_weather_v1`** (backfill). Create `activity_weather` rows from the
  Intervals weather block and the sheet's `Temperatur in °C`, idempotent,
  dry-run.
- **`activity_devices_v1`** (backfill). Once the core device tables and the
  importer writes land, create devices and activity links from the stored
  payloads: FIT `file.manufacturer/product/serial_number` as `recorder`,
  Intervals `device_name` normalized to the same product. Idempotent;
  `--dry-run`; never touches manual links.
  - Tests: device creation from FIT and Intervals, FIT-over-Intervals
    precedence, a rerun is a no-op, dry-run writes nothing, manual links
    survive.

Nothing else queued. New data work registers a task here instead of a script.

## Waiting on

Nothing. The package owns schema evolution, backfills, recomputes, and their
bookkeeping.
