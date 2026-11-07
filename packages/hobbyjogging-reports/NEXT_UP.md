# Next up: reports package

Current focus: planned-event zone distribution in reports and the dashboard.

## Context

- Schema v8 exposes `Event.zone_kind` (`pace`, `hr`, `power`, `unknown`) and
  `Event.zone_times` (`zone_label` like `Z1`–`Z7`/`SS`, `zone_index`,
  `seconds`) through the canonical model and `TrainingRepository`.
- The import package still needs to map `workout_doc.zoneTimes` and run the
  local `events backfill-zones`; the real DB currently has **0** event zone
  rows. Reports must degrade gracefully when the list is empty.
- No report or chart reads event zone times yet. Events are currently used only
  for planned load/distance projections and planned workout dates.

## Tasks

1. **Daily planned session.** Show the planned zone distribution for the
   upcoming/current planned workout, e.g.
   `pace: Z1 27:30, Z3 25:00, Z4 5:00`, labelled with `zone_kind`.
2. **Weekly/period view.** Aggregate planned zone time for upcoming workouts;
   optionally render a stacked bar next to actual zone time.
3. **Planned vs actual.** Match planned events to activities by date + sport:
   - pace and HR comparisons are possible (activities store both);
   - power comparison is not yet possible because activities do not store
     power zone times. Do not fake it.
4. **Normalization.** Events have 4, 5, or 7 zones plus `SS`; actual activity
   zones are normalized to the configured zone count. Use one shared rule:
   compare the first N zones and ignore `SS` (or display `SS` only in the
   planned distribution).
5. **Empty data.** If `Event.zone_times` is empty, omit the section rather than
   printing an empty table.

## Tests

- Daily report includes the planned zone section when zone times exist.
- Empty zone times produce no section.
- Aggregation sums seconds per label/kind.
- Normalization handles 4/5/7 zones and `SS`.
- Planned-vs-actual alignment by date + sport for pace/HR.
- No power comparison is attempted when activity power zones are absent.

## Docs

- Update `packages/hobbyjogging-reports/README.md` with the new planned-zone
  output and its limits.
- Update `docs/NEXT_UP.md` when this lands.
