# Next up: reports package

Updated 2026-11-12.

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
  shows volume, time, and efficiency charts (182-day EWMA by default).
  Only the five most recent years are visible by default; older years stay
  in the legend and can be re-enabled. Also `charts.sh compare`.
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
  invented 18-month athlete (seed, periodized plan, intervals, zone times,
  wellness with an illness and a travel week, planned events, two future
  races, four shoes) through `TrainingWriter`, with no `source_records` or
  personal data. `dashboard --demo-label TEXT` adds an opt-in banner on every
  page. Same seed gives identical content; tests cover counts, complete
  zones, future races, review opt-in, size, and a full dashboard build.
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

## Next

1. **One segment table in the session report.** The session report prints
   `### Intervals` and `### Laps` unconditionally, so a structured workout
   shows the same segmentation twice and an auto-lapped easy run shows one
   whole-activity interval next to its splits.
   - **Why**: of the 2,832 activities that have both, only 29% share a segment
     count (37% once the empty trailing interval is filtered out — see the
     maintenance `drop_empty_intervals_v1`). Laps are device splits (auto-lap,
     manual), intervals are Intervals.icu's typed reps (`WORK`/`RECOVERY`,
     group ids). They are complementary, not duplicates.
   - **Rule**: render one table per activity —
     - intervals when `len(intervals) > 1` (they carry types and groups);
     - otherwise laps when `len(laps) > 1` (splits);
     - otherwise neither: a single segment just restates the activity.
   - Keep the subT "Work reps" section and the interval-based analysis
     untouched; this is only the raw segment tables.
   - **Tests**: intervals>1 → only the interval table; laps only → only the
     lap table; intervals=1 with laps>1 → laps; intervals>1 with laps=1 →
     intervals; one row on each side → no table.
   - **Docs**: the reports README session section, and a line in
     `docs/ARCHITECTURE.md` or `SOURCE_NOTES.md` stating the two concepts
     (device splits vs detected reps) so nobody tries to merge them again.
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
