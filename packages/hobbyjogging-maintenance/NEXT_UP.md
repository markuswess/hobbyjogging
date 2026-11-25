# Next up: maintenance package

This file records what the package is still waiting on.

## Done

- **Duplicate detection and sheet cleanup.** `duplicate_candidates_current`
  opens one hiding item per same-session pair and closes stale ones;
  `sheet_duplicates_v1` copies a sheet-only duplicate's description to a blank
  device row and excludes the sheet row. On a copy: 30 sheet pairs cleaned,
  23 descriptions filled, 3 non-sheet duplicates left for review, 0 canonical
  drift.
- **Pre-run snapshots.** A real `run` writes a `VACUUM INTO` snapshot beside
  the database, keeps the last five and prints the path; a dry run and a
  skipped backfill write none. A snapshot failure aborts the run. It protects
  the minutes around one task, not the machine.
- **Illness and trail candidates.** `illness_candidates_current` opens
  non-hiding `period_candidate` items for illness tags outside a period
  (7 on a copy; `wieder gesund` closes the range); `trail_candidates_current`
  opens non-hiding `consistency` items suggesting `trail_run` from elevation,
  sub-sport, the `Trail` tag and a supporting route name (41 on a copy).
  Neither writes the proposed value.
- **Session metrics.** `activity_metrics_v1` fills the session-average row
  from the stored payloads and the FIT archive (the archive is re-read for the
  old FIT payloads). The audit gained a coverage/unit/conflict section with a
  `--fit-sample` option.
- **Historical audit.** `maintenance audit` is a read-only Markdown report of
  the evidence already stored: field coverage per year, unmapped raw keys and
  tags, interval-like descriptions, trail/race evidence, classification gaps,
  illness/season periods and the review queue. On the real DB it found 289
  unmapped raw keys, 195 unmapped tags, 1,227 unclassified activities and 41
  trail candidates. It opens no review items and writes nothing.
- **Manual overlay and rebuild.** `export-manual` writes the manual decisions
  as JSONL (73 manual fields, 529 manual set records, 8 exclusions and 734
  review answers on the real DB); `import-manual` re-applies it to a database
  with the raw/structural layer. `rebuild --source DB` copies the raw records,
  identities, links, pointers, devices and equipment into a fresh schema,
  applies the overlay, runs `recompute_canonical` and diffs every canonical
  value and the exclusion set; it also checks the FIT archive files. On a copy
  of the real DB: 4,149 activities, 91,278 values, 0 drift, 8/8 exclusions,
  2,864 FIT files present. It does not re-import or re-match.
- **`verify_canonical`.** A read-only recompute that derives every owned
  activity field from its manual value, owner patch or source pointer and
  compares it with the stored value. On the real DB: 4,143 activities, 68,001
  fields, **0 drift, 0 dangling, 0 unmapped**. Run it before trusting a
  rebuild.
- **`recompute_canonical`.** Projects every owned activity field from its
  manual value, owner patch or pointer and writes it back through
  `project_activity_field`. On the real DB it is a no-op: 68,001 fields, 0
  written, 0 dangling. Ownership is never re-decided.
- **`race_links_current`.** Matches each race event to an activity on the same
  date and sport within 5% distance, writes `event_activity_links` and derives
  the `race` method under `race_link`. A non-excluded official `race_results`
  row is evidence too, so the years before the Intervals calendar are covered;
  the method is dropped when neither an event link nor a result remains. A
  manual link or manual method set wins; two candidates open an
  `ambiguous_race` review item. Applied: 2 event links (Linz Marathon 2026,
  Baden Stadtlauf 2025) and 18 result-backed methods, so all 37 official
  results now carry `race`; runs in `sync.sh`.
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
  `recompute` task that now re-derives activities whose sets are entirely
  classifier-sourced (from the current name, RPE, intensity and work reps)
  and fills the remaining unclassified gaps; a classifier proposal that
  differs replaces the set. Manual, sheet, Runalyze-type and imported sets
  are inputs and stay untouched, and a sheet-only or merged sheet proposal is
  written as `source='sheet'` so a later re-derivation cannot overwrite it.
  With no classifier evidence the stored set is kept and counted
  `stale_no_evidence`; disagreements stay empty for
  `workout_classification_queue`. `sync.sh` runs both after a successful sync
  (`--no-classify` skips them). Seeded stale live example: `intervals` +
  `subthreshold` became `intervals` + `lt1`; a second run was unchanged.
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
- **`device_identity_v1`.** Re-resolves every activity still on a provider
  fallback through the import device rule. Applied: 3 activities — Ramsau
  Surfing and Vienna Cycling now carry `fit:garmin:enduro:3386253273`,
  Höchst Other is cleared, and the two 2019 Garmin Connect rows stay NULL. The
  canonical check now resolves a provider name through the same unique-FIT
  claim, so `verify_canonical` stays at 0 drift and `recompute_canonical` is a
  no-op. The two provider rows it left unused were soft-excluded by
  `device_identity_orphans_v1`.
- **`device_identity_orphans_v1`.** Soft-excluded the two provider device rows
  no activity uses (`intervals:garmin-enduro`, `intervals:runalyze`) after the
  FIT claim moved their last activities. `devices.excluded_at` (v24) and the
  `TrainingRepository.devices()` filter hide them; applied: 2 excluded, the
  four FIT devices remain.
- **`interval_source_v1`.** Stamped the 14,680 interval rows that predate
  schema v25 with `source='intervals'`, so a derived set from device laps can
  coexist without overwriting them. Applied; a rerun changes nothing.
- **`derived_intervals_current`.** Infers WORK/RECOVERY reps from device laps
  for a run with no measured set, gated by the stored intervals type or a
  strong lap-pace spread; run-only, idempotent, and written with
  `source='derived'`. On the real DB it derives nothing (the structured runs
  already carry Intervals sets), which is the expected conservative result.
- **`runalyze_load_current`.** Fills an empty `training_load` from Runalyze's
  `fit_trimp`/`trimp` under `source='runalyze'`; `training_load` now ranks
  Intervals before Runalyze, so a mixed database keeps the Intervals value.
  Applied: 15 historical runs gained a load, 2,815 Intervals values were kept,
  and `verify_canonical` stayed at 0 drift.
- **`derived_zone_configs_current`.** Builds local HR/pace configs from the
  threshold snapshot in force on each activity's date (LTHR or max-HR shares;
  threshold-speed shares for pace) and sums lap zone times. Applied to the
  real DB: 242 activities gained a local config, 99 gained lap zone times,
  2,238 kept their Intervals config and 1,201 predate the first snapshot.
  `threshold add|list` is the manual write surface; a manual snapshot survives
  every recompute.

## Next

- **`thresholds_from_races_v1`** (backfill, idea — the race links exist now;
  still blocked on the lab work settling the derivation). Derive per-era threshold pace
  and LTHR from linked race results, fill the activities where Intervals has
  no `threshold_pace`, and record the derived series next to the stamped one
  so the reports can show both. Idempotent, dry-run, and it reports the delta
  to the stamped values.

- **Canonical rebuild** (root item 17). `verify_canonical` (read-only diff) and
  `recompute_canonical` (dry-run first) land here, on top of the manual input
  layer and the per-adapter mapping. The fresh-database proof and the manual
  overlay are done (root item 34); they derive activity scalar fields from the
  stored pointer and payload, apply manual edits last, and never touch links,
  exclusions, review answers, child tables or entity rows.

Nothing else queued. New data work registers a task here instead of a script.

## Waiting on

- **Historical refurbishment.** The read-only audit is done; the proposal
  rules (classification, trail, illness, seasons) wait for the landed
  `activity edit` surface and the lab calibrations.

Nothing else. The package owns schema evolution, backfills, recomputes, and
their bookkeeping.
