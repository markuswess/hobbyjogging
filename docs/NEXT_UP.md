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
  sync replaces/clears them and `events backfill-zones` populated the existing
  payloads (2,808 rows).
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
- **Reports.** Markdown reports (daily/weekly/monthly/yearly, period,
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
  classifier + sheet backfill classified 2,686 activities (including 107
  easy defaults for sheet runs with no code and HR < 140) and tagged 56;
  216 conflicts were left unclassified for review.
- **Static dashboard.** `dashboard.sh` writes a self-contained static site
  (overview with 7/42/182-day hard/total EWMAs and running volume by intensity
  group, recovery and health, activities list, activity detail, data health)
  with embedded plotly charts, bundled `plotly.min.js`, and atomic directory
  swaps. It opens the browser; `sync.sh` regenerates the same site without
  opening one.
- **Reports: planned workouts.** The `planned` report starts tomorrow and ends
  with weekly-average total time and Z3+4 time per 7 days.
- **Real data.** Full FIT archive import and Garmin VO2max backfill have run
  against the real database (2,848 activities, 2,802 with a Garmin VO2max;
  668 events with 2,808 planned zone rows). The historical spreadsheet import
  added the 2009–2021 log (1,292 activities, 10 equipment items, 1,842 shoe
  links); the review queue holds 238 open items (230 field conflicts, 5
  quality, 3 ambiguous matches).

## Next

1. **Review the 216 workout-classification conflicts.** The dry-run list is
   saved at `data/workout-classification-conflicts.txt`; the affected
   activities were left unclassified.
2. **Dashboard follow-ups.** The first static dashboard is done (overview,
   recovery and health, activity list and detail, canonical data-health
   banner) and `sync.sh` regenerates it after a successful sync. Next: expose
   the actual review-item queue through `DataSource`, then add race cards and
   session-level planned-vs-actual views.
3. **Runalyze enrichment** when the API auth/endpoint details are settled:
   comments merged into `description`, tags, gear via the
   equipment-categories endpoint, `vo2max_runalyze`. Unmatched rows create
   activities.
4. **`review scan` prune mode**: resolve stale quality items whose current
   values no longer trigger them.
5. **Homelab cutover**: DB + importer + dashboard generator + static server,
   periodic backups, Tailscale/basic auth.

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
