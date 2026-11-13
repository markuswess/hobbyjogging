# Next up: reports package

Updated 2026-11-13.

Current focus: the demo data and the race metrics; every other item waits
on a core or root change.

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
  dashboard recovery page shows it first, then the chart (last 182 days by
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
- **Bounded chart axes.** subT pace stays at 3:15–4:20 min/km (faster up) and
  subT HR at 140–180 bpm; the volume, time, load, and overview axes follow the
  data instead (see *Data-driven chart ceilings*). Bars above any axis are
  marked with a "clipped above …" triangle instead of being hidden.
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
- **Recovery chart axis matches the data.** The date axis is pinned to the
  first and last wellness point instead of Plotly's padded auto-range, so the
  line fills the panel; planned workout ticks still extend the end when the
  CLI asks for them.
- **Recovery window one source of truth.** `RECOVERY_DAYS`, the
  `--recovery-days` default, `dashboard.sh` help, and the README now derive
  from `recovery_report.WINDOWS[-1]` (182), matching the embedded report's
  7/42/182-day label and the page range and completeness line. Tests cover
  the default title, the denominator, and the `--recovery-days` override.
- **Compare EWMA burn-in.** `compare_year_ewma` and the planned variant seed
  the EWMA with the mean of the first time constant of data instead of the
  first day's value. The 2022 efficiency line now starts at 2.38 instead of
  2.72 and agrees with the year table's 2.47; volume, time and load use the
  same burn-in. The planned line keeps the actual-only seed, so it still
  meets the actual line through today.
- **Standard-distance PBs.** `personal_bests()` only accepts a race within
  2% of the standard distance for 5k/10k/HM/M, so a 4.2 km race no longer
  wins the 5k PB; Trail and Other still use the fastest raw time. The PB
  tables show the distance, and the Riegel `PB` column uses the same
  qualified PB. Official race results will replace this tolerance when root
  item 18 lands.
- **Race PB progression.** The Performance tab draws one step line per bucket
  (`5k`, `10k`, `HM`, `M`, `Trail`, `Other`) through chronological PB
  improvements only, with race points and the current PB annotated. The lines
  use the same standard-distance rule. Tests cover strict improvements, ties,
  bucket separation and short-course rejection.
- **Race report filters.** `races` accepts `--bucket 5k|10k|HM|M|Trail|Other`,
  `--year YYYY` (or `--from`/`--to`) and `--limit N`. Bucket and date
  filters scope the results, PB and Riegel tables; a date filter also scopes
  upcoming races, while bucket and limit leave them alone. Limit caps the
  result rows only, so PBs still use every matching race. Tests cover
  defaults, combined filters, truncation, and empty results.
- **Stable compare colors.** All three compare charts map a year through
  `compare_color(year)`, anchored on 2009, so a year keeps one color across
  the volume/time/load/runs/efficiency, pace/HR, and VO2max charts, and the
  colors no longer shuffle when the data range or `--compare-window`
  changes. The 18 colors cover 2009–2026 without collision; tests pin the
  mapping and check all three charts.
- **One segment table in the session report.** The report now prints typed
  intervals when there is more than one, otherwise device laps when there is
  more than one, and nothing when there is a single segment on each side.
  The subT work-reps section and interval-based analysis are unchanged;
  `docs/ARCHITECTURE.md` records that laps are device splits and intervals
  are Intervals.icu's typed reps.

- **Per-build dashboard cache and timing.** `CachedDataSource` memoizes
  activity ranges (serving narrower requests from a covering block) plus
  intervals and laps by id; the dashboard command wraps the source in it.
  On the real database a build dropped from ~6,800 queries / ~5 s to about
  3,400 interval, 6 activity-range and 93 lap misses / ~1.4 s. `--timing`
  prints per-phase seconds and miss counts, and the demo build test bounds
  the misses.

- **Demo coverage check.** A test builds the synthetic database and asserts
  every embedded report plus the races, equipment, subT EWMA, session and
  race-day reports render their key sections; the dashboard test checks all
  eleven tabs and their markers. The demo now includes five completed
  5k/10k/half races with PB improvements, so the Performance tab has
  results, PBs, a PB progression and a Riegel fit instead of empty states.

- **Data-driven chart ceilings.** `_axis_ceiling` drops the top few percent
  of the plotted values (so one ultra cannot set the axis), adds headroom and
  rounds up to the chart's step; `VOLUME_Y_MAX`, `TIME_Y_MAX`, `LOAD_Y_MAX`
  are gone. The 42/182-day averages are included, the 7-day average is not.
  On the real build the overview axis is 75 min instead of 90 with five long
  days marked, volume 120 km/week (was 130), time 10 h, load 150 with nine
  marked days. The RPE overlay now has its own scale instead of pinning the
  load axis to 0–150.

- **The demo Lab tab publishes no personal results.** A demo build renders
  the bench guide from `experiments/README.md` (everything before `## Ideas`)
  and nothing else: no idea table, no rejected or parked findings, no script
  list, no metric registry. The guide's registry link becomes plain text
  instead of a path into the repo. A test asserts the demo page cannot contain
  the notebook, the scripts, or the registry, and the dashboard test keeps the
  full Lab for non-demo builds. The docs README example already uses a neutral
  placeholder path.

- **VO2max is running-only in every chart.** `vo2max_points` and
  `vo2max_measurements` drop non-running activities, so the rides stop
  injecting a separate series; the daily chart is titled "Garmin running
  VO2max" and the compare chart is "Garmin running VO2max by year". The
  cycling series waits on the core sport column in root's VO2max bug.

- **The race chart draws the prediction line.** `plot_races()` draws
  `t = t_ref · (d/d_ref)^β` through the reference race instead of the free
  least-squares line, rings that race, and labels the line with the fitted
  exponent, n, and the anchor's bucket and date. `riegel_time()` is the one
  formula behind both the drawn line and `equivalent_times()`, so the chart
  and the table can no longer disagree; the `races` report names the anchor
  race as well. The estimator itself is unchanged — age weighting and a
  shape/level split are lab questions.

- **PB progression in pace, standard buckets only.** The step chart plots
  average pace (min/km) on a `M:SS` axis instead of raw times, so a 15 s 5k
  gain is visible beside a marathon line, and only 5k/10k/HM/M get a line:
  Trail and Other have no standard distance, so a step there is a distance
  change, not a PB. Their fastest times stay in the tables as
  `Trail (raw)` / `Other (raw)`. The 2% tolerance inside a bucket waits for
  official race distances (root item 18).

## Bugs

_None._

## Next

Items 1-8 and 11 need a core or root change first; 9 and 10 need root
items 24 and 25. Only **12** can be done in this package today.

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

7. **Elevation in the reports.** Once the columns land: climb per km in the
   session report and the activities list, a coarse grade-adjusted pace from
   per-lap gain (the FIT payload has no altitude stream, so this is
   lap-level), trail suggestions from the ≥40 m/km evidence, and route
   difficulty on the dashboard.

8. **Strava in the session report.** A `Strava: …` line with the title, the
   description as an annotation, and a link to the activity. Depends on the
   root Strava item and on the notes/description decision in root item 1.

9. **Metrics tab.** Render the analysis catalogue from root item 24 as a
   dashboard tab next to Docs: grouped by area (load, intensity, efficiency,
   races, wellness, tools), one anchor per entry, formulas as plain text or
   code so the site stays self-contained. If the catalogue is generated, the
   tab renders the same source the Markdown does.

10. **Coaching tab.** Render the latest coaching note and an index of past
   ones, through the same Markdown-to-HTML path as Docs, with front matter
   turned into a header (date, period, focus) and the decision sections
   linked. Must be empty — not leaking — in the public demo: exclude the
   `coaching/` directory when a demo label is set, or ship a synthetic
   example note. See root item 25.

11. **Season and illness bands.** Once `training_periods` exists (root item
    30), shade seasons on the volume, load and compare charts and illness on
    recovery and efficiency, with the label on the band. Add a seasons table to
    the period report, and decide per metric whether an illness period is
    excluded or only flagged. See the efficiency card's note on the Feb–Mar
    2026 baseline shift.

12. **Demo narrative: Daniels first, then Norwegian singles.** The demo runs one
    generic periodization (base/build/peak/taper across the whole log) with
    five hard-coded races in the last seven months, so the eras are
    indistinguishable and the race times contradict the sessions (a 21:30 5k
    next to subT paces that imply 18:00).
    - **Era 1, Jack Daniels** (first half): E/M/T/I/R paces, two quality
      sessions a week plus a long run, weekly mileage progressing, and **boom
      and bust cycles** — two or three build blocks that end in a 2–3 week
      collapse (illness) and a rebuild, visible in load, volume and VO2max.
    - **Era 2, Norwegian singles** (second half): double-threshold days (two
      sub-threshold sessions in a day, twice a week), five or six easy runs,
      higher weekly hours, almost no VO2max work, and a visibly smoother load
      series.
    - **Races across the whole log**: at least one per season from the first
      year, not five in the last seven months, so the PB progression and the
      Riegel fit have history to draw on.
    - **Times that follow the training**: derive each race from the era's
      fitness — the subT pace of the surrounding sessions, the era's VO2max —
      not from constants. A 10k time must imply a threshold pace within a few
      percent of the generated subT sessions, and a bust must show as a slower
      race before the rebuild.
    - **Tests**: races in the first and last year; PBs improve across the eras;
      the load series shows the busts; the two eras differ in their
      method/target mix; every race time is consistent with its era's pace.

## Tests and docs

Covered now:

- normalization handles 4/5/7 zones and `SS`;
- planned zone seconds aggregate per label, kind, and week;
- empty zone times fall back to the total-time outline;
- zone EWMA points past the requested end are marked projected;
- PB selection per distance bucket (tolerance and short-course rejection)
  and the race-day report;
- the Docs page render (README content present, nav marks Docs active);
- the race chart line passes through the reference race and matches the
  equivalent-time table at every standard distance, and the CLI `races`
  report and the Performance tab print the same predictions;
- the PB progression plots pace on a min/km axis, skips Trail and Other,
  and labels Trail/Other bests as raw in the tables.

New work should add:

- device-timeline coverage, once the field lands.
