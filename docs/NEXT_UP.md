# Status and next steps

Updated 2026-11-12.

## Done

- **Canonical pipeline.** FIT archive, Intervals.icu, and Garmin Personal API
  import into one SQLite database with raw-source provenance, temporal
  matching, and owner-based field precedence (no per-source priority).
- **Review & editing.** Interactive triage, manual field overrides, durable
  exclusion, ambiguous-match linking, field-conflict pick value (`v`), forced
  Intervals re-import (`t`), and Intervals/Garmin activity links (`ci`/`cg`).
- **Sources.** Garmin `fetch` downloads original FITs into the archive;
  API-downloaded FITs are byte-identical to the GDPR export. VO2max is read
  from FIT message 140 into `vo2max_garmin`.
- **Schema v5/v6.** `vo2max_garmin`/`vo2max_runalyze` owners, `activity_tags`,
  `activities.moving_s`, and `events.training_load` (with backfill).
- **Schema v7.** `events.excluded_at`; the repository hides excluded events.
  `upsert_event` now replaces event fields (including NULLs) and revives an
  excluded event; `exclude_event`/`restore_event` support the sync prune.
- **Schema v8.** `events.zone_kind` and `event_zone_times` store the planned
  zone distribution (`Z1`–`Z7`, `SS`); the repository exposes it on `Event`.
- **Planned-events sync.** `events sync` (and the regular Intervals import)
  reconciles the calendar: fields are replaced (including NULLs), events that
  disappeared are soft-excluded, reappearing ones are revived, and only
  Intervals-linked events are touched. `--dry-run` writes nothing.
- **One-command sync.** `hobbyjogging-import sync` (wrapped by `./sync.sh`)
  runs Garmin fetch → Intervals import → FIT scan (skipping known paths) →
  quality review scan, continues past a failing source, and exits non-zero at
  the end.
- **Event zone times.** `workout_doc.zoneTimes` is stored in
  `event_zone_times` with an inferred `zone_kind` (pace/HR/power); the event
  sync replaces/clears them and the `event_zones_v1` backfill populated the
  existing payloads (2,808 rows).
- **Time fields.** Intervals `moving_time` → `moving_s`; FIT
  `total_moving_time` is parsed when present; event duration comes from
  `moving_time` and `training_load` from `icu_training_load`. The
  `moving_time_mismatch` rule flags gaps above `max(10 min, 25%)`.
- **Time authority.** `moving_s` and `elapsed_s` are Intervals-authoritative
  and never produce review items; `duration_s` remains owner-tracked.
- **Quality dedupe.** Review items dedupe by
  `(category, fingerprint, activity_id)`, not by source record.
- **Historical spreadsheet.** `hobbyjogging-import sheet` imports the
  hand-maintained `.ods` log (`Rohdaten`, `Alternativtraining`, `Material`)
  through a standard-library ODS reader, with German column mapping,
  minute-precision start matching, shoe links, tags, and the normal
  owner/conflict review rules. Equipment upsert/link methods are in the
  writer.
- **Reports.** Markdown reports (daily/overview/weekly/monthly/yearly, period,
  year/month comparison, subT, session, activities table), charts, and the
  terminal renderer; report code is split per report.
- **Reports: pace zones.** The time chart stacks actual and planned pace
  zones; planned zone distributions appear as hatched weekly bars and the
  EWMA panel continues through them as dashed projections. Extra zones fold
  into the last displayed zone and `SS` is ignored.
- **Reports: VO2max chart.** Garmin running VO2max appears as daily dots
  with 7- and 42-day exponentially weighted averages.
- **Workout classification (schema v9).** Set-based methods/targets on
  activities and events; quality is derived from methods/targets. The
  classifier + sheet backfill classified 2,687 activities (including 107
  easy defaults for sheet runs with no code and HR < 140) and tagged 56;
  216 conflicts were left unclassified for review.
- **Duration tolerance settled.** A FIT/Intervals recording-time difference
  now counts as the same measurement when it fits inside either source's
  pause gap or is within 5% (the cause classifier's "small difference" bound);
  trims, manual Intervals edits, and sheet estimates still open a review item.
- **`tempo` retired.** A tempo run is `continuous` with a `threshold`
  target, so the method duplicated the target. `remove_tempo_method_v1`
  converted 185 activities; the token now normalizes to `continuous`.
- **Workout classification in the review queue.** Disagreements between the
  classifier and the sheet are now `workout_classification` review items
  (`info`), synced by a `recompute` task, resolved in triage with `(k)`, and
  never hidden from reports.
- **Reports read the stored classification.** `classify()` prefers
  `activity_workout_methods/targets` and falls back to the heuristic when an
  activity is unclassified, so manual resolutions now change reports and the
  dashboard (589 activities changed category). The backfill calls it with
  `use_stored=False` so it never reads back its own output.
- **Reports: one data source.** The direct Intervals.icu API source was
  removed; reports read the canonical database only, and `debug` dumps the
  payloads stored in `source_records`.
- **Schema evolution workflow (schema v10).** Two tracks: immutable SQL
  migrations in core, and registered data tasks in the new
  `hobbyjogging-maintenance` package (`backfill` = applied once and recorded;
  `recompute` = re-runnable re-derivation). The runner uses one transaction per
  run, a dry run executes for real and rolls back, and `maintenance_runs`
  records every run. `event_zones_v1` and `workout_classification_v1` are the
  first registered tasks; the old ad-hoc scripts are gone.
- **Static dashboard.** `dashboard.sh` writes a self-contained static site
  (overview with 7/42/182-day hard/total EWMAs and running volume by intensity
  group, recovery and health, activities list, activity detail, data health,
  and selected Markdown reports converted to HTML) with embedded plotly
  charts, bundled `plotly.min.js`, and atomic directory swaps. It opens the
  browser; `sync.sh` regenerates the same site without opening one.
- **Reports: planned workouts.** The `planned` report starts tomorrow and ends
  with weekly-average total time and Z3+4 time per 7 days.
- **Recurring workout-set derivation.** `workout_sets_current` (a maintenance
  `recompute`) derives methods/targets for activities that have none, using
  the same classifier/sheet helpers as the one-time backfill. It fills gaps
  only, so manual decisions and the backfill are never touched;
  disagreements stay empty for `workout_classification_queue`. `sync.sh` runs
  both after a successful sync (`--no-classify` skips them); a full-DB run
  takes about half a second. The 2026-11-10 "Easy" run is now
  `continuous`/`recovery`.
- **Public demo on GitHub Pages.** `./demo.sh` builds the synthetic database
  and the site; `.github/workflows/pages.yml` rebuilds and deploys it weekly
  and on demand. Live at
  <https://markuswess.github.io/hobbyjogging/>, verified.
- **Dashboard review queue.** The health page lists the open `ReviewItem`
  rows (severity, category, detail, activity, date) through
  `DataSource.review_items`.
- **Session report completeness.** The session report and the dashboard detail
  page show tags, both VO2max owners, review status and open items, the day's
  planned workout, the day's wellness, and the lap table;
  `DataSource.activity_laps` exposes the repository query.
- **Efficiency (m/excess beat).** Meters per heartbeat above the 365-day
  resting baseline: session, activities column, subT work reps/tables/panel,
  subT EWMA, compare tab, and the Markdown reports; the pace/HR scatter draws
  it beside the regression. See `docs/METRICS.md`.
- **Classifier in core.** The workout-category heuristic moved to
  `hobbyjogging_core.classify` (Category, classify, work_intervals, rep-length
  buckets); the reports package keeps only the display aggregation
  (`category_breakdown`). `hobbyjogging-maintenance` now depends on core and
  the importers, not on the renderer.
- **Race method backfill.** `event_race_method_v1` applied the
  `RACE_A/B/C → race` mapping to existing events: 2 gained the method (Baden
  Stadtlauf, Linz Marathon 2026), 648 unchanged, manual rows untouched.
- **Empty interval artifact.** The Intervals importer no longer stores the
  1 s / 0 m trailing `RECOVERY` interval, and `drop_empty_intervals_v1` removed
  the rows left by earlier imports: 239 rows across 235 of 2,836 activities
  with intervals, none cleared; the set's interval source record is kept and a
  forced rerun is a no-op.
- **Real data.** Full FIT archive import and Garmin VO2max backfill have run
  against the real database (4,143 activities, 2,805 with a Garmin VO2max;
  650 events with 2,812 planned zone rows). The historical spreadsheet import
  added the 2009–2021 log (1,292 activities, 10 equipment items, 1,842 shoe
  links). The review queue is empty.

## Next

1. **Derive the display category from the stored sets** (core + reports).
   `classify()` currently re-derives the category from name, duration and
   intervals even when the activity is classified, so the display contradicts
   the canonical sets for **142 of 2,903 classified activities (4.9%)**: races
   over 90 min show as `longrun` (7), `continuous`+`threshold` shows as
   `intervals/other` (76) or `longrun` (18), `long_run` shows as `tempo` (12),
   `intervals` as `longrun` (10), warmups as `race-support` (13).
   - **Core**: add `category_for_sets(methods, targets)` next to
     `classification_for_category` — the inverse mapping, with a fixed
     priority: `race` → race, `long_run` → longrun, `intervals`/`progression`
     → intervals, `continuous`+`threshold` → tempo, `continuous`+`recovery` →
     recovery, `continuous` → easy, empty → unknown. It must round-trip
     with `classification_for_category` for every mapped pair; the only
     intentional ambiguity is `{continuous}, {base}`, which is `easy` (the
     name-based race-support override handles warmups).
   - **Reports**: `classify()` uses `category_for_sets` whenever
     `activity.quality is not None`; the heuristic runs only for unclassified
     activities (488 `unknown` + 743 cross-training today). Keep exactly two
     documented display refinements applied afterwards:
     - `subt-short/medium/long` from the work reps when methods contain
       `intervals` and the target is `subthreshold`;
     - `race-support` from the name for warmup/cooldown.
   - **Not stored**: rep length and race-support stay read-time derivations.
     They cover 134 and 13 activities; storing them would duplicate the
     intervals/name and drift like the current category does.
   - **Acceptance**: no classified activity gets a kind that contradicts its
     sets; `Activity.quality` and `Category.quality` always agree; the
     unclassified fallback is unchanged; the breakdown table and the
     `category` column keep their current labels.
   - **Tests**: round-trip mapping for every `classification_for_category`
     case; the 142 mismatches resolve to the stored kind; a marathon-length
     race stays `race`; a `continuous`+`threshold` session shows `tempo`; a
     warmup still shows `race-support`.
   - **Docs**: the reports README taxonomy section and the ARCHITECTURE
     `classify.py` bullet.

2. **Link planned races to activities and propagate the `race` method**
   (core + maintenance). The classifier only reads the name, so the two past
   planned races are misclassified: the 2026 Linz Marathon (42.45 km, 2:37:49)
   is `long_run` and the 2025 Baden Stadtlauf 10k is `intervals`, although both
   have a race event on the same day. Only 8 of the 45 race activities have a
   same-day event.
   - **Next migration**: `event_activity_links(event_id, activity_id,
     match_method, confidence, linked_at)` — a table, not a column, because a
     race day can also have warmup/cooldown activities.
   - **Matching** (`race_links_current`, a maintenance recompute): date + sport,
     then distance within ~5% (42.20 vs 42.45 km), then start-time proximity.
     Ambiguous candidates open an `ambiguous_race` review item instead of
     guessing.
   - **Propagation**: for each linked race event, ensure the activity carries
     the `race` method with a non-manual source; manual sets always win, so a
     deliberate change survives.
   - **Plan vs actual** comes free: the event already stores planned
     distance/duration/load/zones.
   - **Split**: core owns the table, migration, model and repository;
     maintenance owns the recompute; reports consumes the link for the race
     report.
   - **Tests**: distance tolerance, ambiguous → review item, manual methods
     untouched, idempotent, dry-run.

3. **Elevation gain and loss on activities** (core + import + maintenance).
   Per-lap FIT elevation is stored (`activity_laps.elevation_gain_m`, 2,800
   activities), but `activities` has no elevation column. The payloads cover
   81% of activities: Intervals `total_elevation_gain` / `_loss` (2,846), the
   sheet's `m bergauf` (839, gain only), and FIT session `total_ascent`
   (parsed, not stored; `total_descent` not parsed at all). FIT and Intervals
   agree closely — median 0.4%, p90 5.3% on the 2,755 activities with both —
   so there is no authority fight.
   - **Schema v11**: `activities.elevation_gain_m` and
     `activities.elevation_loss_m`, both nullable.
   - **Importers**: FIT session `total_ascent` / `total_descent` (parse the
     descent), Intervals `total_elevation_gain` / `_loss`, sheet `m bergauf`
     (gain only).
   - **Ownership**: owner-based like distance, with a wide tolerance (10% or
     20 m) because the sources are estimates; manual wins. Intervals authority
     is the fallback if conflicts turn out to be noisy.
   - **Backfill `activity_elevation_v1`** (maintenance): fill existing rows
     from the stored payloads (Intervals, sheet) and from summed FIT laps, no
     network, idempotent, `--dry-run`.
   - **Uses**: the trail suggestion rule (9 candidates at ≥40 m/km), climb per
     km in the session report and activity list, coarse grade-adjusted pace
     from per-lap gain, and route difficulty on the dashboard.
   - **Tests**: FIT/Intervals/sheet parsing, the tolerance agreement, the
     backfill idempotency, and `loss` staying `NULL` for sheet-only rows.

4. **Maximum HR per activity** (core + import + maintenance). There is no
   canonical column today, though Intervals `max_heartrate`, the FIT session
   and the sheet's `max. Hf` (1,233 rows) all carry it.
   - **Next migration**: `activities.max_hr`, nullable, owner-based with a
     small tolerance (2 bpm); manual wins.
   - **Import**: FIT session max HR, Intervals `max_heartrate`, sheet
     `max. Hf`.
   - **Backfill `activity_max_hr_v1`** from the stored payloads.
   - **Uses**: HR-zone accuracy, interval intensity, and the existing >205 bpm
     sensor-fault cause reading the canonical value; a session-report line.
   - **Coverage**: report how many activities gain it, per source and year,
     before deciding whether the column earns its place.

5. **Per-activity weather** (core + import + maintenance + reports).
   Intervals carries `average_temp`, `average_weather_temp`,
   `average_feels_like`, `average_wind_speed`, `average_wind_gust` and
   `average_clouds` (2,847 activities); the sheet has `Temperatur in °C`
   (766). Weather is the biggest pace/HR confounder we ignore today.
   - **Explore first, in the lab**: how much temperature and wind explain pace
     and HR variance, and whether an "adjusted pace" is worth it.
   - **If it earns its place**: a small `activity_weather` row per activity
     (`temp_c`, `feels_like_c`, `wind_speed_ms`, `wind_gust_ms`, `clouds_pct`,
     `source`) rather than five columns on `activities`; importers write it and
     `activity_weather_v1` backfills from the payloads.
   - **Uses**: heat/wind annotations on pace, HR and efficiency charts;
     comparing similar efforts across conditions.

6. **Athlete thresholds and zone configs** (core + import + maintenance +
   reports). The Intervals payloads carry the athlete's settings per activity:
   `athlete_max_hr` (192), `lthr` (174, drifting 172–180), `LTHRdetected`,
   `threshold_pace` (**4.59 → 4.85 m/s = 3:38 → 3:26/km** across 2019–2026),
   and the zone boundaries `icu_hr_zones` (`[135,156,174,192]`) and
   `pace_zones` (`[73,83,100,999]` %). None of it is stored, and
   `zone_configs` plus the activity FK columns are empty dead schema.
   - **Zone configs**: reuse `zone_configs(id, kind, source,
     boundaries_json)`, one row per distinct snapshot, and set
     `activities.pace_zone_config_id` / `hr_zone_config_id`. Zone times then
     mean the same thing across eras.
   - **Thresholds**: a small dated `athlete_thresholds` snapshot table
     (`effective_from`, `max_hr`, `lthr`, `threshold_pace_mps`, `source`)
     rather than columns on activities — they belong to the athlete and change
     slowly.
   - **Import**: write both from the payloads; treat `threshold_pace` 0 and
     implausible values (e.g. 0.83) as absent.
   - **Backfills**: `athlete_thresholds_v1`, `activity_zone_configs_v1`.
   - **Reports**: a threshold trend chart (LTHR, threshold pace, max HR) beside
     VO2max, era-correct zone normalization, and subT work-rep pace compared
     with the period's threshold pace.
   - **Races as threshold evidence** (idea, depends on item 2's race links).
     Intervals' stamped values are athlete settings, not measurements, and
     `threshold_pace` is missing on ~1,400 activities. A race is the best
     observed evidence we have: a 10k–half marathon result gives a defensible
     threshold pace (via Riegel-style adjustment for the distance) and LTHR
     (the sustained HR of the last third). A `thresholds_from_races_v1`
     backfill would derive a per-era series from linked race results and use it
     to (a) fill the gaps, (b) cross-check the stamped values, and (c) emit a
     consensus series where they disagree. It also yields HR/pace zone
     boundaries for eras with no `icu_hr_zones`. **The derivation rule set,
     the race-distance window and the tolerances are still to be determined** —
     start in the lab against the existing stamped values before storing
     anything.
   - **Validation**: Intervals' threshold pace and the subT-derived pace should
     agree; report the delta.

7. **Wellness beyond HRV, resting HR and sleep** (core + import +
   maintenance + reports). Intervals wellness carries 47 keys; we store three.
   The useful extras: `readiness`, `sleepScore`/`sleepQuality`, `stress`,
   `respiration`, `spO2`, `mood`, `soreness`/`fatigue`, `steps`,
   `floorsClimbed`, `weight`, and Intervals' `ctl`/`atl`.
   - **Next migration**: `wellness_days` gains the selected nullable columns.
   - **Import**: map the Intervals wellness payload; Runalyze later.
   - **Backfill `wellness_extras_v1`** from the stored payloads (3,022 days).
   - **Reports**: a readiness view (readiness, sleep score, stress,
     respiration, spO2), a weight trend, and steps/floors as non-training
     activity.
   - Start with the four with the best signal-to-noise — readiness,
     sleepScore, stress, respiration — and leave the rest behind a flag.

8. **Route identity and grouping** (core + import + maintenance + reports).
   The sheet has `Strecke` / `Streckennummer` (389 / 360 rows) and a Gmap link
   (993), but the canonical model has no route. FIT payloads carry no GPS
   streams, so historical route identity can only come from the sheet.
   - **Next migration**: `routes(id, name, external_ref, notes)` and
     `activity_routes(activity_id, route_id, source, source_record_id,
     is_manual)` — a table, since one run can cover several routes.
   - **Import/maintenance**: map `Strecke` (with `Streckennummer` as the
     stable key) to routes and link the activity; `activity_routes_v1`
     backfills from the sheet payloads.
   - **Reports**: group activities by route so pace, HR and efficiency compare
     like-for-like; a route page with its best efforts.
   - **Open**: GPS-derived routes for the FIT era would need stored streams,
     which do not exist today.

9. **Device registry and per-activity device** (core + import + maintenance +
   reports). The sources already carry the device: FIT
   `file.manufacturer/product/serial_number` (fr645 2019–2022, enduro
   2022–2026, edge_540 2025–2026, fr945 once, 2 "connect" uploads) and
   Intervals `device_name` with the same four devices in mixed casing. Nothing
   before 2019 (the sheet has no device column), and `vo2max_garmin` from FIT
   message 140 differs per watch algorithm without being attributable.
   - **Next migration**: `devices(id, type, manufacturer, product,
     serial_number, name, acquired_on, retired_on, notes)` and
     `activity_devices(activity_id, device_id, role, source,
     source_record_id, is_manual)`. Device id
     `fit:<manufacturer>:<product>:<serial>`; Intervals-only devices
     `intervals:<slug>`. `role` is `recorder` in v1 (the table leaves room for
     `hrm`).
   - **Import**: FIT parses `file_id` (already in the payload) → upsert the
     device and link the activity; Intervals normalizes `device_name` to a
     product and links with `source='intervals'` (FIT wins on conflict).
     Sheet: nothing.
   - **Maintenance**: `activity_devices_v1` backfills devices and links from
     the stored payloads, idempotent, `--dry-run`.
   - **Pre-2019 gap**: manual assignment only (a `devices assign --from --to
     --device` command or a triage action writing manual links); never infer
     from a date range.
   - **Reports**: the equipment page becomes "Gear & devices" with active
     periods, counts and a device timeline; the VO2max chart marks device
     changes; the session report shows `- Device: …`.
   - **Tests**: FIT/Intervals parsing and normalization, FIT-over-Intervals
     precedence, backfill idempotency, manual links surviving.

10. **Runalyze enrichment** when the API auth/endpoint details are settled:
   comments merged into `description`, tags, gear via the
   equipment-categories endpoint, `vo2max_runalyze`. Unmatched rows create
   activities. The gear half includes cross-source equipment identity
   (`equipment_source_links`, co-occurrence matching, review items for
   ambiguity); see the import `NEXT_UP`.
11. **Homelab cutover**: DB + importer + dashboard generator + static server,
   periodic backups, Tailscale/basic auth.
12. **Reports backlog** — handed to the reports session; the list lives in
   `packages/hobbyjogging-reports/NEXT_UP.md`: the equipment report and tab
   (including devices), the race report plus Performance tab, and the Docs
   tab.
13. **Raw vs derived: document the tiers and add a check** (low priority). The
   tiers already exist structurally — raw `source_records`, canonical
   `activities`/`events` columns, derived set/zone tables, read-time metrics —
   but the invariant is implicit: a derived stored value is always recomputable
   from raw + manual and never outranks manual. Add a short ARCHITECTURE
   section and a read-only maintenance `check` task (the kind cut from the
   runner) asserting that derived rows have a known origin, manual rows survive
   recomputes, and a recompute reproduces the same sets. No schema change; a
   `computed_by` column only if a queryable need appears.

Triage is empty (0 open items), all four suites are green, and the demo
deploys from GitHub Actions.

## Notes

- Reports hide activities with open review items by default
  (`--include-review` shows them); excluded activities never appear.
- `events sync` defaults to today .. today + 182 days; `--from`/`--to`
  override the window, and `--dry-run` reports without writing.
- `./sync.sh` runs the incremental sync (Garmin → Intervals → FIT → review
  scan) and then regenerates the dashboard; `--no-garmin`, `--no-intervals`,
  `--no-fit`, `--no-scan`, and `--no-dashboard` skip those steps.
- `./dashboard.sh` regenerates the dashboard and opens `index.html` in the
  browser; `--no-open` or `NO_OPEN=1` suppresses the browser.
- The `planned` report always starts tomorrow.
- Reports use `duration_s` (recording/timer time) for pace and time.
  `moving_s` is stored for provenance and the `moving_time_mismatch` rule
  only; it is not a report denominator.
- The Garmin key is valid for 30/90/180/365 days; each run exchanges it for a
  24 h bearer token.
- Runalyze's activity payload exposes no Garmin activity id, so matching stays
  temporal.
