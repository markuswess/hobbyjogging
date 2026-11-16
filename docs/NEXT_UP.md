# Status and next steps

Updated 2026-11-12.

## Done

- **Recording devices are stored (schema v17).** A `devices` table
  (manufacturer, product, serial, name, active dates) and a nullable
  `activities.device_id` — one recorder per activity, so no link table. FIT
  owns the field (it carries the serial) and a manual assignment wins. The
  backfill filled 2,853 activities across 6 devices: enduro 1,636, fr645
  1,139, edge_540 74, fr945 1, plus two Intervals-only rows; 1,295 pre-2019
  activities have no device. Garmin Connect web uploads are not devices. The
  device timeline stays on the reports list.
- **Official race results are stored (schema v16).** `race_results` keeps the
  official distance and time apart from the measured GPS values, with
  `officially_measured`, places and participants by total/gender/age class,
  `priority_level`, `status` and notes; a manual row is never overwritten by an
  import. `TrainingWriter.upsert_race_result`, `DataSource.race_results()` and
  the `race-result add|list|remove` CLI are in place, so a result can be
  entered by hand until Runalyze supplies it. The reports still have to prefer
  the official pair over the measured one (their list).
- **Athlete thresholds and zone configs are stored (schema v14/v15).**
  `athlete_thresholds` holds dated snapshots of `max_hr`, `lthr` and
  `threshold_pace_mps` — **per sport**, because Intervals stamps the settings
  of the activity's own sport. The running series has 14 snapshots and the
  threshold pace drifts **4.587 → 4.854 m/s (3:38 → 3:26/km)** over 2019–2026;
  rides, swims and the rest have their own small series. `zone_configs` is
  filled with 11 distinct boundary sets and 2,848 activities point at the HR
  config of their era (2,230 at a pace config). Both are recomputes
  (`athlete_thresholds_current`, `activity_zone_configs_current`) that run in
  `sync.sh`. The threshold trend view remains on the reports list.
- **Per-activity weather is stored (schema v13).** `activity_weather` holds the
  union of what the sources provide — temperature, feels-like, humidity, wind
  speed/degree/gust, wind chill, heat index, pressure, UV, clouds, condition,
  `is_night` — in metric units, one row per activity, first source owns it and
  a later source only fills its gaps. Intervals writes `average_temp` and the
  sheet `Temperatur in °C`; the backfill covered 3,002 activities (2,823
  Intervals, 179 sheet). The Runalyze fields stay `NULL` until that import
  lands, and the lab still has to say whether adjusted pace is worth it.
- **Elevation and max HR are stored (schema v12).** `activities` gains
  `elevation_gain_m`, `elevation_loss_m` and `max_hr`, owner-based with a wide
  elevation tolerance (10 % or 20 m) and 2 bpm for max HR. FIT parses
  `total_descent` and writes ascent/descent/max HR, Intervals maps
  `total_elevation_gain`/`_loss` and `max_heartrate`, the sheet maps
  `m bergauf` and `max. Hf`. The backfills filled 3,287 activities with
  elevation (2,802 with loss) and 3,394 with max HR; 62 and 29 source
  disagreements were counted, not queued. The reports views (climb per km,
  session line) remain on the reports list.
- **The redundant sheet tags are gone.** The sheet import no longer writes the
  `Trainigstyp` code as a tag — the method/target sets carry it — and
  `drop_classification_tags_v1` removed 874 code tags from 869 activities,
  leaving the 1,015 training-area labels (`w`, `m`, `wb`, `a`, `t`, `I`) that
  are orthogonal to the classification. Manual tags are never touched.
- **The display category comes from the stored sets.** `category_for_sets`
  maps methods/targets to the display kind with a fixed priority (race,
  long_run, fartlek, intervals/progression, continuous+threshold, recovery,
  easy, unknown), and `classify()` uses it whenever an activity is classified;
  the heuristic runs only for unclassified ones. Two read-time refinements
  survive: the subT rep-length detail from the work reps and the race-support
  label from the name. `quality/fartlek` is its own kind, so a fartlek never
  enters the subT or rep-length buckets.
- **`fartlek` is back for unstructured quality.** The token is in the core
  vocabulary (quality, mutually exclusive with `intervals`, aliases
  `fahrtspiel`/`fartlek_run`), the sheet's `fs` code maps to `fartlek` +
  `vo2max`, and `fartlek_from_fs_v1` converted 40 activities on the real DB
  (20 kept manual method rows and were skipped; 34 missing targets filled with
  `vo2max`). The display kind lands with item 3 and the reports list.
- **VO2max is per sport, and the report now says so.** Message 140 carries the
  estimate for the activity's own sport, so `vo2max_garmin` on a ride is the
  cycling value — the data was right and no backfill was needed. The charts
  were already running-only; the session report now qualifies the label
  (`VO2max: 64.6 (Garmin, cycling)`), and `docs/SOURCE_NOTES.md` records the
  per-sport semantics. The residual 2026 dips (a trail race, an altitude easy
  run, a 17-minute second run) are transient session artefacts and stay with
  the lab's parked entry.
- **FIT scan manifest (schema v11).** `fit_scan_files` records every archive
  file the scan has classified, activity or not, so a routine sync skips
  unchanged ones: measured on the real archive, 18.3 s → 2.7 s over 64,349
  files, 61,470 of them non-activity. Core owns the table and the writer API;
  the import package owns the scan, prunes deleted files, and `--full` still
  re-imports everything.
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

_None._

## Next

Numbers are labels, not a schedule: a completed item leaves a gap and a new
one takes the next free number, so cross-references stay valid.

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
   - **Text fields (decided).** One training-notes text per activity, not a
     list. `activities.description` is the training notes — Intervals
     description, the sheet's `Beschreibung`, Runalyze as a blank-fill fallback
     — and the edit CLI edits it with `--description`. **No `activity_notes`
     table**: the field inventory shows one training text and one social text
     per activity, so a notes table would be the speculative abstraction the
     rules warn about. The social text lives in `activity_social` (item 16).
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
   - **Canonical weight (decided)**: `weight_kg` on `wellness_days`, nullable
     and owner-based, in kilograms with a plausible-range guard. Sources:
     the Intervals wellness payload, the sheet's `Gewicht nachher`, and
     Runalyze's `bodyComposition` endpoint — the Runalyze API confirmed it
     exists, which closes the open question. Body fat waits until something
     reads it; the lab's HR/economy VO2max idea now has its other blocker
     (max HR, item 6) resolved too.
   - **Runalyze wellness is split, not one endpoint**: `sleep`, `hrv`,
     `heartRateRest`, `heartRateMax`, `bodyComposition` and `disease` are
     separate health-metric resources, so the importer maps each into
     `wellness_days` rather than expecting a wellness object.
   - **Out of scope, recorded**: `bloodPressure`, `bloodGlucose`,
     `bodyTemperature`, `mental`, `dailyNote`, `menstrualCycle`, `statistics`
     and `race-suggestion` are not stored.

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
   - **Runalyze supplies routes for the FIT era**: the activity payload nests a
     `recurring_route` with id, name, distance, start/end coordinates and a
     bounding box, so route identity after 2021 does not depend on stored
     streams. The sheet remains the only source before 2022; a route id from
     Runalyze is a different identity from a `Streckennummer`, so the two
     never merge automatically.
   - **Open**: our own GPS-derived routes would still need stored streams.

12. **Runalyze enrichment** (core + import + maintenance + reports; milestone).
    Runalyze is the source that closes the 2022+ gap: gear identity (the sheet
    ends in 2021, so 2022–2026 has no gear at all), comments, tags, race
    results and `vo2max_runalyze`. It is not one import but a milestone with
    its own dependencies.
    - **Access, checked against the live API (Nov 2026)**: the header is
      **`token: <key>`**, not `Authorization: Bearer` (that one is for the MCP
      server). With a premium key, `/api/v1/ping` answers `["pong"]` but every
      data endpoint returns **403 Access Denied** with rate-limit headers
      (240/min) — the key is valid and lacks the read scopes. Fix is on the
      account side: regenerate the token at `/settings/personal-api` with read
      scopes and check its expiry. Docs are split per tier
      (`/doc/api/free|supporter|premium`) and all return an empty OpenAPI
      document, so the resource list comes from `/api` instead.
    - **Fallback that may unblock it now**: `runalyze.com/my/exports` offers a
      CSV/JSON export from the web UI, the same pattern as the Strava bulk
      export. Check whether it carries comments, tags, gear and race results;
      if it does, the milestone starts there and the API is only for
      incremental sync.
    - **Schema is public, only read access is gated**: the authoritative spec is
      **`/api/docs.jsonopenapi`** (749 KB, 289 schemas) — the `/doc/api/*` pages
      return an empty document even with a token. The open-source repository
      (`Runalyze/Runalyze`, branch `support/4.3.x`) adds the per-activity
      dataset keys in `inc/core/Dataset/Keys/` and the entities in
      `src/CoreBundle/Entity/`. Design against the spec — it already shaped the
      race-result, weather and threshold items (18, 7, 8).
    - **Payload findings (Nov 2026, token with read scopes)**: the activity
      object has 81 fields (87 in the detail). `vo2max` is Runalyze's
      *effective* estimate and sits beside `vo2max_by_time` and
      `vo2max_with_elevation`, so
      `vo2max_runalyze` must name which one — take `vo2max` and note the others
      as alternatives, never a Garmin value. Tags are not in the activity
      payload but are filterable (`?tag=<id>` returns the activities), so one
      query per tag definition imports them. `sport`, `recurring-route`,
      `planned-race` and `device-profile` answer 403 with this token; the
      nested activity data covers routes and the device name anyway.
    - **Also available**: a hosted MCP server at `runalyze.com/mcp` with the
      same personal token — relevant to the coaching workflow (item 25), not to
      bulk import.
    - **Dependencies**: official race results (item 18) and the equipment
      identity work below. Comments need no decision — they fill
      `activities.description` only when it is blank (item 1).
    - **Phases**: (1) export/API client with a dry run that reports what is
      available per field and per year; (2) comments and tags into the chosen
      text home; (3) gear with cross-source identity; (4) race results;
      (5) `vo2max_runalyze` as the second owner; (6) the reports.
    - **Gear identity**: gear records become
      `source_records(record_type='gear')` plus `equipment` rows, linked
      through `activity_equipment` with `source='runalyze'`. Cross-source
      identity reuses `equipment_source_links`: link a gear record to an
      existing item when its activities consistently carry the same sheet shoe
      (co-occurrence), else on a unique normalized brand+model match, else open
      an `ambiguous_equipment` review item — never guess (the two
      "Lunge C-Dur" pairs differ only by colour and date). 2022+ gear has no
      sheet counterpart and simply creates new rows.
    - **Import rules**: Runalyze never writes `name` — its title is a Garmin
      auto-title, and an unmatched row that creates the activity would own the
      name and block the Intervals session name the classifier reads. Its
      description fills `description` only when blank; comments go there, not
      into a separate table.
    - **Matching**: temporal plus distance, since Runalyze exposes no Garmin
      activity id; unmatched rows create activities so the history stays
      complete. Enrichment only — never timing or distance.
    - **Reports**: gear coverage per year closes the 2022–2026 gap on the gear
      page, comments appear where the text home decides, and `vo2max_runalyze`
      sits beside `vo2max_garmin`.
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
      no owner tracking, and planned workouts carry methods/targets/zones but no
      step list.
    - **Phases**, in order: owner-tracked events (`event_field_sources`, manual
      wins, a new `AGENTS.md` rule) → planned-workout steps and authoring →
      subjective wellness ownership → thresholds/zones (item 8) → the front end
      from item 1 → Garmin/FIT ingest so Intervals becomes optional.
    - **Not needed**: a notes/comments table. The field inventory shows one
      training-notes text per activity (`description`) plus a social text on
      Strava, so this work reuses `description` rather than adding
      `activity_notes`.
    - **Parked decisions**: whether programmed workouts are followed on the
      watch (which would need a `.fit` workout export and upload) or the lap
      button is enough — the 370 intervals activities with ≥3 WORK reps suggest
      the latter; and whether the front end ever replaces the CLI.
    - **Edit history** from item 1 is a prerequisite, not an extra: without it,
      dropping the platform also drops the audit trail.

15. **Reports backlog** — handed to the reports session; the list lives in
   `packages/hobbyjogging-reports/NEXT_UP.md` and is kept current there rather
   than duplicated here.
16. **Social titles, descriptions and links** (core + import + reports; low
    priority). Strava is the first social layer, but not the only possible one:
    the title is a pun, the description sometimes a note, while the Intervals
    title is the workout name. Both are worth keeping, and they must not
    compete — `name` is deliberately not a conflict field, so a social import
    writing it would be ignored (Intervals names are never blank) or open
    thousands of review items.
    - **Schema**: `activity_social(activity_id, source, title, description,
      external_id, url, source_record_id, is_manual, updated_at)`, keyed by
      `(activity_id, source)` — a table like `activity_equipment` and the
      planned device/weather/route tables, not columns on `activities`:
      source-specific metadata, not a canonical metric. The table is
      deliberately not named after Strava, so another user can map a different
      social import into it; `source` is data, not schema. `url` is stored
      rather than derived, because only Strava has a predictable activity URL.
    - **Writes only `activity_social`**: the pun title and its description
      never touch `activities.name`, `activities.description` or `classify()`.
      The training notes stay canonical (item 1); this is social text.
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

28. **Periodic cleanup pass** (all packages + docs; recurring). Nothing guards
    readability today: no linter is configured, and the documentation has
    started to duplicate itself. Neither is a fire, but both drift in one
    direction.
    - **Docs**: the `## Done` sections are 160, 90, 25 and 232 lines in the four
      `NEXT_UP.md` files and restate git history; trim them to a short "recently
      landed" list or drop them, keeping only what a reader needs for context.
      Also sweep for facts stated twice (the reports pointer, the roadmap that
      was folded into ARCHITECTURE).
    - **Code**: audit the ~108 names re-exported from
      `hobbyjogging_report.analysis.__init__` for dead exports, then delete
      unused helpers, parameters and flags. No `TODO`/`FIXME` markers exist
      today — keep it that way.
    - **Mechanical guard**: propose `ruff` (lint and format check) in CI. It
      would catch unused imports and variables and enforce a line length, but
      expect a first pass of violations and some config churn; decide whether
      that is worth it before wiring it into the test job.
    - **Cadence**: one pass at each release tag (item 22), plus the boy-scout
      rule already in `AGENTS.md` — leave a file no worse than you found it.
    - **Acceptance**: no dead exports, no duplicated doc sections, no file that
      has outgrown its purpose without being split or trimmed.

29. **Detach the lab into `laufen_private`, keep the bench** (root + reports;
    future). The lab's scripts and notebook carry personal research and
    findings and should not live in the project repo — but the bench must stay
    so another user can run their own.
    - **Split**: the bench ships (the rules, `experiments/template.py`,
      `lab.sh`, the gate in `docs/METRICS.md`, the Lab tab); the log moves to
      `laufen_private/lab/` (the scripts, the candidate table, the statuses and
      the rejected findings).
    - **Env var rename**: `HOBBYJOGGING_LAB_DIR` currently means the output
      directory (`data/lab`) in `shell.py`; rename that to
      `HOBBYJOGGING_LAB_OUTPUT_DIR` and give `HOBBYJOGGING_LAB_DIR` the lab
      itself, defaulting to `experiments/` so a fresh clone works out of the
      box.
    - **Dashboard**: read `$HOBBYJOGGING_LAB_DIR` for local builds; demo builds
      never read it and render the bench guide only (see the reports bug).
    - **Evidence split**: `docs/METRICS.md` keeps the contract (definition,
      baseline, thresholds) and the aggregate statistics; the personal
      narrative — illness dates, resting-HR values, run counts tied to events —
      moves to the lab repo and is referenced by name.
    - **Move checklist**: create `laufen_private/lab/`, move the scripts and the
      candidate table, split `experiments/README.md` into bench rules and
      notebook, then update `lab.sh`, the lab section of `AGENTS.md`, the
      dashboard and the `.env` example.
    - **Risks**: two repos to clone on a new machine; `lab.sh` must fail
      clearly when the lab dir is missing; CI must never need the private repo;
      the moved scripts lose their in-repo history.
    - **Related**: item 23 (this is its lab case), item 26 (demo upkeep) and
      item 25 — the coaching notes will live in the same private repo, so the
      dashboard reads both from there.

30. **Training periods: seasons, plans and illness** (core + import +
    reports). The raw data already carries them and nothing interprets them:
    Intervals events have `category` = `SEASON_START` (3 — "VCM 23/24/25", each
    December, the season ending at the Vienna City Marathon), `SICK` (25
    single-day "krank" / "leicht verkühlt" markers), `NOTE` (4 — travel, wisdom
    tooth recovery), `TARGET` (9) and `FITNESS_DAYS` (1). The importer stores
    them as events with `type=''` — 34 rows — so they appear nowhere.
    - **Schema**: `training_periods(id, kind, label, start_date, end_date,
      source, source_record_id, notes, excluded_at)`. A period is a range, which
      an event is not; kinds `season`, `plan`, `illness`, `travel`, `recovery`,
      `other`. Overlaps are allowed (an illness inside a season).
    - **Import**: `SEASON_START` → a season beginning on that date and ending
      before the next one (or at the goal race); `SICK` → an illness marker;
      `NOTE` → `other` with the label. Store `category` on the period rather
      than guessing from names, and keep the raw event link.
    - **Ranges from markers**: a season's end is derivable; an illness's is not
      — 25 single-day markers say "sick today", not how long. Start with the
      marker, allow a manual end, and never infer a duration.
    - **Runalyze `disease` supplies the range**: the API has a health-metric
      resource for illness with its own start and end, which is exactly what
      the day markers cannot give. Use it as the illness source when the
      import lands, with the Intervals markers as a fallback and manual entry
      always winning.
    - **Manual entry**: `period add|edit|remove` (manual wins), and the future
      edit CLI from item 1.
    - **Reports**: shade seasons and illness on volume, load, recovery and
      compare charts; a seasons table in the period report; flag or exclude
      illness from efficiency and trend aggregates — the efficiency card
      already records that the Feb–Mar 2026 illness moved the resting baseline
      8%.
    - **Lab**: the experiments split by illness by hand; canonical periods make
      that reproducible.
    - **Open**: `plan_name` / `plan_folder_id` are in every event payload but
      null today, so Intervals training plans are not in use; store them anyway
      if plans return.
    - **Tests**: SEASON_START maps to a season range, SICK to a day marker, a
      manual end survives a reimport, overlapping periods are allowed.

31. **Efficiency over all activities** (lab first, then reports and the card).
    The steady aggregate stops at 75 min (`STEADY_DURATION_BAND`), so a long run
    contributes nothing to the trend; it used to start at 45 min as well.
    - **40-minute floor (landed).** The duration model gives `+135/T` bpm, so a
      40-minute run reads about 1.5 % lower than a 60-minute one; inside the
      40–75 min band that spread is acceptable while the band is printed. On the
      real log it added 26 steady runs over the last year (108 → 134) and 314
      all-time (1,165 → 1,479), moving the aggregate by 0.002 and 0.001. The
      card now says 40–75 min.
    - **An all-runs series.** Every run with HR, distance and duration, as a
      second labelled line beside the steady aggregate — never merged into it.
      The card's Comparability caveat says whole-session interval averages are
      not comparable to steady runs, so the two have to stay visually distinct
      and separately labelled.
    - **Lab first**: does the all-runs series track the steady one, and is it
      more reliable (more n) or noisier (protocols mixed)? Split-half
      reliability and a year-by-year comparison, per the gate in
      `docs/METRICS.md`.
    - **Card**: if it lands, the efficiency card gains the 40 min floor, the
      all-runs series and the reason they are not merged.
    - **Split**: the implementation lives in the reports list, under the
      efficiency-scope item; the lab files the candidate row in
      `experiments/README.md` and runs the split-half comparison. The root
      session updates the card.

32. **Explicit ownership on the todo lists** (docs + tools). Each package has
    its own `NEXT_UP.md` and the root list tags items with their packages, but
    ownership is prose: an item says what blocks it, not who owns it, and the
    numbered cross-references break silently when the root list is renumbered —
    which happened twice in one session.
    - **Check (done)**: `tools/check_todos.py` fails when a package list
      references a root item that does not exist, or when a root number appears
      twice. It runs in the CI test job, so a renumbering cannot land with a
      dangling pointer.
    - **Convention**: `AGENTS.md` says a package session starts from its own
      list and treats root items as dependencies, not work.
    - **Target format** for new or edited package items: one line —
      `Owner: <pkg> · Needs: root #N (title) · Status: blocked|ready` — so the
      state is visible to an agent that only reads the package list.
    - **Open**: whether the root items also get an owner line, and whether the
      check should compare the parenthetical title with the root item's title
      (fragile — probably not).

33. **Efficiency fallback when no resting-HR baseline exists** (reports + card).
    `robust_baselines` returns `None` for a date before the first wellness
    sample, so `excess_beats` yields `None` and efficiency is `-` for the whole
    pre-Sep-2022 log — eleven years of activities.
    - **Backward fill**: for a date before the first sample, use the earliest
      available 365-day median (the first baseline) instead of `None`. It is
      data-driven and continuous at the boundary, with no invented number.
    - **Last resort**: a configured default (for example 50 bpm) only when the
      wellness table has no resting HR at all, printed as an assumption.
    - **Mark it estimated**: the lookup returns the value plus an `estimated`
      flag, so the session report and the activities column can say "estimated
      baseline" while the trend aggregates keep using measured baselines only —
      an estimated period must not look measured.
    - **Guard**: keep `avg_hr − rhr ≥ 10` and reject a fallback outside a
      plausible 35–70 bpm range; a too-low fallback inflates efficiency.
    - **Card**: the efficiency card records the fallback, when it applies, and
      why the trends stay measured-only.
    - **Tests**: an activity before the first wellness day gets a value with the
      estimated flag; the compare and overview aggregates still exclude it; a
      fallback of 0 or 200 is rejected.

34. **Manual-layer export and rebuild check** (maintenance + core; **low
    priority** — insurance, not a blocker). The raw layer is preserved and
    SQLite stays readable, so the data does not disappear; what dies with the
    code is the *meaning*: which values were overridden, which sessions were
    deliberately excluded, which conflicts were decided. That layer is small —
    measured on the real DB: 73 manual field overrides (`sport` 38, `avg_hr`
    28, …), 335 + 209 manual workout method/target rows, 29 exclusions, 33
    ignored review items — against 14,393 source records and 4,148 activities
    that are raw or recomputable.
    - **Phase 1**: `maintenance export-manual` writes JSONL — manual field
      values, manual sets, manual tags, manual equipment links, exclusions and
      the ignored/resolved review fingerprints — and `import-manual` re-applies
      it to a fresh database, idempotently. Human-readable, diffable, a few
      kilobytes.
    - **Phase 2**: a `rebuild` check — fresh database, replay the raw layer
      (`source_records` plus the FIT archive), apply the overlay, then diff the
      canonical layer against the live database. An empty diff is the proof
      that raw + overlay + code reproduce everything. Companion to item 17
      (raw vs derived).
    - **Placement and cadence**: the overlay lives in `laufen_private` next to
      the database (item 29) and is exported at each release tag (item 22).
    - **Not doing**: a CSV/JSON export of the whole canonical database — it
      duplicates the raw layer and rots with the schema — and not treating the
      overlay as a backup; a periodic `sqlite3 .backup` remains the safety net.
    - **Why low**: the raw sources and the database are already safe; this
      protects the decisions and the design claim, which matters if the project
      is ever abandoned or handed over.

35. **Runalyze's extra metrics: what to store, what to ignore** (core + import
    + reports; decision). The activity payload carries more than our schema
    holds. Coverage measured in the Intervals payloads we already keep:
    `average_cadence` 2,353 of 2,851 (83%), `average_stride` 2,334, but the
    running-dynamics family (`average_vertical_oscillation`,
    `average_stance_time`, `average_vertical_ratio`) only 110 (4%). The FIT
    session message carries the same averages (`avg_vertical_oscillation`,
    `avg_stance_time`, `avg_stance_time_balance`, `avg_vertical_ratio`,
    `avg_step_length`, `avg_running_cadence`) and the records carry them per
    second, so the 4 % is Intervals' coverage, not the ceiling — the importer
    just does not extract them yet. Runalyze adds `gap`/`x_gap`,
    `aerobic_decoupling_pace/power`, `trimp`/`fit_trimp`/`fit_training_effect`,
    `required_critical_pace/power`, `climbs`, `hrv`, and zone distributions as
    percentages.
    - **Store**: `cadence` and `stride_length` (83 % coverage, actionable) and
      `gap_mps` — Runalyze's grade-adjusted pace beats a lap-based estimate.
    - **Lab**: decoupling and critical speed already have candidates; use
      Runalyze's values as a cross-check, not as stored metrics.
    - **Out of scope for now**: vertical oscillation, stance time and ratio
      (4 % in Intervals, more in FIT), impact loading, leg spring stiffness,
      TRIMP and training effect (we keep Intervals' `training_load`), climbs as
      an entity, HRV analysis, and zone distributions as percentages. If the
      dynamics ever matter, extract the FIT session averages rather than
      storing streams.
    - **Open**: whether cadence and stride sit on `activities` or in an
      `activity_dynamics` row; two columns are defensible at 83 % coverage.

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
