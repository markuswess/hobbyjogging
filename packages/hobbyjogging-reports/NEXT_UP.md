# Next up: reports package

Updated 2026-11-16.

Current focus: the demo data; 13 is parked on its page-coverage cost, 16 is a
small dashboard-only pass, and every other open item needs a core or root
change or the lab gate.

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
  qualified PB. Official race results will replace this tolerance when root
  item 18 lands.
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
  tolerance inside a bucket waits for official race distances (root item
  18).

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
  page adds an approximate plan-vs-actual table by date and sport, exact links
  wait on `event_activity_links` (root item 4), and it links back to the
  activity. An untyped note, or an event without an id, stays plain text.
  Tests cover the planned and missed rows, the matched page, zones and
  methods, and the demo link.

## Bugs

_None._

## Next

Items 1-8 and 11 need a core or root change first, and 9 and 10 need root
items 24 and 25. Of what is left, 13 is reports-only but parked because every
link needs a page for the plotted activity, 16 is a small dashboard-only
pass, 14 needs root items 4 and 30, 15's series needs the lab gate in root
item 31, and 12 is recurring upkeep. The efficiency floor and the
planned-event page landed here.

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

12. **Periodic demo review.** Recurring upkeep, not a feature: at each
    release tag and schema bump, re-read the reports against the demo
    athlete's story — does every tab still show the era it describes, do new
    fields have demo data, and do the race times, workout paces and VO2max
    still agree? Keep the seed fixed so the output stays diffable. See root
    item 26.

13. **Click a point to open its activity.** The charts are the place an outlier
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

14. **Calendar view** (idea). A month grid where each day carries that day's
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
    - **Depends on**: `event_activity_links` (root item 4) for done/planned/
      missed, and `training_periods` (root item 30) for illness and season
      shading. Without them it can only show activities and raw events.
    - **Open**: month grid or heat map first; wellness markers in the cells
      (they crowd it); whether it complements or replaces the activities tab;
      and how it degrades on a phone.

15. **Efficiency scope: an all-runs series.** The floor landed at 40 min, but
    every long run is still invisible to the trend, because the steady
    aggregate stops at 75 min (root item 31).
    - **All-runs series**: only after the lab passes it — a second labelled line
      over every run with HR, distance and duration, never merged into the
      steady aggregate. Both lines carry their own label.
    - **Card**: the efficiency card gains the second series.
    - **Tests**: the all-runs line includes a long run and a short easy run;
      the steady line does not; both labels render.

16. **Collapse the long dashboard lists.** The activities tab renders 50
    activity rows plus the planned window, and Performance renders every race
    result; on a phone those tables push the rest of the page out of reach.
    Collapse a long table behind a summary that names its row count, with the
    most recent rows still visible.
    - **Mechanism**: native markup only — no JavaScript and no build option.
      Either a `<details>` around the whole table (closed, summary
      `Activities (50)`), or a checkbox plus a `:checked` sibling rule that
      keeps the first ~20 rows visible and reveals the rest; pick one when
      implementing. Every row stays in the DOM, so the activity links and the
      browser's find still work.
    - **One place**: extend `table()` in `html.py` with an optional summary and
      row limit, so the count, the toggle and the muted "showing all N" line
      are rendered once, not per page. Count the rendered rows, never a
      hard-coded number.
    - **Where**: any table past the threshold — activities, race results, PBs,
      review items, gear. Short tables (equivalent times, upcoming races,
      category breakdown) and the Markdown reports stay as they are.
    - **Threshold**: a module constant (about 20 rows), not a flag, so a quiet
      week looks unchanged.
    - **Tests**: a long table renders the summary with the real row count and
      keeps every row in the HTML; a short one renders a plain table; the
      activities tab still carries a planned row and an activity link; the
      demo dashboard test covers the collapsed lists.

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
  plan-vs-actual table.

New work should add:

- device-timeline coverage, once the field lands.
