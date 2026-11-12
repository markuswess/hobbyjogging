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
  and the `subT Report` over the last year. The same EWMA report is
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

- **Compare tab and chart.** `compare.html` renders one EWMA line per
  calendar year over a fixed Jan–Dec axis (metric and window chosen with
  `--compare-metric volume|time|load|runs` and `--compare-window N`,
  default volume/42d; the current year stops at today and is marked) plus
  the year and month comparison reports. The EWMA runs across the whole
  history, so each year line starts on the previous year's close. The tab
  shows volume and time charts (182-day EWMA by default). Also
  `charts.sh compare`.
- **Pace vs HR scatter.** `charts.sh pace-hr` and the Analysis tab plot one
  point per run: linear speed (m/s, labelled in min/km ticks) against
  average HR, coloured by date from blue (oldest) to red (newest) with a
  year colour bar, plus least-squares lines for the older and newer half of
  the runs (slope, intercept, and r shown on the chart and printed by the
  CLI).

- **Recovery readiness bands.** The recovery chart shades three bands
  behind each panel using the last 42 days: HRV green at/above its
  baseline, amber down to one standard deviation below, red below;
  resting HR mirrored; sleep green 7-9 h, amber 6-7 h or 9-10 h, red
  outside. Fewer than seven values in the baseline window means no HRV/RHR
  bands. A small colored key sits at the top right of the chart and the
  dashboard note explains the thresholds.

- **Efficiency (m/beat).** Runs report meters per heartbeat in the session
  report, the optional `eff` activities column, every subT work-rep line,
  the subT summary/block tables, the subT EWMA report (pace/HR/efficiency
  tables), the subT chart's third panel, and the compare tab. Aggregates are
  always sum(distance)/sum(beats); the subT chart and compare series use a
  weighted rolling mean rather than an EWMA of ratios, and rest days carry
  the previous value in the compare series. The compare efficiency chart
  drops years with fewer than 20 HR-backed runs (2014, 2017, 2018). The
  subT efficiency axis auto-ranges for now (roughly 1.5-1.9 m/beat in the
  current data).

## Next

1. **Efficiency: subtract the resting baseline (`m/excess beat`).** The
   shipped metric is raw `distance / (HR × min)`, which is biased by the HR
   offset. A fit on the real data gives `HR ≈ 52.5 + 26.2·v` (R² = 0.54) with
   the intercept matching the median resting HR (51 bpm), and `v/HR` spreads
   11.3% across speed quartiles while `v/(HR − RHR)` spreads only 3.3%.
   Subtracting the baseline makes the number comparable across paces — which
   is what the subT categories, the compare page and the activity level need.
   - **Metric**: `distance_m / ((avg_hr − rhr) × duration_min)`, still called
     efficiency, label **`m/excess beat`**; `EFFICIENCY_UNIT` changes.
   - **Baseline**: rolling **42-day median** of `wellness_days.resting_hr`;
     when the window has no values, the all-time median of the supplied
     wellness; `None` when there is none at all. Guard `avg_hr − rhr < 10` →
     `None`. Keep it a pure helper, e.g.
     `resting_hr_baseline(wellness, day, window_days=42)`.
   - **Plumbing**: every caller fetches wellness with a 42-day lead-in and
     passes the baseline through — `format_session_activity`,
     `sessions.session_report`, `activity_list`, `analysis/subt`
     (`SubtPoint`), `subt_ewma`, `charts.plot_subt`,
     `compare.compare_year_ewma`, and the dashboard pages. `analysis/` stays
     pure: the baseline is an argument, never a query.
   - **Aggregates stay weighted**: Σdistance / Σexcess beats. Keep the raw
     distance/excess-beat sums on `SubtPoint`.
   - **Labels/ranges**: "Efficiency (m/excess beat)" in the session line, the
     `eff` column, the subT panel title and the compare axis; subT axis
     roughly 1.8–2.8 (the raw metric sat at 1.5–1.9).
   - **Caveats**: RHR noise propagates (~5% for a 5 bpm error on a ~90 bpm
     difference) — this is a trend signal, not a per-run score; HR lag still
     understates short reps; runs only.
   - **Tests**: known value (10 000 m / 3 600 s / 150 bpm / rhr 50 → 1.667),
     the baseline fallback chain, the `hr − rhr < 10` guard, weighted
     aggregate vs naive mean, a regression test that the metric is flat
     across speed bands under a synthetic linear HR model, and `-` in the
     renderers when absent.
   - **Docs**: the module docstring gets the fitted model and the 11.3% → 3.3%
     spread; update the Done bullet that quotes the raw axis range.
2. **Daily planned session.** Show the upcoming/current workout's planned
   distribution, for example `pace: Z1 27:30, Z3 25:00, Z4 5:00`, labelled
   with `zone_kind`. Omit the section when the event has no zone times.
3. **Planned vs actual by session.** Match events to activities by date +
   sport and compare pace distributions. The time chart and dashboard
   currently compare by week only. Power comparisons remain impossible until
   activities store power zone times; do not fake them.
4. **Optional HR-zone variant.** The time chart is pace-only now. Add
   `--zone-kind hr` (or a separate chart) if the old HR view is still wanted.
5. **Shoe mileage.** Distance per equipment item from canonical data:
   `equipment` → `activity_equipment` → `activities.distance_m`. No schema
   change — 10 shoes and 1,842 links are already there (e.g. Lunge C-Dur
   3,774 km / 283 runs, Brooks Adrenaline 20 2,878 km / 184 runs). Show total
   distance and session count per shoe, wear against `target_distance_m` when
   set (currently NULL for every shoe), and retirement candidates
   (`retired_on` empty, beyond the target). A `shoes` report plus a dashboard
   card; compute in `analysis/`, render separately.
6. **Session report completeness** (low priority, last). The `session` report
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
