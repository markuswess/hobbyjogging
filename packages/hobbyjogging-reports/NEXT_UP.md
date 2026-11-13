# Next up: reports package

Updated 2026-11-12.

Current focus: the synthetic demo database for the public GitHub Pages
dashboard (handoff below); daily planned-zone display and session-level
planned-vs-actual comparison remain next.

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
- **Workout methods/targets on the session detail.** The dashboard
  session page and the Markdown `session` report list methods and targets;
  the activities table and the `activities` CLI report gained `methods` and
  `targets` columns (in the default set).
- **Race cards.** The overview lists races in the next 180 days from
  `Event` (date, name, distance, planned load, zone kind), selecting events
  whose methods or targets contain `race`. The Intervals importer now maps
  the API's `RACE_A`/`RACE_B`/`RACE_C` event categories onto the `race`
  method during event sync, so an existing database needs a fresh event
  sync before its races show up.
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
  shows volume (km/week), time (hours/week), and efficiency charts (182-day EWMA by
  default), with dashed projected volume/time lines for the current and
  future years: actual through today, then the plan. A separate raw Garmin
  VO2max line plot connects the per-activity readings, no averaging. Only
  the five most recent years are visible by default; older years stay in
  the legend and can be re-enabled. The year/month comparison reports use
  the period average Garmin VO2max. Also `charts.sh compare`.
- **Pace vs HR scatter.** `charts.sh pace-hr` and the Analysis tab plot one
  point per run: linear speed (m/s, labelled in min/km ticks) against
  average HR, coloured by date from blue (oldest) to red (newest) with a
  year colour bar, plus least-squares lines for the older and newer half of
  the runs (slope, intercept, and r shown on the chart and printed by the
  CLI).

- **Recovery readiness bands.** The recovery chart shades three bands
  behind each panel using a robust 365-day baseline (median centre,
  `1.4826 x MAD` spread) computed at the end of the displayed range: HRV
  green at/above the centre, amber down to one spread below, red below;
  resting HR mirrored; sleep green 7-9 h, amber 6-7 h or 9-10 h, red
  outside. Fewer than seven values in the baseline window means no HRV/RHR
  bands. `analysis/baseline.py` provides the generic helper, shared with
  the efficiency resting-HR baseline. A year-long window deliberately
  adapts slowly: March 2026 RHR 58 now reads red instead of green, while a
  2 bpm rise in a stable period reads amber instead of red. A small colored
  key sits at the top right of the chart and the dashboard note explains
  the thresholds. The recovery report's moving-average table also shows the
  365-day baseline column for HRV and resting HR (sleep is absolute).

- **Efficiency (m/excess beat).** Runs report meters per heartbeat above
  rest in the session report, the optional `eff` activities column, every
  subT work-rep line, the subT summary/block tables, the subT EWMA report
  (pace/HR/efficiency tables), the subT chart's third panel, and the
  compare tab. The metric is `distance / ((avg_hr - rhr) * minutes)` with
  `rhr` = rolling 365-day median resting HR, expanding when history is
  shorter and `None` when there is none; the guard is
  `avg_hr - rhr < 10`. Aggregates are always
  sum(distance)/sum(excess beats); the subT chart and compare series use a
  weighted rolling mean rather than an EWMA of ratios, and rest days carry
  the previous value in the compare series. The compare efficiency chart
  drops years with fewer than 20 HR-backed runs and years without a
  baseline (resting HR starts in Sep 2022, so it currently shows 2022-2026).
  The subT efficiency axis auto-ranges (roughly 1.8-2.8 in the current
  data). A 365-day baseline is deliberate: a 42-day window read +8% high
  after the Feb-Mar 2026 illness; see the module docstring.

- **Synthetic demo database.** `demo-db --out PATH` writes a deterministic
  invented 4-year athlete (seed, periodized plan, intervals, zone times,
  wellness with an illness and a travel week, planned events, two future
  races, four shoes) through `TrainingWriter`, with no `source_records` or
  personal data. Easy and long runs use only Z1/Z2, workouts carry Z3/Z4,
  VO2max is one smooth daily value, interval sets alternate work/recovery,
  and the future plan copies the last four complete weeks. `dashboard --demo-label TEXT` adds an opt-in banner on
  every page. Same seed gives identical content; tests cover counts, complete
  zones, smooth VO2max, easy/vs-workout zones, future-plan similarity, future
  races, review opt-in, size, and a full dashboard build.
  `./demo.sh` builds the site locally and GitHub Actions publishes it
  weekly to <https://markuswess.github.io/hobbyjogging/>.
- **Pace/HR efficiency lines.** The scatter keeps the two free regression
  halves and adds a dashed efficiency line per half,
  `HR = RHR + v * 60 / E`, with `E` = that half's weighted efficiency
  (`sum(distance) / sum(excess beats)`, m/excess beat) and `RHR` = its median
  365-day baseline. Points without a baseline stay in the scatter but not in
  the line. The chart and CLI annotate `E` and RHR; the Analysis tab and
  `charts.sh pace-hr` fetch wellness with a 365-day lead-in.
- **Compare tab pace/HR scatter.** The compare page adds the same
  speed-vs-HR scatter as the Analysis tab, but one categorical colour per
  calendar year, with the same fixed pace/HR axes and hover text. The five
  most recent years are visible by default; older years stay in the legend.
- **Efficiency in the Markdown reports.** Daily runs show a compact
  efficiency line; `report`/`weekly`/`monthly`/`yearly` show a weighted
  efficiency total and an `Efficiency (m/excess beat)` category column;
  `compare-years`/`compare-months` show a weighted efficiency column; and
  `overview` adds an Efficiency row to the existing EWMA table, using the
  7/42/182-day weighted efficiency and leaving the planned column empty.
  All aggregates are sum(distance)/sum(excess beats) and use the 365-day
  baseline; no baseline means an omitted line or a dash.
- **Session report completeness.** The session report now shows tags, both
  VO2max owners, review status and open-item details, the day's planned
  workout (with planned zone times), the day's wellness, the lap table, and
  the existing intervals/work reps. `DataSource.activity_laps` exposes the
  existing repository query, and dashboard detail pages pass the same context
  (including per-day events and wellness) as the CLI.
- **One segment table in the session report.** The report now prints typed
  intervals when there is more than one, otherwise device laps when there is
  more than one, and nothing when there is a single segment on each side.
  The subT work-reps section and interval-based analysis are unchanged;
  `docs/ARCHITECTURE.md` records that laps are device splits and intervals
  are Intervals.icu's typed reps.

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
4. **Equipment report and dashboard tab.** `reports.sh equipment` plus an
   **Equipment** dashboard tab, computed from `equipment` →
   `activity_equipment` → `activities.distance_m`. No schema change.
   - **Per item**: name, brand/model, type, acquired/retired, sessions, km,
     km/month, last used, target/wear, notes.
   - **Coverage block**: activities with and without gear per year. Gear
     currently ends in 2021 (10 shoes, 1,842 links); 2022–2026 has none until
     the Runalyze gear import lands, so show the gap explicitly.
   - **Retirement candidates**: active items beyond the target, or unused for
     N months.
   - **Wear target**: `target_distance_m` is NULL everywhere; use a report
     constant (e.g. 800 km for shoes) with an optional per-item override.
     Ignore the sheet's own totals in the notes for now.
   - **Dashboard**: the table plus a chart — cumulative km per shoe over time,
     or bars with target lines and retirement markers.
   - **Tests**: mileage sums, coverage counts, the active/retired split, and
     `-` rendering when an item has no activities.

5. **Race report and Performance tab.** Depends on the root
   `event_activity_links` item; until that lands, use activities whose methods
   contain `race`.
   - `reports.sh races`: past results (date, name, distance, time, pace,
     category, HR, load), **PBs per distance bucket** (5k/10k/HM/M/trail, with
     a tolerance — the 4.20 km and 4.91 km "5k" rows need it), upcoming races
     with countdown, and the planned-vs-actual line for linked races.
   - `reports.sh race <id>`: race-day report — splits from laps, HR/zone
     execution against the event's planned zones, positive/negative split, and
     the plan delta.
   - **Analysis**: pace-vs-distance scatter (log-log) with a Riegel exponent,
     an equivalent-time table (what today's 10k predicts), and best-effort
     trends.
   - **Dashboard Performance tab**: upcoming races, results table, PB table,
     the performance trend chart, and race-day cards. Supersedes the overview
     race cards.
   - **Tests**: PB selection per bucket, planned-vs-actual delta, `-` when a
     race has no link, race-day split rendering.

6. **Docs tab instead of Reports.** Replace the dashboard's "Reports" tab
   (`reports.html`, `reports_page`) with a **Docs** tab (`docs.html`).
   - **Phase 1**: render `packages/hobbyjogging-reports/README.md` through the
     existing Markdown → HTML renderer inside a `.report` card, with a short
     intro and a table of contents. Nav becomes Overview, Activities, Recovery
     and Health, NSA, Analysis, Compare, **Docs**, Data Health.
   - **Phase 2 (planned)**: per-metric explanations — definition, formula,
     baseline, thresholds, caveats — generated from `docs/METRICS.md`, which is
     already the metric registry. Link metric names in the dashboard to their
     Docs section.
   - **The embedded Markdown reports** currently on that tab (`--reports LIST`)
     already appear elsewhere (overview embeds overview/daily/planned,
     recovery embeds recovery-report, nsa embeds subt-report). Move any
     remaining ones to their page, then retire `--reports` or keep it as a
     no-op for compatibility.
   - **Tests**: the page builds, contains the README heading, the nav marks
     Docs active, the demo label still applies, and no `reports.html` is left
     behind.
   - **Docs**: the reports README dashboard section.

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
