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

## Bugs

- **VO2max is per sport, we store one series.** Garmin reports VO2max per sport,
  but `activities.vo2max_garmin` is filled from FIT message 140 field 7 on
  **every** activity regardless of sport: 482 rides, 22 swims, 21 trail runs,
  plus walks, skis and a sail carry a value. Measured against nearby runs, the
  ride values differ by **+1.70 on average (range −0.52 .. +3.67)**, so they
  are a different series, not noise — yet the reports draw one VO2max line and
  the audit rules read one value.
  - **Investigate**: message 140 carries ~30 fields in a run file and ~60 in a
    ride file (`unknown_43..67` appear only for cycling), so the sport-specific
    value may be identifiable there; also check whether Intervals exposes more
    than its single `VO2MaxGarmin`, and whether `vo2max_runalyze` is a running
    value by definition.
  - **Fix**: record the sport the value describes (`vo2max_garmin_sport`, or a
    per-sport key) and attach a value only to an activity whose sport it
    actually describes. Running stays the primary series; cycling becomes its
    own.
  - **Backfill**: re-key or clear the values on non-running activities once the
    sport discriminator is known.
  - **Reports**: label the series "Running VO2max", keep it to running
    activities, and add the cycling series when it exists.
  - **Tests**: a ride no longer inherits the running value, the run series is
    unchanged, and the chart labels the sport.

## Next

1. **Activity editing, CLI first** (core + import). The only manual write
   surface is `review edit`, which changes `duration_s`, `distance_m` and
   `sport`, and only with a review item attached. Name, description, RPE, feel,
   sub-sport, tags, classification and equipment have no free-form edit, no way
   to clear a value, and no history — `activity_field_sources` stores only the
   current owner and value, so there is nothing to undo against.
   - **Command**: `hobbyjogging activity edit <id>` with explicit flags
     (`--name`, `--description`, `--rpe`, `--feel`, `--sub-sport`, repeatable
     `--tag`, `--method`, `--target`, `--equipment`), plus `--clear <field>`,
     `--dry-run`, `--history`, and an interactive mode that prompts field by
     field with the current value as the default. A review item is never
     required.
   - **Provenance**: every field goes through `TrainingWriter.set_manual_field`
     (`is_manual=1`, `source='manual'`), so a reimport cannot undo it; `sport`
     still normalizes through `core.sports`; the sets go through
     `set_manual_activity_workout_methods` / `_targets`. **`MANUAL_FIELDS`
     currently rejects `name`, `description`, `rpe`, `feel` and `sub_sport`**,
     so that tuple has to grow first — `set_manual_field` raises for every one
     of those flags today.
   - **Quality**: reuse `apply_manual_edit`, which re-runs the quality rules and
     prints the findings that still stand.
   - **Relationship to triage**: both surfaces share one write path —
     `apply_manual_edit` → `set_manual_field` + `refresh_activity_quality` — so
     provenance and the quality re-check never diverge. Triage stays the
     contextual surface (sources, `(v)` pick value, `(t)` trust Intervals,
     `(ci)`/`(cg)` links, `(d)` exclude, `(k)` classification proposals); edit
     is the direct surface and must not grow those actions. Only
     `duration_s`/`distance_m`/`sport` and the classification sets genuinely
     duplicate, which is intended: `_VALUE_PROMPTS` covers exactly three
     fields, and `(k)` adds the proposals the raw `--method`/`--target` cannot.
   - **Item lifecycle fix**: `refresh_activity_quality` only closes
     `category=quality` items, and `prune_field_conflicts` only closes a
     conflict whose *recorded* current/incoming values agree — it knows nothing
     about a manual override. An item-less edit therefore leaves the matching
     `field_conflict` open forever. `apply_manual_edit` must also resolve open
     `field_conflict` items for the touched `(activity, field)` and open
     `workout_classification` items when methods/targets are written; `--item`
     then becomes a convenience, not a requirement. `edit_log` records the
     resolved item id so the history explains the closure.
   - **Prompt table**: move `_VALUE_PROMPTS` from `triage.py` to `values.py`
     so the interactive edit mode and triage share one prompt/parser table.
   - **Notes and comments — settle the home first.** Three designs exist for
     user-authored text: Runalyze merges comments into `description`, Strava
     gets its own table (item 16), and the independence item plans an
     append-only `activity_notes`. Pick one before any of them ships:
     `description` (one editable blob per activity, no history) or a notes
     table (multiple timestamped notes, per source, the audit trail the edit
     log already argues for). The edit CLI and the reports line depend on the
     answer.
   - **Edit log (new)**: `edit_log(entity_kind, entity_id, field, old_json,
     new_json, source, note, created_at)`, append-only, written in the same
     transaction as the edit. `activity_field_sources` is a snapshot, not a
     history; independence later means the database has to carry the audit
     trail a platform would have kept. `--history` reads it, and events and
     wellness reuse it.
   - **Placement**: keep it in the import CLI for now — `editing`, `values`,
     `quality` and `causes` already live there. When the front end starts,
     extract a `hobbyjogging-app` package and move those modules behind it, the
     same move the classifier made to core once it had a second consumer.
   - **Front end (later, same package)**: localhost only — the database is
     single-writer (WAL, 5 s busy timeout) and unauthenticated, so it must never
     be exposed. The CLI stays the reference implementation: if the UI needs
     something the CLI cannot do, the CLI is wrong.
   - **Tests**: a manual edit survives a reimport; `--clear` removes the value
     and its manual ownership; `--history` shows the prior value; `--dry-run`
     writes nothing; quality findings print; an empty interactive answer keeps
     the current value; tags/methods/targets replace as sets; an item-less edit
     closes the matching `field_conflict` and leaves other fields' items open;
     a classification edit closes the `workout_classification` item; `--item`
     still resolves explicitly.
   - **Docs**: the ARCHITECTURE role list gains the human write surface, and
     the import README documents the command.

2. **Bring back `fartlek` for unstructured quality** (core + import +
   maintenance + reports). `intervals` has become a mixed bucket: of the 561
   activities carrying it, **170 have zero WORK reps** and 22 have 1–2, 47
   have no target, and 40 spend >75% of the session in WORK. The sheet code
   `fs` (Fahrtspiel) is the proof: **60 activities, 54 now `intervals`, 38 of
   them with zero WORK reps**.
   - **The distinction to preserve**: `fartlek` means *never structured*;
     `intervals` means *structured reps intended*, even when the device data
     is missing. Relabelling the latter would lie about the session, so
     missing reps stay `intervals` and become an audit data-gap item instead.
   - **Core**: add `fartlek` to `WORKOUT_METHODS` and `QUALITY_METHODS`; it is
     mutually exclusive with `intervals`, and it always makes a session
     quality. Map `fs` to `fartlek` + a `vo2max` target in `SHEET_TYPE_CODES`,
     and add the aliases (`fahrtspiel`, `fartlek_run`).
     `category_for_sets` returns the new `quality/fartlek` kind (item 3).
   - **Backfill `fartlek_from_fs_v1`**: rewrite the sheet-`fs` activities from
     `intervals` to `fartlek` (source `backfill`, skip manual rows), leaving
     their targets alone except for filling a missing one with `vo2max`.
     Idempotent and dry-run.
   - **Reports**: a `fartlek` label in the breakdown and the category column;
     exclude it from the subT rep-length buckets and every rep-count/duration
     analysis by construction (it has no reps to measure). The `tempo`-style
     read-time fallback must not turn a fartlek into `intervals`.
   - **Why this does not contradict the `tempo` retirement**: `tempo`
     duplicated the target (continuous + threshold); `fartlek` expresses
     structure, which the target axis cannot say.
   - **Tests**: `fs` maps to fartlek+vo2max; fartlek is quality; fartlek never
     round-trips to `intervals`; the 54 fs rows convert and manual rows do not;
     the subT buckets ignore fartlek.

3. **Derive the display category from the stored sets** (core + reports).
   `classify()` currently re-derives the category from name, duration and
   intervals even when the activity is classified, so the display contradicts
   the canonical sets for **142 of 2,903 classified activities (4.9%)**: races
   over 90 min show as `longrun` (7), `continuous`+`threshold` shows as
   `intervals/other` (76) or `longrun` (18), `long_run` shows as `tempo` (12),
   `intervals` as `longrun` (10), warmups as `race-support` (13).
   - **Core**: add `category_for_sets(methods, targets)` next to
     `classification_for_category` — the inverse mapping, with a fixed
     priority: `race` → race, `long_run` → longrun, `fartlek` → fartlek,
     `intervals`/`progression` → intervals, `continuous`+`threshold` → tempo,
     `continuous`+`recovery` → recovery, `continuous` → easy, empty → unknown.
     `quality/fartlek` is a **new display kind** (item 2), deliberately not
     folded into `intervals/other`, so rep-based analyses stay clean. It must
     round-trip with `classification_for_category` for every mapped pair; the
     only intentional ambiguity is `{continuous}, {base}`, which is `easy`
     (the name-based race-support override handles warmups).
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
     `fartlek` session shows `quality/fartlek` and never enters the subT or
     rep-length buckets; a warmup still shows `race-support`.
   - **Docs**: the reports README taxonomy section and the ARCHITECTURE
     `classify.py` bullet.

4. **Link planned races to activities and propagate the `race` method**
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

5. **Elevation gain and loss on activities** (core + import + maintenance).
   Per-lap FIT elevation is stored (`activity_laps.elevation_gain_m`, 2,800
   activities), but `activities` has no elevation column. The payloads cover
   81% of activities: Intervals `total_elevation_gain` / `_loss` (2,846), the
   sheet's `m bergauf` (839, gain only), and FIT session `total_ascent`
   (parsed, not stored; `total_descent` not parsed at all). FIT and Intervals
   agree closely — median 0.4%, p90 5.3% on the 2,755 activities with both —
   so there is no authority fight.
   - **Future schema**: `activities.elevation_gain_m` and
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

6. **Maximum HR per activity** (core + import + maintenance). There is no
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

7. **Per-activity weather** (core + import + maintenance + reports).
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

8. **Athlete thresholds and zone configs** (core + import + maintenance +
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
   - **Races as threshold evidence** (idea, depends on item 4's race links).
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

9. **Wellness beyond HRV, resting HR and sleep** (core + import +
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

10. **Route identity and grouping** (core + import + maintenance + reports).
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

11. **Device registry and per-activity device** (core + import + maintenance +
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

12. **Runalyze enrichment** when the API auth/endpoint details are settled:
   comments merged into `description`, tags, gear via the
   equipment-categories endpoint, `vo2max_runalyze`. Unmatched rows create
   activities. The gear half includes cross-source equipment identity
   (`equipment_source_links`, co-occurrence matching, review items for
   ambiguity); see the import `NEXT_UP`.
13. **Homelab cutover**: DB + importer + dashboard generator + static server,
   periodic backups, Tailscale/basic auth.
14. **Platform independence** (long-term, dormant; ingestion unchanged). The
    goal is to stop depending on Intervals.icu as the *system of record* — not
    to stop using it as transport. The trigger is a paywall or wanting out, so
    nothing here starts now: Garmin, Intervals and FIT ingestion stay exactly
    as they are.
    - **Acceptance test**: for every action taken in Intervals today there is a
      local equivalent, and a reimport cannot undo it.
    - **What is missing**: events are Intervals-authoritative (`upsert_event`
      replaces every field including NULLs, removal soft-excludes), wellness has
      no owner tracking, there is no notes/comments table, and planned workouts
      carry methods/targets/zones but no step list.
    - **Phases**, in order: owner-tracked events (`event_field_sources`, manual
      wins, a new `AGENTS.md` rule) → notes/comments (`activity_notes`,
      append-only) → planned-workout steps and authoring → subjective wellness
      ownership → thresholds/zones (item 8) → the front end from item 1 →
      Garmin/FIT ingest so Intervals becomes optional.
    - **Parked decisions**: whether programmed workouts are followed on the
      watch (which would need a `.fit` workout export and upload) or the lap
      button is enough — the 370 intervals activities with ≥3 WORK reps suggest
      the latter; and whether the front end ever replaces the CLI.
    - **Edit history** from item 1 is a prerequisite, not an extra: without it,
      dropping the platform also drops the audit trail.

15. **Reports backlog** — handed to the reports session; the list lives in
   `packages/hobbyjogging-reports/NEXT_UP.md` and is kept current there rather
   than duplicated here.
16. **Strava titles, descriptions and links** (core + import + reports; low
    priority). Strava is the social layer: the title is a pun, the description
    sometimes a note, while the Intervals title is the workout name. Both are
    worth keeping, and they must not compete — `name` is deliberately not a
    conflict field, so a Strava import writing it would be ignored (Intervals
    names are never blank) or open thousands of review items.
    - **Schema**: `activity_strava(activity_id PRIMARY KEY, external_id,
      title, description, source, source_record_id, is_manual, updated_at)` —
      a table like `activity_equipment` and the planned device/weather/route
      tables, not columns on `activities`: source-specific metadata, not a
      canonical metric. `external_id` is the Strava activity id, from which
      `https://www.strava.com/activities/<id>` is derived for the link.
    - **Classifier isolation**: the Strava title never enters `classify()` — a
      pun ("Race you to the bakery") must not match the `race`/`tempo`/`lt1`
      keywords. Keeping it out of `activities.name` makes that structural.
    - **Import, CSV first**: the Strava bulk export (`activities.csv`) matched
      on start time (±2 min) and distance (±2%), unmatched rows left alone,
      checksum-idempotent. Titles and descriptions only: Strava
      distance/time/HR would add a third source competing for ownership with no
      benefit.
    - **API, deferred**: OAuth with a client secret and refresh token, 100
      requests per 15 min and 1,000/day — only if the CSV proves the titles are
      wanted continuously.
    - **Reports**: a `Strava: …` line under the workout name in the session
      report, the description as an annotation, and the link to the activity —
      the same pattern as the triage `(ci)`/`(cg)` links. Not in the activities
      table, where a second line costs row height.
    - **Tests**: CSV parsing, the ±2 min / 2% match, an unmatched row writing
      nothing, a pun never affecting the classification, the URL derived from
      the id, and a reimport not duplicating the row.

17. **Raw vs derived: document the tiers and add a check** (low priority). The
   tiers already exist structurally — raw `source_records`, canonical
   `activities`/`events` columns, derived set/zone tables, read-time metrics —
   but the invariant is implicit: a derived stored value is always recomputable
   from raw + manual and never outranks manual. Add a short ARCHITECTURE
   section and a read-only maintenance `check` task (the kind cut from the
   runner) asserting that derived rows have a known origin, manual rows survive
   recomputes, and a recompute reproduces the same sets. No schema change; a
   `computed_by` column only if a queryable need appears.

18. **Official race results** (core + import + reports). Race results, PBs,
   and the Riegel fit currently use GPS distance/time because there is no
   official race metadata. `events.distance_m` is a planned/announced
   distance, not a result, and `activities.distance_m` is the measured
   GPS value — neither should be overwritten.
   - **Future schema**: `race_results(id, activity_id, event_id,
     official_distance_m, official_time_s, placing, participants, notes,
     source, source_record_id, excluded_at, created_at, updated_at)`, with
     `UNIQUE(activity_id)`; both official columns are nullable. Race results
     get their own record so the official and measured values stay separate.
   - **Core**: model + `DataSource.race_results()` +
     `TrainingWriter.upsert_race_result` (replace or insert; provenance and
     exclusion rules follow the usual canonical pattern).
   - **Import/manual entry**: a small CLI (`race-result add`/`edit`) or a
     triage action writes the row; the fields are optional so a partial result
     can be entered now and completed later.
   - **Reports**: PBs, the Riegel fit, and distance buckets use
     `official_distance_m` + `official_time_s` when both exist and fall back to
     the activity's measured values otherwise. The race report shows both the
     official and GPS values so a mismatch is visible. The computed pace uses
     one consistent pair, never a mix.
   - **Relationship to race links**: this does not require `event_activity_links`
     (item 4); the row is keyed by activity. A later link can enrich it with
     the event's planned distance/zone metadata.
   - **Tests**: writer idempotency, `race_results()` returns the stored row,
     PB/bucket/Riegel prefer official values, the GPS fallback is unchanged,
     and the race report shows both values.
   - **Docs**: the reports README's race section.

19. **Retire the redundant sheet tags** (core + import + maintenance + reports).
    `activity_tags` still holds the sheet's `Trainigstyp` codes — 890 `w`,
    278 `r`, 166 `i`, 130 `ll`, 99 `tdl`, 60 `fs`, 51 `m`, 44 `b`, 38 `lt`,
    33 `u` — which the stored method/target sets now encode. Reports only print
    them, and the classifier never reads them.
    - **Decide**: keep tags for genuinely orthogonal labels (`hills`,
      `bad data`) and drop the classification codes, or retire the table.
    - **Backfill `drop_classification_tags_v1`**: remove the classification
      codes, keep manual tags and the orthogonal ones; idempotent, dry-run.
    - **Import**: stop writing the codes; keep the sheet's free tags.
    - **Reports**: the session Tags line keeps working for what remains.
    - **Tests**: the codes drop, `hills` survives, manual tags are untouched,
      a rerun is a no-op.

20. **Intervals' own metrics as a cross-check** (lab first, then reports; low
    priority). The payload carries `decoupling`, `efficiency_factor`,
    `icu_intensity` and `icu_variability_index`, computed independently of
    ours. Compare them with our efficiency and intensity on the same activities
    to catch a formula bug before adding another derived number. Follows the
    metrics gate: a lab script first, a card only if it earns one.

21. **Sheet leftovers** (import + reports; low priority). `equipment.notes`
    holds size, price and colour from the sheet and is never parsed;
    `tz_offset_min` is populated on the activities and unused. Parse the notes
    into typed equipment fields (or leave them as text) and use
    `tz_offset_min` where local time matters — chart day boundaries and session
    times. Decide per field whether it earns a place.

22. **Release versioning** (repo-level; no package). Every `pyproject.toml` says
    `0.1.0` and never changes, and there are no tags, so "which code built this
    database" is unanswerable. The *data* contract already exists — `PRAGMA
    user_version`, immutable ordered migrations, and `migrate()` refusing a
    database newer than the code — so only the code version is missing.
    - **Triggers**: the homelab cutover (item 13), where scheduled syncs and
      ad-hoc reports can run two code versions against one DB; a second
      installation; any destructive migration; and the published demo, which
      already ships output without provenance.
    - **Shape**: one repo-level semver tag (the four packages move together),
      a `CHANGELOG.md` with schema/data-task/report sections and a
      compatibility line ("v0.4 requires schema ≥10, migrates to 10"), and a
      GitHub release note. **No PyPI** — private workspace, no consumer.
      Pre-1.0 while the schema moves; 1.0 only once a second person's data is
      on it.
    - **Cadence**: not time-based — tag now for the current state, then at each
      schema bump and milestone.
    - **Not versioned**: experiments, report output, docs.
    - **Checklist instead of tests**: suites green, changelog written, DB
      backed up before the migration, tag pushed.

23. **Portability for a second user** (core + import + reports + CI). The model
    is already portable — canonical activity, owner-based fields, no
    per-source priority, the migration machinery, the importers, reports over
    `DataSource`, the synthetic demo. What is personal is the defaults.
    - **Blocking**: no `init`/`doctor` (a new user must infer that the first
      import creates and migrates the DB, and nothing checks the paths,
      credentials or schema version up front); test CI only covers pushes to
      `main` through the demo workflow, so there is no pull-request check;
      `requires-python >= 3.14` with no 3.14-only syntax found, so the floor
      can likely drop to 3.12.
    - **Personal constants in the analysis**: fixed chart ceilings
      (`VOLUME_Y_MAX`, `TIME_Y_MAX`, `LOAD_Y_MAX` — a 130 km/week axis for a
      40 km/week athlete), `COMPARE_VISIBLE_YEARS = 5`, the 2009 colour anchor,
      `RACE_DAYS = 180`. Make the ceilings a "nice max" from the data.
    - **The sheet shapes the core**: `SHEET_TYPE_CODES` (German `Trainigstyp`
      codes for one personal ODS) lives in `hobbyjogging_core.workouts`; it
      belongs in the import package so the canonical vocabulary is not shaped
      by one spreadsheet.
    - **Thresholds as defaults, not laws**: RPE > 3, 90-min long run, 40-min
      recovery, subT 4/7-min buckets, 5-bpm HR conflict, 10 %/20 m elevation.
      Document them as defaults and keep them in one module.
    - **Missing one-file fixes**: no `LICENSE`, no `.env.example`; the README
      starts at `data/fit` without saying how files get there (Garmin GDPR
      export, or Intervals-only).
    - **Out of scope, state it**: multi-athlete (one athlete per DB), imperial
      units, a hosted service, arbitrary platforms.
    - **Order**: cheap first — LICENSE, `.env.example`, `init`/`doctor`, a
      pull-request test workflow, the README first-run path; then the
      data-driven ceilings and the sheet-code move; then the Python floor.

24. **Catalogue every metric and analysis tool** (docs + reports; idea). The
    registry only documents what came through the lab gate, so most of what the
    reports actually compute is undocumented: load EWMAs, zone shares, session
    RPE, race buckets and Riegel, the VO2max EWMAs, the robust wellness bands,
    the classifier, the work-interval filter, the matching and tolerance rules.
    The goal is a reference catalogue of everything in use, with a source for
    each, distinct from the promotion gate.
    - **Two jobs, two homes.** `docs/METRICS.md` stays the registry (gate,
      promoted, rejected); the catalogue is a separate document (working name
      `docs/ANALYSIS.md`) so a reader does not confuse "how a metric earns its
      place" with "what a metric means".
    - **Three classes with different reference styles**: *metrics* (a number:
      efficiency, load, IF, zone share), *methods* (the classifier, the
      work-interval filter, race matching, the owner/tolerance rules) and
      *statistics* (EWMA, median/MAD, split-half reliability, regression). Each
      entry: definition, formula, source or "coaching convention", where it
      renders, and its caveats.
    - **References**: cite the origin where one exists (Riegel 1981 for the
      endurance formula; Foster 2001 for session RPE; Coggan/Allen for
      CTL/ATL/TSB and IF; Seiler for polarization; Daniels for VDOT; Friel for
      decoupling; Minetti for the grade cost model; Plews/Buchheit for HRV).
      Mark coaching conventions explicitly rather than inventing a citation —
      the load EWMAs and m/beat are conventions, not papers.
    - **Anti-drift**: either generate the list from one registry in the reports
      package and render Markdown and HTML from it, or keep it hand-written
      with a test asserting every `analysis/` module is mentioned and every
      named module still exists. Prefer the second unless the first proves
      cheap; prose does not generate well.
    - **Dashboard**: a "Metrics" tab rendering the catalogue grouped by area
      (load, intensity, efficiency, races, wellness, tools) with anchors, next
      to the existing Docs tab. Formulas must render without new runtime
      dependencies — plain Unicode/code blocks, or bundle KaTeX if the site
      stays self-contained.
    - **Open questions**: one doc or two; catalogue at metric level or
      report level; whether the review rules and the import tolerances belong
      in it (they are tools, not metrics); and whether the lab's candidate
      table should link into the catalogue.
    - **Acceptance**: every number a report shows is either catalogued or
      explicitly listed as plumbing; every entry names the module that
      computes it; no entry describes code that no longer exists.

25. **LLM coaching workflow** (root + reports). The workflow exists but lives
    outside the repo: another model reads the Markdown reports and plans through
    a terminal agent, discusses them, and writes a coaching note as Markdown
    that could be shown in the dashboard. Nothing defines where that note lives,
    what shape it has, or how the dashboard finds it. ARCHITECTURE already plans
    a deterministic "LLM coaching bundle" and an append-only decision log; this
    item makes the real workflow first-class and feeds that plan.
    - **Notes**: a `coaching/` directory of committed Markdown notes, one file
      per session, with front matter (`date`, `period`, `focus`, linked
      events) and sections (state, assessment, decision, next). The decision
      section *is* the append-only decision log ARCHITECTURE asks for.
    - **Input**: the model reads reports through the CLI on demand (`session`,
      `period`, `races`, `plan`) rather than a giant dump. A
      `reports.sh coaching-bundle` command would emit a compact digest — goals,
      planned events, load and recovery trends, key sessions, explicit caveats
      — plus pointers, bounded in size and reproducible for a date range.
    - **Continuity**: a session starts by reading the last N notes, so a
      recommendation and whether it was followed carries over; the next note
      records the outcome.
    - **Write safety**: the model never writes the database. Reports stay
      read-only and the only write is the note file.
    - **Dashboard**: a Coaching tab with the latest note rendered and an index
      of past ones, through the Markdown-to-HTML path the Docs tab already
      uses. The public demo builds from the synthetic database and must not
      ship real notes — exclude `coaching/` when a demo label is set, or ship a
      synthetic example.
    - **Later**: plans authored as events instead of prose, which ties into the
      platform-independence item.
    - **Open questions**: committed notes or local-only; one file per session
      or per week; JSON, Markdown or both for the bundle; and whether the tab
      is "Coaching" or part of "Docs".

26. **Keep the demo data current** (reports; recurring). The synthetic demo is
    now both the public face and a smoke test — it builds in CI on every
    relevant push. But `demo.py` predates the newest features, so a tab or chart
    that reads a new field (max HR, elevation, weather, devices, routes, Strava
    notes, thresholds and zones, fartlek) renders empty and the demo stops
    proving the feature works.
    - **Rule**: a change that adds a user-visible field, chart or tab updates
      `demo.py` in the same work; the demo build is part of the acceptance
      check, and it already runs in CI.
    - **Coverage check**: a `demo-db --check` (or a test) asserting that every
      report and dashboard tab renders non-empty content from the demo
      database, so a feature without demo data fails loudly instead of showing
      a blank card.
    - **Recurring review**: at each release tag (item 22) and schema bump,
      re-read the feature list against the demo and fill the gaps. Keep the seed
      fixed so the output stays deterministic and diffable.
    - **Open**: how realistic the synthetic athlete should be — a plausible
      build, a taper, a race, a couple of devices — versus how much to leave
      empty so the "no data" paths stay exercised.

27. **Performance budget** (reports + import; watch, do not optimise
    blindly). Sync and dashboard run times grow with the data. They are not yet
    a nuisance, so the work is to measure, record and notice — and only
    optimise when a ceiling is crossed.
    - **Baseline** (real DB, 4,136 activities): a full dashboard build takes
      **~5 s and issues 6,803 SQL queries** — 4,457 `activity_intervals` calls,
      219 `activities(start, today)` range loads and 95 lap loads.
    - **Instrument**: a `--timing` summary on the CLI with per-phase numbers
      (read, analysis, charts, write), plus one line at the end of a dashboard
      build and of a sync, so a regression is visible in the log.
    - **Budget**: a ceiling (for example dashboard under 15 s on the real DB)
      that counts as a bug when crossed; re-record the numbers at each release
      tag (item 22).
    - **Suspects, in order**: per-activity interval/lap lookups inside loops;
      each dashboard section loading its own `activities()` range (219 calls
      per build); per-activity `classify()`; chart rendering.
    - **Cheap first**: a read-only per-build cache on `DataSource` —
      `activities()` by range and `activity_intervals()`/`activity_laps()` by
      id — removes most of it without touching the analysis code. Do that
      before rewriting queries.
    - **Tests**: bound the query count on the demo database, so a new N+1 fails
      the suite instead of the wall clock.

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
