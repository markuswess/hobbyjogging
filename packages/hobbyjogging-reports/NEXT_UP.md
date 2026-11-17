# Next up: reports package

Updated 2026-11-16.

Current focus: the demo data; 2's max-HR half and 5's threshold trend are
open, 12 is parked, and the rest need a core or root change or the lab gate.

## Done

- **Static dashboard.** `dashboard.sh` writes a self-contained site with an
  overview (7/42/182-day hard/total EWMAs, running volume by intensity group,
  load, plan vs actual), recovery and health charts, activity list and detail
  pages, Docs and Lab tabs (README, experiments notebook, metric registry),
  and a canonical data-health banner; it opens the browser. `sync.sh`
  regenerates the same site after a successful sync without opening a browser.
  Charts use bundled plotly; generation is atomic.

Older work (imports, charts, tabs, review queue) lives in `git log`;
this list keeps the recent decisions only.

- **Standard-distance PBs.** `personal_bests()` only accepts a race within
  2% of the standard distance for 5k/10k/HM/M, so a 4.2 km race no longer
  wins the 5k PB; Trail and Other still use the fastest raw time. The PB
  tables show the distance, and the Riegel `PB` column uses the same
  qualified PB. Official race results are stored now (`race_results`, schema
  v16); the tables still have to prefer the official pair, which is the next
  step here.
- **Race report filters.** `races` accepts `--bucket 5k|10k|HM|M|Trail|Other`,
  `--year YYYY` (or `--from`/`--to`) and `--limit N`. Bucket and date
  filters scope the results, PB and Riegel tables; a date filter also scopes
  upcoming races, while bucket and limit leave them alone. Limit caps the
  result rows only, so PBs still use every matching race. Tests cover
  defaults, combined filters, truncation, and empty results.
- **EWMA lines draw shortest first.** The overview plot now goes window-major
  (every 7-day line, then 42, then 182) and the shared average-line helper
  draws fatigue → fitness → base, so the smoothest line ends up on top and a
  rough line no longer hides it. Legends follow the same order; tests pin it
  for the overview and the load chart.

- **Stable compare colors, strongest for the newest years.** All compare
  charts map a year through `compare_color(year)`, anchored on a fixed year
  (2026 today) and running backwards: the newest years get the saturated
  colours and old years fade into the pale tail. A year keeps one colour
  across the volume/time/load/runs/efficiency, pace/HR, and VO2max charts, the
  colours no longer shuffle when the data range or `--compare-window`
  changes, and a fixed anchor means dropping old years does not recolour
  anything. The 18 colours cover 2009–2026 without collision; tests pin the
  newest-first mapping and check all three charts.
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
  eleven tabs and their markers. The demo now carries races across the
  whole log, so the Performance tab has results, PBs, a PB progression and
  a Riegel fit instead of empty states.

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
  cycling series is not planned; `activities.sport` is the discriminator and no
  core column is needed, and the session report qualifies the label on
  non-runs.

- **The race chart draws the prediction line.** `plot_races()` draws
  `t = t_ref · (d/d_ref)^β` through the reference race instead of the free
  least-squares line, rings that race, and labels the line with the fitted
  exponent, n, and the anchor's bucket and date. `riegel_time()` is the one
  formula behind both the drawn line and `equivalent_times()`, so the chart
  and the table can no longer disagree; the `races` report names the anchor
  race as well. The estimator itself is unchanged — age weighting and a
  shape/level split are lab questions.

- **PB progression in pace, standard buckets only.** The chart plots
  average pace (min/km) on a `M:SS` axis instead of raw times, so a 15 s 5k
  gain is visible beside a marathon line, and only 5k/10k/HM/M get a line:
  Trail and Other have no standard distance, so a level there is a
  distance change, not a PB. Their fastest times stay in the tables as
  `Trail (raw)` / `Other (raw)`. Every other standard-distance race in the
  bucket is a hollow dot in the bucket's colour, unconnected to the line,
  so a PB reads against the races that missed it. The axis follows the PB
  lines, so a slower race is a triangle at the top rather than stretching
  the chart. Equal times do not advance a line; tests cover strict
  improvements, ties, bucket separation and short-course rejection. The 2%
  tolerance inside a bucket can go once the tables read the stored official
  distances.

- **Equivalent times with paces.** The Riegel table projects 5k, 7k, 10k,
  15k, HM, 30k and the marathon. 7k/15k/30k have no PB bucket, so they show
  a prediction only, and both the predicted and PB columns now carry a
  min/km pace (`EquivalentTime`). The `races` report and the Performance
  tab print the same rows.

- **The demo athlete follows a story.** Four weeks of continuous running
  and a first 5k (20:30), a rest week, a classical build to 10k (40:10) and
  half (1:34), a 10-day injury and a four-week return, down weeks, a taper
  and a first marathon (3:27), six boom-and-bust weeks with a slow comeback
  10k, then a threshold-focused Norwegian block that ramps from ~70 to
  ~110 km/week with double-threshold days and PBs down to
  18:10 / 37:00 / 1:24 / 2:59. One fitness curve (5k pace plus an endurance
  factor per distance) drives every race time and training pace, and VO2max
  follows it (42 to 53) with a slow wobble, so the log reads as one athlete.
  13 races across four years replace the five in the last seven months; the
  demo database grows to ~5.2 MB.

- **VO2max says which sport it belongs to.** The session report printed
  `VO2max: 59.1 (Garmin)` on a ride, where that is the cycling estimate.
  Non-running activities now qualify it from their own sport — `(Garmin,
  cycling)`, `(Garmin, swim)`, `(Garmin, strength training)` — while runs
  keep the plain label. The chart already filtered to running. The activity's
  own sport is the discriminator, so no core column is needed.

- **A bigger, calmer overview chart.** The main chart is 700 px tall
  instead of 520, with 10 px ticks and legend, compact trace names
  (`hard 7d`, `total 42d`, `planned hard`, ...), a two-row legend, and the
  card heading "Overview" instead of "Daily running minutes". A wrapped
  horizontal legend fills in reverse trace order, so the layout sets
  `traceorder: normal`. The EWMA lines draw after the bars and carry a pale
  outline (all outlines first, then all lines, so a crossing does not cut an
  earlier line), and are 2.0-2.6 px wide; tests pin the order, height, font,
  entry width and names.

- **Crosshair on hover.** `_crosshair()` sets `showspikes`,
  `spikemode="across"` and a thin grey dotted guide on every chart (and
  `yaxis2` where a chart has one, such as the load RPE overlay and the
  overview's VO2max). The vertical guide snaps to the nearest day; the
  horizontal one follows the cursor, so a value can be read anywhere.
  Tests cover the axes, the second axis, the snap modes and that an existing
  axis range survives; the demo dashboard test asserts every chart on every
  page carries spikes.

- **Pre-baseline efficiency, flagged.** `robust_baselines(backfill=True)`
  returns the earliest baseline for days before the first sample and marks
  it `estimated`; `resting_hr_baselines` exposes the flag and accepts an
  optional 35-70 bpm fallback used only when there is no sample at all. The
  session report says `2.23 m/excess beat (estimated baseline)` and the
  `eff` activities column `2.38 (estimated)`; the period, overview and
  compare aggregates still require a measured baseline. Backfill mode reads
  the whole wellness table, because the first sample can be years after an
  old activity. The metric-card update is root item 33.

- **The demo VO2max is a watch step, not a daily wobble.** `_vo2max_value()`
  interpolates a dedicated curve (42.6 to 51.4) instead of the sine: it
  drops through the 10-day injury and the boom-bust and climbs more slowly
  after the switch to threshold work. The value is written only on quality
  and long run days, quantized to 0.1 and held in between, so the chart has
  plateaus; rides carry no running VO2max (the demo has an easy ride on the
  recovery weeks again). Tests cover the grid, the plateaus, the bust drop
  and the empty rides.

- **Efficiency floor at 40 minutes.** `STEADY_MIN_DURATION_S` is 40 min, so a
  short easy run now enters the period/overview/compare aggregates. The band
  label comes from `STEADY_BAND_LABEL` everywhere it is printed (category
  table, period line, compare header, chart and CLI notes, README), because
  the duration model's `+135/T` term makes a 40-minute run read about 1.5 %
  lower than a 60-minute one. On the real log the floor adds 26 steady runs
  over the last year (108 → 134) and 314 all-time (1,165 → 1,479), while the
  aggregate moves by 0.002 last year (2.485 → 2.487) and 0.001 all-time
  (2.425 → 2.426), so it widens n without changing the trend. Quality
  sessions stay out. The metric card now says 40–75 in its definition,
  comparability, rendered list and HR-line section (root item 31).

- **The activities tab is a training log.** It keeps every completed
  activity row and appends a row for each planned event in the shown range
  and the next 14 days that has no matching activity (same date and sport
  for now). A Status column reads `done`, `planned` or `missed`; planned
  rows carry methods, targets, planned time, distance and load, and link to
  their event page (see below). Events without a sport and matched events
  never add a row.
  The `activities` CLI report is unchanged. Tests cover a matched event, a
  missed one, a future one and the demo's planned sessions.

- **Planned events open a page.** Every typed event in the tab's window (and
  on any session day) gets `event/<id>.html`: date, sport, planned
  time/distance/load, methods and targets, the planned zone distribution from
  `event_zone_times`, and the description. The date and name of a planned or
  missed row link to it, and the session report's planned block links there
  too, so a matched event — which has no tab row — stays reachable. A matched
  page adds a plan-vs-actual table by date and sport from
  `event_activity_links` (schema v21), and it links back to the activity. An untyped note, or an event without an id, stays plain text.
  Tests cover the planned and missed rows, the matched page, zones and
  methods, and the demo link.

- **A streaks report.** `reports.sh streaks` lists the current running streak
  (days, span, km, time, and whether today is already run) and the longest
  streaks with the same fields, cut by `--limit` (default 10). A streak day is
  a calendar day with one run of at least 10 minutes; a rest day ends it and a
  ride never extends it, so cross-training cannot hold a running streak.
  `analysis/streaks.py` does the grouping (two runs on one day count once,
  with both added), the current streak ends today or yesterday, and
  review-excluded runs never count. On the real log: current 23 days, best 117
  days of 961 streaks. The dashboard card waits for a week of use, per the
  gate.

- **Long dashboard lists collapse.** `html.table()` takes a unique `collapse`
  key: past `TABLE_COLLAPSE_ROWS` (20) it renders a native checkbox and hides
  the extra rows with a CSS sibling rule, keeping the first 20 visible and
  printing "Showing the first 20 of N rows" beside a "Show all N rows" label
  (and "Show fewer" when open). Every row stays in the HTML, so the activity
  and race links and the browser's find keep working; it is CSS only, with no
  JavaScript and no build option. Wired on activities, race results, PBs, the
  review queue and gear; short tables and the Markdown reports are unchanged.
  The demo's activities tab (66 rows) collapses.

- **Weather in the reports.** The session report prints
  `- Weather: 12 °C, wind 3 m/s` (feels-like only when it differs by 3 °C or
  more); the pace/HR scatters on Analysis and Compare carry the same line in
  their hover and note coverage and range (`weather on 709 of 709 runs (median
  19 °C, 1 to 35 °C)`). The health tab gains a per-year coverage table from
  `analysis/coverage.py`: on the real log weather is 92–100 % from 2019 and 0 %
  before. `CachedDataSource` memoizes weather by activity, `DatabaseSource`
  exposes it, and the demo writes seasonal temperature and wind through
  `upsert_activity_weather` (about 3 % of days left empty). Max HR waits on the
  core exposure.

- **Session times read as M:SS.** A single activity or planned workout now
  prints `M:SS` (`H:MM:SS` past an hour) for duration, elapsed time, zone
  splits, the event page's plan-vs-actual table and the activities/planned
  tables; the compact `fmt_zones` variant is gone. Week, month, category,
  overview and streak totals keep `1h02`/`50min`, because they are sums and
  averages where seconds are noise. On the real log a 3,000 s session reads
  `50:00`, and `activities` shows `42:32` instead of `42min`.

- **subT efficiency ranges.** The efficiency panel now shows each session's
  worst–best work-rep efficiency as a thin stick, like the pace range, with
  the values and rep count in the hover. `SubtPoint` carries
  `lowest_efficiency`/`highest_efficiency` from `_subt_point()`, using the same
  usable reps as the weighted average (reps without HR or distance are
  skipped; a single rep has no range). The efficiency axis rounds to the bulk
  (top and bottom 5 % dropped) so a single 3.4 m/excess beat rep no longer
  stretches the panel past 3.2. Trends for the extremes were tried and removed
  again: three lines per category overloaded the panel, so only the weighted
  average keeps a line, and fastest/slowest rep pace and max HR never got one
  because rep length and count confound them.

- **Overview no longer repeats the planned report.** The activities tab owns
  the plan (rows and event pages), so the embedded `planned` Markdown card and
  its `planned_html` plumbing are gone; the overview chart's planned bars, the
  weekly planned averages and the `planned` CLI report stay. Tests assert the
  card is absent and the tab still carries the plan.

- **Efficiency lines on the Compare by-year scatter.** The by-year pace/HR
  chart now draws one dashed line per year, `HR = RHR + v·60/E`, with the
  year's weighted steady efficiency over the steady band and its median
  resting-HR baseline. The line takes a darkened year colour so it reads over
  the pale markers, the points keep their year colours, and the chart note
  lists every year's `E`. Years without two usable steady runs get no line.

- **The Analysis charts show the plan.** Volume, time and load now draw the
  next `future_days` (the same window as Overview): a dashed planned-km line,
  planned zone bars with a total-time outline, and planned load bars on days
  without an actual load. The plan series come from the existing
  `weekly_planned_*`/`daily_planned_load` helpers, and the axes extend to the
  last planned week.

- **NSA subT tables collapse.** `collapse_tables()` re-renders long tables from
  the subT report's HTML through the same checkbox helper as the activities
  log, so the per-category tables collapse past 20 rows while the summary
  stays open. The demo's category tables (38, 46 and 112 rows) show the
  toggle; the CLI report stays plain Markdown.

- **Reports list their periods newest first.** The Compare tab's year and
  month comparison tables now start with the most recent period (chart series
  stay chronological), and the subT report blocks sort newest first within
  each category. Tests pin both orders.

- **Fartlek is its own category, end to end.** The core token and display kind
  already landed and the category table shows `quality/fartlek` (7 sessions on
  the real log). `is_subt_activity()`/`is_lt1_activity()` now return False for
  any activity with a stored `fartlek` method, so a name that says subT or LT1
  cannot pull it into the rep buckets; classification stays `quality/fartlek`
  even when the name says "tempo", because stored sets win and no read-time
  fallback can turn it into intervals. The demo story now carries one fartlek
  session (week 20), and a demo test checks the method row.

## Bugs

_None._

## Next

Schema v12-v16 moved the data under several items, so the picture changed:
5's threshold trend is reports-only, and 2's weather half landed. What
still needs core first: max HR and elevation on `Activity` (repository
query and model drop them; items 2 and 6), the per-activity zone config ids
(item 5's zone normalization), devices (1), routes (3), wellness extras (4)
and social titles (7). Item 13 has its data (`event_activity_links`, schema
v21), item 10 is handed to root item 36 for its illness ranges and resumes
here after the maintenance fix, and 14's series needs the lab gate in root
item 31. Item 12 stays parked on its page-coverage cost, 11 is recurring
upkeep. The dashboard polish pass is finished. The
efficiency floor, the planned-event page, the streaks report and the
collapsible lists landed here.

1. **Device timeline.** Depends on the root device registry. Add a device
   timeline (which watch/computer recorded when, with activity counts), mark
   device changes on the VO2max chart so a step is attributable to the watch,
   and add a `- Device:` line to the session report.

2. **Max HR in the reports.** Weather landed: the session report, both
   pace/HR scatters and the health coverage table use it. Max HR is stored
   (schema v12) but the repository's activity query and the `Activity` model
   drop it, so that exposure comes first; then the session line, the HR-zone
   checks, and the Max HR column beside weather in the coverage table.

3. **Route grouping.** Group activities by route so pace, HR and efficiency
   compare like-for-like, with a route page listing its best efforts. The data
   is there (`routes` + `activity_routes`, schema v20; 36 routes, 384 links).

4. **Wellness extras.** A readiness view (sleep score and quality, SpO2,
   steps, CTL/ATL; readiness and stress are empty in the payloads) plus a
   weight trend from `wellness_days` (schema v19).

5. **Threshold trend and era-correct zones.** The dated snapshots landed
   (schema v14/v15) and `DataSource.athlete_thresholds()` returns them, so the
   LTHR/threshold-pace/max-HR chart beside VO2max, the subT comparison with the
   period's threshold pace, and the race-derived series from the official
   results (schema v16) are reports-only. Normalizing zone times through each
   activity's config needs that config id on the model first: the database
   column exists, but the repository query and `Activity` drop it.

6. **Elevation in the reports.** The columns landed (schema v12) but the
   repository's activity query and the `Activity` model drop
   `elevation_gain_m`/`elevation_loss_m`, so that exposure comes first. Then:
   climb per km in the session report and the activities list, a coarse
   grade-adjusted pace from per-lap gain (the FIT payload has no altitude
   stream, so this is lap-level), trail suggestions from the ≥40 m/km
   evidence, and route difficulty on the dashboard.

7. **Strava in the session report.** A `Strava: …` line with the title, the
   description as an annotation, and a link to the activity. Depends on the
   root Strava item and on the notes/description decision in root item 1.

8. **Metrics tab.** Render the analysis catalogue from root item 24 as a
   dashboard tab next to Docs: grouped by area (load, intensity, efficiency,
   races, wellness, tools), one anchor per entry, formulas as plain text or
   code so the site stays self-contained. If the catalogue is generated, the
   tab renders the same source the Markdown does.

9. **Coaching tab.** Render the latest coaching note and an index of past
   ones, through the same Markdown-to-HTML path as Docs, with front matter
   turned into a header (date, period, focus) and the decision sections
   linked. Must be empty — not leaking — in the public demo: exclude the
   `coaching/` directory when a demo label is set, or ship a synthetic
   example note. See root item 25.

10. **Season and illness bands.** `training_periods` is stored (schema v18: 3
    seasons, 25 illness markers, 4 notes), and the source carries real ranges:
    every Intervals `SICK`/`NOTE` event has an `end_date_local` (the Feb–Mar
    2026 thyroid episode is 2026-02-08 → 2026-03-09). The derived rows are
    one-day because `training_periods_current` drops that end date. **Handed
    off**: root item 36 fixes the recompute (read `end_date_local`, test a
    ranged and a same-day payload, re-run it); this item resumes here
    afterwards. Until then the reports draw one-day markers, and the shading
    handles both shapes either way.
    - **Chart**: one shared helper shades seasons on the volume and load charts
      with a quiet label at each visible band start, and illness periods on
      recovery and the analysis pace/HR chart (which carries the efficiency
      lines), all behind the data; a one-day period draws as a thin line. Hover
      names the period and its dates.
    - **Not on Compare**: that chart overlays years on a reference-year axis, so
      real season dates cannot be placed there. Leave it out; volume, load and
      the report table carry the context.
    - **Report**: a `Seasons` table in the period report (label, kind,
      start–end or ongoing, days) and the illness days inside the range.
    - **Policy**: shade only, never exclude illness from aggregates; the
      efficiency card makes the baseline shift the signal, not noise to remove.
    - **Demo**: write three seasons and a couple of illness ranges (one
      multi-day, e.g. the story's injury) through `upsert_training_period`, so
      bands and the table are exercised.
    - **Tests**: visible-range filtering, ranged versus one-day rendering,
      labels, the seasons table, no periods leaving a chart unchanged, and demo
      coverage.

11. **Periodic demo review.** Recurring upkeep, not a feature: at each
    release tag and schema bump, re-read the reports against the demo
    athlete's story — does every tab still show the era it describes, do new
    fields have demo data, and do the race times, workout paces and VO2max
    still agree? Keep the seed fixed so the output stays diffable. See root
    item 26.

12. **Click a point to open its activity.** The charts are the place an outlier
    is noticed, but the activity page is only reachable from the activities
    table, so inspecting a strange pace/HR point means searching for the date
    by hand. Make single-activity points clickable.
    - **Mechanism**: carry the activity id in `customdata` and attach a
      `plotly_click` handler that navigates to `activity/<id>.html` — through
      `to_html(post_script=...)` or one small bundled script, so it stays a
      single implementation. Ctrl/cmd/middle click opens a new tab; the hover
      text says "click to open".
    - **Scope**: charts where one point is one activity — the pace/HR scatter
      (analysis and compare), the race log-log chart, the PB progression steps,
      and the subT panels (a work rep links to its session). The stacked bars
      (volume, time, load, overview) are daily or weekly aggregates and are
      left alone; linking one arbitrary activity of the day would be a lie.
    - **Static constraint**: the site still does no data fetching — this is
      navigation only, and it must degrade to a plain chart when the id is
      missing.
    - **Tests**: the trace carries `customdata`; the rendered HTML contains the
      handler; a chart without ids still renders; the URL is
      `activity/<id>.html` (`race/<id>.html` for race points) relative to the
      page.
    - **Cost, measured (parked 2026-11-15).** The handler is cheap; coverage
      is not. The dashboard writes activity pages only for the recent list
      (50), while the charts reach back years, so a clickable point needs its
      page written: ~1,300 pages in the demo (~+9 MB, ~+2 s of build) and
      ~2,800 on the real log (~+20 MB, ~+4-6 s), one lap query each. The
      detail loop must also batch its per-day wellness and events lookups
      into two range queries, because it would go from ~50 distinct days to
      ~2,800.
    - **Plan when it resumes.** Build the href in Python (`activity_href`
      moves to `links.py`) and emit one `CHART_LINKS_JS` from `page()` when
      `plotly=True`, attaching to every `.js-plotly-plot`; take the nearest
      point that carries `customdata`, because the race and subT charts
      hover `x unified` and return every trace at that x. Ctrl/cmd-click
      opens a new tab. Every plotted activity gets a page (the pace/HR
      scatter and subT panels link to it); races and PB steps open the
      existing `race/<id>.html` instead, which adds no pages.

13. **Calendar view** (idea). A month grid where each day carries that day's
    sessions — completed, planned, missed — plus races, illness and season
    shading, and optionally wellness markers. The activities tab and the
    overview are chronological but not spatial; a calendar is how the shape of
    a week or a block is normally read.
    - **Shape**: one static page per month (`calendar/2026-11.html`) with
      previous/next links, or a single year page with twelve grids. The first
      navigates better on a phone, the second is one file.
    - **Cell content**: sport and name, duration/distance, load; done versus
      planned styling; a `missed` marker for a past plan with no activity; a
      race badge; a review flag. Clicking an activity opens its page.
    - **Cheap alternative first**: a year heat map — one square per day,
      coloured by load or distance, with a hover tooltip — shows the training
      shape in a single page with no navigation. Worth trying before the full
      grid.
    - **Depends on**: `event_activity_links` (schema v21) for done/planned/
      missed, and `training_periods` (schema v18) for illness and season
      shading.
    - **Open**: month grid or heat map first; wellness markers in the cells
      (they crowd it); whether it complements or replaces the activities tab;
      and how it degrades on a phone.

14. **Efficiency scope: an all-runs series.** The floor landed at 40 min, but
    every long run is still invisible to the trend, because the steady
    aggregate stops at 75 min (root item 31).
    - **All-runs series**: only after the lab passes it — a second labelled line
      over every run with HR, distance and duration, never merged into the
      steady aggregate. Both lines carry their own label.
    - **Card**: the efficiency card gains the second series.
    - **Tests**: the all-runs line includes a long run and a short easy run;
      the steady line does not; both labels render.

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
  and labels Trail/Other bests as raw in the tables;
- planned-event pages: a planned and a missed row link to their page, the
  page renders zones and methods, and a matched event shows the approximate
  plan-vs-actual table;
- streaks: gaps split, a ride does not extend, the minimum duration, two runs
  on one day, the current streak with and without today, the distance
  tie-break, the limit, and the report's shape;
- collapsible tables: a long table renders the toggle and the count with every
  row still in the HTML, a short or key-less one stays plain, and the demo's
  activities tab collapses;
- weather: `format_weather` variants, the point lookup, the hover and coverage
  note, per-year shares, the cached lookup, and the demo's weather lines;
- subT efficiency ranges: per-rep low/high (varied reps, a single rep, a rep
  without HR), the sticks and hover, the absence of extra trend lines, and the
  axis ignoring one extreme rep;
- fartlek: the stored method classifies as `quality/fartlek` even with a
  "tempo" name, keeps the session out of the subT/LT1 sets, and the demo now
  carries one;
- newest-first periods in the Compare tables and the subT blocks, the
  Overview page no longer carrying the planned report, the per-year
  efficiency lines (values, pale-run contrast, and the no-steady-run case),
  the analysis charts' planned traces, and the collapsible Markdown tables.

New work should add:

- device-timeline coverage, once the field lands.
