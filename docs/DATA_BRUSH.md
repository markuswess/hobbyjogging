# Data brush

A recurring pass over the stored record, by problem class. It is phase 3's
exit test and the maintenance cadence afterwards: the review queue is the
inbox, the health card is the gauge, and the CLI is the reference. The
localhost UI (phase 4, item 65) automates the same passes and adds no new ones.

## Before a pass

- Back up the database and export the overlay (`maintenance export-manual`).
- Record the baseline: `verify_canonical`, open items per category, the
  duplicate count, per-field/per-year coverage (`./reports.sh health`).
- Run bulk work on a copy first; apply to the live database only after a dry
  run.

## Passes

| # | pass | what it settles | tool | stop when |
|---|---|---|---|---|
| 1 | duplicates | a sheet row mirrors a device row; keep the device row, copy the description, exclude the sheet row | duplicate items, `sheet_duplicates_v1` output, triage | the duplicate count is zero or the rest are accepted |
| 2 | conflicts | advisory causes resolve in bulk; `duration_estimate`, `sport_vocabulary`, `hr_sensor_anomaly` need a per-activity decision | `review triage`, `review causes`, `review resolve --cause` | no open `field_conflict` |
| 3 | classification | tag/comment/type suggestions where the evidence is clear; fix renamed or stale sets | evidence proposals, triage `(k)`, `activity edit` | the sampled sessions have a believable category |
| 4 | coverage | per year: HR, pace zones, elevation, weather, gear, distance | health coverage table, audit | every gap is filled or deliberately accepted |
| 5 | tags | map or retire the unmapped tags; the mapped ones already drive rules | tag lexicon audit | no needed tag is unmapped |
| 6 | races and periods | official results, PBs, race methods, seasons, illness ranges | `races`, `race-result`, `period` | the race/PB pages and season bands are right |
| 7 | gear | retire old shoes, fix names, link missing activities | `equipment add / edit / retire` | gear coverage is sane and nothing is unlinked |
| 8 | thresholds and wellness | dated thresholds, zones, derived VO2max; fill or accept wellness gaps | `threshold add`, wellness report | zones exist where expected; no unexplained hole |
| 9 | close | export the overlay, run the rebuild proof, record the new baseline, tag the release | `export-manual`, `maintenance rebuild`, `verify_canonical` | empty rebuild diff and a recorded baseline |

One pass per sitting (1–2 hours); do not open the whole log. After the
campaign a 20–30 minute weekly brush, or one per release tag, keeps it there.

## The source loop

Correct the platform when it will re-import the wrong value; correct the
database (a manual value plus `edit_log`) when the platform cannot or should
not change. Keep the corrections export (item 57) as the source-side list:
apply it there, re-sync, and let the database stay a mirror. The overlay is
the end-of-pass paperwork, not a backup.

## What this means for the browser

Build it for this brush, not as a general editor: queue-first decisions,
filters and date/name search, batch actions with a manifest, a provenance
dossier, health drill-down and the corrections list. Do a CLI-only brush
first and build only the friction it exposes — most likely batch decisions,
filtering and side-by-side provenance. A 30-minute pass with no terminal is
the acceptance test.
