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
  `Trail (raw)` / `Other (raw)`. Equal times do not advance a line; tests
  cover strict improvements, ties, bucket separation and short-course
  rejection. The 2% tolerance inside a bucket waits for official race
  distances (root item 18).

## Bugs

_None._

## Next

Items 1-8 and 11 need a core or root change first, and 9 and 10 need root
items 24 and 25. Only **12** is reports-only.

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
