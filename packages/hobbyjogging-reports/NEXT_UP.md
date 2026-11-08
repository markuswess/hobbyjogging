# Next up: reports package

Updated 2026-11-08.

Current focus: daily planned-zone display and session-level planned-vs-actual
comparison.

## Done

- **Time chart uses pace zones.** The weekly stack and zone EWMA panel use
  activity pace zones. Planned pace zones appear as hatched weekly bars and
  continue through the EWMA panel as dashed projections. Planned zones of
  other kinds are ignored.
- **Planned report Z3+4 column.** Sums each event's own Z3 and Z4 time,
  ignoring `SS`. Missing zone data shows `-`; genuine zero Z3+4 time shows
  `0min`.
- **Zone helpers.** `event_zone_seconds()`, `event_zone_time()`,
  `daily_planned_zone_time()`, and `weekly_planned_time_by_zone()` handle
  normalization, `SS`, empty zones, and weekly aggregation.

## Next

1. **Daily planned session.** Show the upcoming/current workout's planned
   distribution, for example `pace: Z1 27:30, Z3 25:00, Z4 5:00`, labelled
   with `zone_kind`. Omit the section when the event has no zone times.
2. **Planned vs actual by session.** Match events to activities by date +
   sport and compare pace distributions. The time chart currently compares
   by week only. Power comparisons remain impossible until activities store
   power zone times; do not fake them.
3. **Optional HR-zone variant.** The time chart is pace-only now. Add
   `--zone-kind hr` (or a separate chart) if the old HR view is still wanted.
4. **Dashboard.** Reuse the weekly planned-zone aggregation for the static
   dashboard's planned zone distribution.

## Tests and docs

Covered now:

- normalization handles 4/5/7 zones and `SS`;
- planned zone seconds aggregate per label, kind, and week;
- empty zone times fall back to the total-time outline;
- zone EWMA points past the requested end are marked projected.

New work should add:

- daily report coverage for the planned zone section, including the
  no-zone-times case;
- date + sport planned-vs-actual matching for pace;
- no power comparison when activity power zones are absent.

Update `packages/hobbyjogging-reports/README.md` when the daily section or
session matching lands.
