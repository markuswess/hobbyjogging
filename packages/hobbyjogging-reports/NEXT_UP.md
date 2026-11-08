# Next up: reports package

Current focus: planned-event zone distribution in reports and the dashboard.

## Done

- **Time chart uses pace zones.** The weekly stack and the zone EWMA panel
  now use activity pace zones. Planned running workouts with a pace zone
  distribution render as hatched weekly stacked bars over the actual stack;
  planned zones of other kinds are ignored. Weeks without planned pace zones
  keep the dashed total-time outline.
- **Normalization.** `event_zone_seconds()` folds zones beyond the displayed
  count into the last zone and ignores `SS`;
  `weekly_planned_time_by_zone()` aggregates per Monday–Sunday week and can
  filter by `zone_kind` or include all kinds.
- **Empty data.** Missing or all-zero event zone times leave the total-time
  outline in place; no empty legend entry or panel is added.
- **Planned report Z3+4 column.** The planned-workouts table sums each
  event's own Z3 and Z4 time (pace, HR, or power), ignoring `SS`. Missing
  zone data shows `-`; genuine zero Z3+4 time shows `0min`.

## Remaining

1. **Daily planned session.** Show the planned zone distribution for the
   upcoming/current planned workout, e.g.
   `pace: Z1 27:30, Z3 25:00, Z4 5:00`, labelled with `zone_kind`.
2. **Planned vs actual detail.** Match planned events to activities by
   date + sport so pace distributions can be compared session by session.
   The time chart currently overlays planned pace zones by week, not by
   matched session. Power comparisons remain impossible because activities
   do not store power zone times; do not fake them.
3. **Optional HR-zone variant.** The time chart now uses pace zones. An
   HR-zone variant (or a `--zone-kind` option) would restore the old view.
4. **Dashboard.** Reuse the weekly planned-zone aggregation for the planned
   zone distribution in the static dashboard.

## Tests

Covered now:

- planned zone seconds are summed per label/kind and across all kinds;
- normalization handles 4/5/7 zones and `SS`;
- empty zone times fall back to the total-time outline.

Still needed when the remaining work lands:

- daily report includes the planned zone section when zone times exist;
- planned-vs-actual alignment by date + sport for pace/HR;
- no power comparison is attempted when activity power zones are absent.

## Docs

- `packages/hobbyjogging-reports/README.md` documents the time chart's
  planned zone stack and its limits.
