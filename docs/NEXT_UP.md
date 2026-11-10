# Status and next steps

Updated 2026-11-08.

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
- **Real data.** Full FIT archive import and Garmin VO2max backfill have run
  against the real database (2,848 activities, 2,802 with a Garmin VO2max;
  668 events with 2,808 planned zone rows). The historical spreadsheet import
  added the 2009–2021 log (1,292 activities, 10 equipment items, 1,842 shoe
  links); the review queue holds 238 open items (230 field conflicts, 5
  quality, 3 ambiguous matches).

## Next

1. **Dashboard follow-ups** — handed to the reports session; the list lives in
   `packages/hobbyjogging-reports/NEXT_UP.md` (workout methods/targets on the
   session detail, review queue through `DataSource`, race cards,
   session-level planned-vs-actual).
2. **Runalyze enrichment** when the API auth/endpoint details are settled:
   comments merged into `description`, tags, gear via the
   equipment-categories endpoint, `vo2max_runalyze`. Unmatched rows create
   activities.
3. **`review scan` prune mode**: resolve stale quality items whose current
   values no longer trigger them (field conflicts already prune).
4. **Homelab cutover**: DB + importer + dashboard generator + static server,
   periodic backups, Tailscale/basic auth.
5. **Classifier into core** (hygiene): move the heuristic out of
   `hobbyjogging-reports` so `hobbyjogging-maintenance` stops depending on the
   renderer. No behavior change.

Triage is done: five items remain on hold (2 `ambiguous_match`, 3 zero-duration
`quality`).

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
