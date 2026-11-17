# Next up: maintenance package

This file records what the package is still waiting on.

## Done

- **`race_links_current`.** Matches each race event to an activity on the same
  date and sport within 5% distance, writes `event_activity_links` and derives
  the `race` method under `race_link`. A manual link or manual method set wins;
  two candidates open an `ambiguous_race` review item. Applied: 2 links
  (Linz Marathon 2026, Baden Stadtlauf 2025), 2 methods added; runs in
  `sync.sh`.
- **`activity_routes_v1`.** Resolves the sheet's `Strecke`/`Streckennummer`
  into routes (number first, then the name's number when unambiguous) and
  links the matched activity. Applied: 36 routes and 384 links; name-only
  variants and Gmap URLs are handled without guessing.
- **`wellness_extras_v1`.** Filled weight, sleep score and quality, SpO2,
  steps, floors climbed and CTL/ATL from the wellness payloads, with the
  sheet's `Gewicht nachher` as a weight fallback. Applied: 3,167 days; weight
  358, sleep score 1,493, SpO2 155, steps 966, CTL/ATL 3,022.
- **`training_periods_current`.** Derives seasons, illness ranges and notes
  from the Intervals event payloads, closing each season the day before the
  next. It reads `end_date_local` inclusive (falling back to the start), so a
  source range is kept and never invented. Applied: 3 seasons, 25 illness
  ranges, 4 note ranges; runs in `sync.sh`.
- **`activity_device_v1`.** Created the devices from the FIT
  `file.manufacturer/product/serial_number` and filled `activities.device_id`,
  with Intervals `device_name` only where FIT left it empty. Applied: 2,853
  activities across 6 devices; 1,295 pre-2019 rows have none.
- **`athlete_thresholds_current` and `activity_zone_configs_current`.** Derive
  the per-sport threshold snapshots and the zone configs from the Intervals
  payloads, then point each activity at the config of its era. Recomputes, so
  they run in `sync.sh` after every import. Applied: 51 snapshots across 21
  sports (14 for running, threshold pace 4.587 → 4.854 m/s), 11 zone configs,
  2,848 activities linked to an HR config and 2,230 to a pace config.
- **`activity_weather_v1`.** Created `activity_weather` rows from Intervals
  `average_temp` and the sheet's `Temperatur in °C`, first source owning the
  row. Applied to the real DB: 3,002 activities (2,823 Intervals, 179 sheet).
- **`activity_elevation_v1` and `activity_max_hr_v1`.** Filled the v12 columns
  from the stored payloads in import order (Intervals, FIT, sheet), through the
  writer so ownership and tolerances hold. Applied to the real DB: 3,287
  activities with elevation (2,802 with loss), 3,394 with max HR; 62 and 29
  source disagreements counted, not queued.
- **`drop_classification_tags_v1`.** Removed the sheet's `Trainigstyp` codes
  from `activity_tags`, keeping manual tags and the training-area labels.
  Applied to the real DB: 874 tags from 869 activities; 1,015 area tags remain.
- **`fartlek_from_fs_v1`.** Converted the sheet-`fs` activities from
  `intervals` to `fartlek`, filling a missing target with `vo2max` and skipping
  manual rows entirely. Applied to the real DB: 60 activities, 40 converted,
  20 kept manual methods, 34 targets filled.
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

- **`thresholds_from_races_v1`** (backfill, idea — the race links exist now;
  still blocked on the lab work settling the derivation). Derive per-era threshold pace
  and LTHR from linked race results, fill the activities where Intervals has
  no `threshold_pace`, and record the derived series next to the stamped one
  so the reports can show both. Idempotent, dry-run, and it reports the delta
  to the stamped values.

Nothing else queued. New data work registers a task here instead of a script.

## Waiting on

Nothing. The package owns schema evolution, backfills, recomputes, and their
bookkeeping.
