# Next up: reports package

Current focus: planned-event zone distribution in reports and the dashboard.

## Done

- **Time chart planned HR zones.** Planned running workouts with an HR zone
  distribution render as hatched weekly stacked bars over the actual HR-zone
  stack. Weeks without planned HR zones keep the dashed total-time outline.
- **Normalization.** `event_zone_seconds()` folds zones beyond the displayed
  count into the last zone and ignores `SS`;
  `weekly_planned_time_by_zone()` aggregates per Monday–Sunday week and
  filters by `zone_kind`.
- **Empty data.** Missing or all-zero event zone times leave the total-time
  outline in place; no empty legend entry or panel is added.

## Remaining

1. **Daily planned session.** Show the planned zone distribution for the
   upcoming/current planned workout, e.g.
   `pace: Z1 27:30, Z3 25:00, Z4 5:00`, labelled with `zone_kind`.
2. **Planned vs actual detail.** Match planned events to activities by
   date + sport so pace and HR distributions can be compared session by
   session. The time chart currently overlays planned HR zones by week, not
   by matched session. Power comparisons remain impossible because
   activities do not store power zone times; do not fake them.
3. **Planned pace zones.** Upcoming events are mostly `pace` kind, and there
   is no pace-zone chart yet. Do not mix pace and HR zones in one stack.
4. **Dashboard.** Reuse the weekly planned-zone aggregation for the planned
   zone distribution in the static dashboard.

## Tests

Covered now:

- planned zone seconds are summed per label/kind;
- normalization handles 4/5/7 zones and `SS`;
- empty zone times fall back to the total-time outline.

Still needed when the remaining work lands:

- daily report includes the planned zone section when zone times exist;
- planned-vs-actual alignment by date + sport for pace/HR;
- no power comparison is attempted when activity power zones are absent.

## Docs

- `packages/hobbyjogging-reports/README.md` documents the time chart's
  planned HR-zone stack and its limits.
