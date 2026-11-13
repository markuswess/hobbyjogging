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

2. **Elevation gain and loss on activities** (core + import + maintenance).
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

3. **Runalyze enrichment** when the API auth/endpoint details are settled:
   comments merged into `description`, tags, gear via the
   equipment-categories endpoint, `vo2max_runalyze`. Unmatched rows create
   activities.
4. **Homelab cutover**: DB + importer + dashboard generator + static server,
   periodic backups, Tailscale/basic auth.
5. **Reports backlog** — handed to the reports session; the list lives in
   `packages/hobbyjogging-reports/NEXT_UP.md`: daily planned session, planned
   vs actual by session, optional HR-zone variant, shoe mileage.
6. **Raw vs derived: document the tiers and add a check** (low priority). The
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
