# Next up: reports package

Updated 2026-11-13.

Current focus: the demo data; every other item waits on a core or root
change.

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
  cycling series waits on the core sport column in root's VO2max bug.

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
  keep the plain label. The chart already filtered to running. The value's
  true sport still waits on the core column in the root VO2max bug.

- **A bigger, calmer overview chart.** The main chart is 700 px tall
  instead of 520, with 10 px ticks and legend, compact trace names
  (`hard 7d`, `total 42d`, `planned hard`, ...), a two-row legend, and the
  card heading "Overview" instead of "Daily running minutes". A wrapped
  horizontal legend fills in reverse trace order, so the layout sets
  `traceorder: normal`; tests pin the height, font, entry width and names.

## Bugs

_None._

## Next

Items 1-8 and 11 need a core or root change first, and 9 and 10 need root
items 24 and 25. Items 13-17 are reports-only; 18 needs the lab gate in
root item 31, and 12 is recurring upkeep.

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

13. **Demo: a realistic VO2max curve.** The demo's VO2max is a smooth daily
    function — `45 + (240 − p5k)·0.3` plus a 120-day sine — so it carries a
    value every day and wobbles continuously, which no watch does. Garmin
    updates the estimate only after a qualifying run and holds it in between.
    - **Step function**: sample the underlying fitness curve on quality and
      long days only, hold the value in between, and quantize to 0.1 so the
      line has plateaus instead of a daily wiggle.
    - **Story**: drop through each injury and bust and rebuild over two or three
      weeks; flatten in the Norwegian era, because threshold work moves VO2max
      less than intervals do.
    - **Runs only**: no value on rides or cross-training, which also matches the
      per-sport fix in the root bug list.
    - **Tests**: the curve has repeated values, drops at a bust, and carries no
      value on a ride; the demo coverage test still passes.

14. **Crosshair on hover.** Plotly draws a vertical line at the hovered x in the
    `x unified` charts and nothing horizontally, so reading a value off the y
    axis means following an imaginary line. Add the horizontal spike too, from
    one layout helper rather than per chart.
    - **Helper**: `_crosshair(figure)` sets `showspikes`, `spikemode="across"`,
      a thin grey `spikethickness` and `spikecolor` on both axes, and on
      `yaxis2` where a chart has one (the overview's VO2max line).
    - **Where it helps most**: the pace/HR scatter, the race log-log chart, the
      PB progression and the subT panels — a horizontal line makes a pace or a
      heart rate readable at a glance.
    - **Caveat**: on the stacked bar charts (volume, time, load) a horizontal
      spike follows the cursor, not a stack boundary, so it can point at a
      meaningless value. Use `spikesnap="data"` there or skip those charts.
    - **Tests**: the helper sets spikes on x, y and yaxis2 when present; a
      chart that already sets an axis range keeps it; the HTML contains
      `showspikes`.

15. **Click a point to open its activity.** The charts are the place an outlier
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
      `activity/<id>.html` relative to the page.

16. **Planned workouts on the activities tab.** The tab is a list of completed
    activities, so a missed session or tomorrow's workout is invisible there and
    the plan lives only on the overview and in the `planned` report. Make the
    tab a training log that carries the plan.
    - **Append, do not merge**: keep the activity rows as they are and add a row
      for every planned event with no matching activity — same date and sport
      for now, replaced by `event_activity_links` once root item 4 lands. A
      "Status" column reads `done`, `planned` or `missed` (past date, no
      activity), which is the whole point of the change.
    - **Columns**: planned rows fill date, sport, name, methods/targets and the
      planned duration/distance/load; pace, HR and feel stay empty because
      nothing was recorded. No link — there is no event page yet.
    - **Window**: the table shows the recent past plus the next 14 days, so
      tomorrow's session appears without the tab becoming a calendar.
    - **Not the CLI**: `reports.sh activities` stays activity-only; this is the
      dashboard tab.
    - **Tests**: a matched event does not duplicate its activity; an unmatched
      past event shows `missed`; a future event shows `planned`; the demo's
      planned workouts appear in the tab and the coverage test still passes.

17. **Calendar view** (idea). A month grid where each day carries that day's
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

18. **Efficiency scope: 40-minute floor and an all-runs series.** The aggregates
    use non-quality runs in 45–75 min, so a 40-minute easy run and every long
    run are invisible to the trend (root item 31).
    - **40-minute floor**: lower `STEADY_MIN_DURATION_S` to 40 min. The duration
      model's `+135/T` term makes a 40-minute run about 1.5 % lower than a
      60-minute one; print the band so the bias is visible. Raises n without
      mixing protocols, and it can ship on its own.
    - **All-runs series**: only after the lab passes it — a second labelled line
      over every run with HR, distance and duration, never merged into the
      steady aggregate. Both lines carry their own label.
    - **Card**: the efficiency card gains the floor and the second series.
    - **Tests**: a 40-minute easy run enters the steady aggregate; an interval
      session does not; the all-runs line includes it; both labels render.

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
