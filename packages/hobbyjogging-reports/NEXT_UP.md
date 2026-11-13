# Next up: reports package

Updated 2026-11-12.

Current focus: the dashboard's gear/devices and race work.

## Done

- **Static dashboard.** `dashboard.sh` writes a self-contained site with an
  overview (7/42/182-day hard/total EWMAs, running volume by intensity group,
  load, plan vs actual), recovery and health charts, activity list and detail
  pages, Docs and Lab tabs (README, experiments notebook, metric registry),
  and a canonical data-health banner; it opens the browser. `sync.sh`
  regenerates the same site after a successful sync without opening a browser.
  Charts use bundled plotly; generation is atomic.
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
  steady efficiency total and a `Steady efficiency (45–75 min)` category
  column; `compare-years`/`compare-months` show a weighted steady efficiency
  column; and `overview` adds an Efficiency row to the existing EWMA table,
  using the 7/42/182-day weighted steady efficiency and leaving the planned
  column empty. All aggregates are sum(distance)/sum(excess beats) and use
  the 365-day baseline; no baseline means an omitted line or a dash.
- **Efficiency duration bands.** Report aggregates are now steady:
  non-quality runs in a fixed 45–75 min band (`is_steady_run`,
  `steady_efficiency`, and an `aggregate_efficiency(duration_band=...)`
  filter). Period/category reports, the overview EWMA row, compare series
  and pace/HR efficiency lines all use that band and print it next to the
  number, so no two aggregates are compared across bands. Raw session and
  daily efficiency stay unbanded; subT keeps work-rep efficiency and labels
  it. The pace/HR scatter outlines the steady points that feed the dashed
  efficiency lines and notes that all runs are shown. Tests cover the
  duration filter, quality exclusion and labels.
- **Category symbols on the pace/HR charts.** `PaceHrPoint.category` is
  filled from `classify(activity, intervals)`. The Analysis scatter splits
  into one trace per category with a fixed symbol map (easy, recovery,
  intervals, long run, race, tempo, fartlek, race support, other) while
  keeping a shared date gradient and colour bar; the compare scatter keeps
  year colours and applies per-point category symbols with a key
  annotation. Regression and efficiency lines are unchanged. Tests pin the
  map, the unknown fallback, the trace split and the compare symbol arrays.
- **Session report completeness.** The session report now shows tags, both
  VO2max owners, review status and open-item details, the day's planned
  workout (with planned zone times), the day's wellness, the lap table, and
  the existing intervals/work reps. `DataSource.activity_laps` exposes the
  existing repository query, and dashboard detail pages pass the same context
  (including per-day events and wellness) as the CLI.
- **Race report and Performance tab.** `reports.sh races` lists results,
  personal bests per bucket, upcoming races, and Riegel equivalent times;
  `reports.sh race ACTIVITY_ID` renders splits, half-pace, planned zones, and
  plan deltas. `performance.html` shows the tables, a log-log race chart with
  the fitted exponent, and per-race detail pages. Race matching uses race
  methods/targets on the same date until `event_activity_links` lands. The
  overview race cards moved to this tab.
- **Gear report and Gear tab.** `reports.sh equipment` aggregates
  `equipment` → `activity_equipment` → activities into sessions, km,
  km/month, last use, target/wear, and active/retired status. It also shows
  per-year coverage with and without gear and retirement candidates (over
  target or unused for a year). The Gear dashboard tab adds a mileage bar
  chart with target markers, the same table, coverage, and candidates. Shoes
  without `target_distance_m` use an 800 km default.
- **Docs tab instead of Reports.** `docs.html` replaces the old Reports tab
  and renders the reports README, with a contents list and prefixed heading
  anchors. The nav order is Overview, Activities, Performance, Gear, Recovery
  and Health, NSA, Analysis, Compare, Docs, Lab, Data Health. Embedded
  reports already live on their pages; `--reports` remains a compatibility
  no-op. A **Lab** tab follows Docs and renders `experiments/README.md`, the
  experiment script index with one-line summaries, and the metric registry
  from `docs/METRICS.md`, with its own contents list.
- **One segment table in the session report.** The report now prints typed
  intervals when there is more than one, otherwise device laps when there is
  more than one, and nothing when there is a single segment on each side.
  The subT work-reps section and interval-based analysis are unchanged;
  `docs/ARCHITECTURE.md` records that laps are device splits and intervals
  are Intervals.icu's typed reps.

## Bugs

- **Recovery tab window mismatch (182 vs 186).** The tab queries and labels a
  186-day window — `RECOVERY_DAYS = 186`, the `--recovery-days` default, the
  `dashboard.sh` help, the page title `start → end` and the "N of 186 days"
  completeness line — while the embedded recovery report states 7/42/**182**-day
  averages, so one tab shows two windows. The 186 arrived in `703c4d0` with no
  recorded reason.
  - Fix: one source of truth. Derive the window from
    `recovery_report.WINDOWS[-1]` (182) instead of a separate constant, default
    `--recovery-days` to it, and update `dashboard.sh` and the README. If the
    extra 4 days are intentional slack, say so in the help text and on the
    page instead of leaving two numbers.
  - Tests: the page title, the completeness denominator and the report's
    window label agree; `--recovery-days` still overrides.

- **Compare plot colors shift between charts.** All three compare charts pick
  `COMPARE_COLORS[index % len]` from the *index in that chart's own sorted year
  list* (`plot_compare_pace_hr`, `plot_compare_vo2max`, `plot_compare`), so a
  year's color depends on which other years happen to be present: 2023 is one
  color in the volume chart and another in the VO2max chart because their year
  sets differ, and the colors shuffle again when the data range or
  `--compare-window` changes.
  - Fix: one `compare_color(year)` helper anchored on a fixed year —
    `COMPARE_COLORS[(year - 2009) % len(COMPARE_COLORS)]` — used by all three.
    The 18 colors then cover 2009–2026 with no collision.
  - Tests: a year gets the same color in all three charts, and a year outside
    the current data range still maps deterministically.

## Next

1. **Device timeline.** Depends on the root device registry. Add a device
   timeline (which watch/computer recorded when, with activity counts), mark
   device changes on the VO2max chart so a step is attributable to the watch,
   and add a `- Device:` line to the session report.

2. **Weather and max HR in the reports.** Once the data lands: show max HR in
   the session report and use it for HR-zone checks; annotate pace, HR and
   efficiency charts with temperature and wind; add a per-year data-coverage
   line for both.

3. **Route grouping.** Group activities by route so pace, HR and efficiency
   compare like-for-like, with a route page listing its best efforts. Depends
   on the root route item.

4. **Wellness extras.** A readiness view (readiness, sleep score, stress,
   respiration, spO2) plus a weight trend, once the columns land.

5. **Threshold trend and era-correct zones.** A chart of LTHR, threshold pace
   and max HR over the years beside VO2max; normalize activity zones with each
   activity's zone config; compare subT work-rep pace with the period's
   threshold pace. If the race-derived series lands, show it against the
   stamped values so a divergence is visible.

6. **Fartlek as its own category.** Show `quality/fartlek` in the breakdown
   and the category column, and keep it out of the subT rep-length buckets and
   every rep-count/duration analysis — a fartlek has no reps to measure. The
   read-time `tempo` fallback must not turn it into `intervals`. Depends on
   the root fartlek item.

7. **Race PB progression chart.** Add a per-bucket PB trajectory to the
   Performance tab (and optionally the `races` report): one step line per
   distance bucket connecting improvements over time, with race points on
   top and the current PB annotated. Use the bucket tolerance and, once the
   official race-result table lands, the official distance/time pair with the
   GPS fallback. X is date, Y is race time (`M:SS` / `H:MM:SS`); toggle or
   separate small multiples for `5k`, `10k`, `HM`, `M`, `Trail`, `Other`.
   - Tests: only improvements advance the step line; ties do not; buckets stay
     separate; official values win when present.

8. **Race report filters.** Add `--bucket`, `--year` (or `--from`/`--to`),
   and `--limit` to `reports.sh races`, applying them to the results and PB
   tables while leaving the upcoming-race list unfiltered unless explicitly
   requested. Derive the filter metadata from the existing race buckets; no
   schema change. Add a short usage note to the README and tests for combined
   filters and empty results.

9. **Elevation in the reports.** Once the columns land: climb per km in the
    session report and the activities list, a coarse grade-adjusted pace from
    per-lap gain (the FIT payload has no altitude stream, so this is
    lap-level), trail suggestions from the ≥40 m/km evidence, and route
    difficulty on the dashboard.

10. **Strava in the session report.** A `Strava: …` line with the title, the
    description as an annotation, and a link to the activity. Depends on the
    root Strava item and on the notes/description decision in root item 1.

11. **VO2max by sport in the charts.** Label the series "Running VO2max" and
    keep it to running activities, so the 482 rides stop injecting a different
    series; add the cycling series when it exists. Depends on the root VO2max
    bug fix.

12. **Data-driven chart ceilings.** `VOLUME_Y_MAX`, `TIME_Y_MAX` and
    `LOAD_Y_MAX` are fixed to this athlete's peak (a 130 km/week volume axis),
    so another user's charts are mostly empty and this one's are cramped when
    it grows. Compute a "nice max" from the data (round up to a sensible step)
    and keep the fixed values only as a fallback. Same for
    `COMPARE_VISIBLE_YEARS` and `RACE_DAYS` if they turn out to be personal.
    See root item 23.

13. **Metrics tab.** Render the analysis catalogue from root item 24 as a
    dashboard tab next to Docs: grouped by area (load, intensity, efficiency,
    races, wellness, tools), one anchor per entry, formulas as plain text or
    code so the site stays self-contained. If the catalogue is generated, the
    tab renders the same source the Markdown does.

## Tests and docs

Covered now:

- normalization handles 4/5/7 zones and `SS`;
- planned zone seconds aggregate per label, kind, and week;
- empty zone times fall back to the total-time outline;
- zone EWMA points past the requested end are marked projected.

New work should add:

- equipment mileage and device-timeline coverage;
- PB selection per distance bucket and the race-day report;
- the Docs page render (README content present, nav marks Docs active).
