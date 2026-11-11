# Next up: reports package

Updated 2026-11-09.

Current focus: daily planned-zone display and session-level planned-vs-actual
comparison.

## Done

- **Static dashboard.** `dashboard.sh` writes a self-contained site with an
  overview (7/42/182-day hard/total EWMAs, running volume by intensity group,
  load, plan vs actual), recovery and health charts, activity list and detail
  pages, selected Markdown reports converted to HTML, and a canonical
  data-health banner; it opens the browser. `sync.sh` regenerates the same
  site after a successful sync without opening a browser. Charts use bundled
  plotly; generation is atomic.
- **Time chart uses pace zones.** The weekly stack and zone EWMA panel use
  activity pace zones. Planned pace zones appear as hatched weekly bars and
  continue through the EWMA panel as dashed projections. Planned zones of
  other kinds are ignored. Zones stack Z1 on top and higher zones below, and
  a third panel shows each zone's share of the week's running time.
- **Planned report Z3+4 column.** Sums each event's own Z3 and Z4 time,
  ignoring `SS`. Missing zone data shows `-`; genuine zero Z3+4 time shows
  `0min`.
- **Zone helpers.** `event_zone_seconds()`, `event_zone_time()`,
  `daily_planned_zone_time()`, and `weekly_planned_time_by_zone()` handle
  normalization, `SS`, empty zones, and weekly aggregation.
- **Analysis and NSA tabs.** `analysis.html` shows the weekly volume, weekly
  time-by-zone, and load charts over the last two years (`--analysis-days`,
  default 731). `nsa.html` (NSA) holds the subT EWMA report (7/42/182-day
  pace and session-HR EWMAs for short/medium/long/LT1), the subT/LT1 chart,
  and the `subT Report` over the same window. The same EWMA report is
  available as `reports.sh subt-ewma-report`. The load chart gained the
  three session-RPE EWMAs (7/42/182) on a right-hand RPE axis; the daily
  value is the mean RPE of that day's rated sessions, carried forward
  between sessions like VO2max, with the EWMAs warming up over the usual
  910 days.
- **Recovery report.** `reports.sh recovery-report` renders HRV, resting HR,
  and sleep with simple 7/42/182-day calendar-day moving averages (missing
  days skipped) plus the last four nights in the daily report's format. The
  dashboard recovery page shows it first, then the chart (last 186 days by
  default, `--recovery-days`) and completeness note. Also selectable with
  `--reports recovery-report`.
- **Activity detail uses the session report.** `activity/<id>.html` renders
  `format_session_activity()` — the same Markdown body as
  `reports.sh session` — instead of a parallel hand-built page. The session
  report links to the Intervals and Garmin Connect activity pages when the
  database source can resolve their external ids.
- **Dashboard data health is canonical-only.** The review queue is exposed
  through `DataSource.review_items()` and rendered on the health page.
- **Review queue on the health page.** The health page shows the open
  `ReviewItem` rows (severity, category, detail, linked activity, reported
  date), counts them in the stat grid, and keeps the separate list of
  activities hidden by review.

## Handoff from the root session

Dashboard follow-ups, handed over together with the triage work:

- **Workout methods/targets on the session detail.** Done. The dashboard
  session page and the Markdown `session` report list methods and targets;
  the activities table and the `activities` CLI report gained `methods` and
  `targets` columns (in the default set).
- **Race cards.** Done. The overview lists races in the next 180 days from
  `Event` (date, name, distance, planned load, zone kind), selecting events
  whose methods or targets contain `race`. The Intervals importer now maps
  the API's `RACE_A`/`RACE_B`/`RACE_C` event categories onto the `race`
  method during event sync, so an existing database needs a fresh event
  sync before its races show up.
- **Review queue rendering.** Done. `DataSource.review_items(status="open",
  category=...)` feeds the health page: one row per open item with severity,
  category, detail, linked activity, and reported date; the count is in the
  stat grid. Category filters exist in the API for a later per-category view.

- **Fixed chart axes.** Charts no longer autoscale: volume 0–130 km, time
  0–10 h (both panels), load 0–150 with the RPE axis on the right at 0–6 so
  one RPE point lines up with 25 load units, subT pace 3:15–4:20 min/km
  (faster up), subT HR 140–180 bpm. Bars that exceed a fixed limit are
  marked with a "clipped above …" triangle instead of being hidden. The RPE
  axis extends in whole points (and the load axis with it) if a session-RPE
  EWMA ever passes 6.

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
4. **Compare tab and compare chart.** Render the existing year/month compare
   reports on a new dashboard tab, and add a compare chart: one line per
   calendar year over a single Jan–Dec x-axis, plotting an EWMA of a chosen
   metric (volume, time, load, runs) with a chosen window (7/42/182 days).
   The current year is partial — mark today and keep the axis fixed so the
   years line up.
5. **Pace vs HR scatter.** One point per run (average pace vs average HR) for
   aerobic-efficiency analysis. Decide the pace axis: `min/km` is intuitive
   but reciprocal (equal speed changes curve the cloud), `m/s` is linear and
   better for a trend line or correlation. Recommendation: plot `m/s` and
   label the ticks in `min/km`, or offer a toggle.
6. **Recovery bands.** Red/yellow/green zones behind the recovery plots (HRV,
   resting HR, sleep) so a point's status reads at a glance. Thresholds are
   not defined yet — propose HRV relative to the 42-day baseline (±1 SD),
   resting HR relative to its baseline, and sleep 7–9 h green.
7. **Shoe mileage.** Distance per equipment item from canonical data:
   `equipment` → `activity_equipment` → `activities.distance_m`. No schema
   change — 10 shoes and 1,842 links are already there (e.g. Lunge C-Dur
   3,774 km / 283 runs, Brooks Adrenaline 20 2,878 km / 184 runs). Show total
   distance and session count per shoe, wear against `target_distance_m` when
   set (currently NULL for every shoe), and retirement candidates
   (`retired_on` empty, beyond the target). A `shoes` report plus a dashboard
   card; compute in `analysis/`, render separately.
8. **Session report completeness** (low priority, last). The `session` report
   omits tags, VO2max, the day's planned workout and wellness, and review
   status; laps need a core `DataSource.activity_laps` first. See the root
   `docs/NEXT_UP.md` for the full gap list.

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
