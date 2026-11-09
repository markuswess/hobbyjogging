# Next up: reports package

Updated 2026-11-09.

Current focus: daily planned-zone display and session-level planned-vs-actual
comparison.

## Done

- **Static dashboard.** `dashboard.sh` writes a self-contained site with an
  overview (7/42/182-day hard/total EWMAs, running volume by intensity group,
  load, plan vs actual), recovery and health charts, activity list and detail
  pages, and a canonical data-health banner; it opens the browser. `sync.sh`
  regenerates the same site after a successful sync without opening a browser.
  Charts use bundled plotly; generation is atomic.
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
- **Dashboard data health is canonical-only.** The actual review-item queue
  needs a core `DataSource` addition; see the follow-up below.

## Next

1. **Daily planned session.** Show the upcoming/current workout's planned
   distribution, for example `pace: Z1 27:30, Z3 25:00, Z4 5:00`, labelled
   with `zone_kind`. Omit the section when the event has no zone times.
2. **Planned vs actual by session.** Match events to activities by date +
   sport and compare pace distributions. The time chart and dashboard
   currently compare by week only. Power comparisons remain impossible until
   activities store power zone times; do not fake them.
3. **Optional HR-zone variant.** The time chart is pace-only now. Add
   `--zone-kind hr` (or a separate chart) if the old HR view is still wanted.
4. **Review queue in the dashboard.** Expose unresolved `review_items`
   through `DataSource` (root/core change) for a richer health page and
   category links.

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
