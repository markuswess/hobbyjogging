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

- **Compare tab and chart.** `compare.html` renders one EWMA line per
  calendar year over a fixed Jan–Dec axis (metric and window chosen with
  `--compare-metric volume|time|load|runs` and `--compare-window N`,
  default volume/42d; the current year stops at today and is marked) plus
  the year and month comparison reports. The EWMA runs across the whole
  history, so each year line starts on the previous year's close. Also
  `charts.sh compare`.
- **Pace vs HR scatter.** `charts.sh pace-hr` and the Analysis tab plot one
  point per run: linear speed (m/s, labelled in min/km ticks) against
  average HR, coloured by date from blue (oldest) to red (newest) with a
  year colour bar.

- **Recovery readiness bands.** The recovery chart shades three bands
  behind each panel using the last 42 days: HRV green at/above its
  baseline, amber down to one standard deviation below, red below;
  resting HR mirrored; sleep green 7-9 h, amber 6-7 h or 9-10 h, red
  outside. Fewer than seven values in the baseline window means no HRV/RHR
  bands. A small colored key sits at the top right of the chart and the
  dashboard note explains the thresholds.

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
4. **Efficiency (m/beat).** Meters covered per heartbeat: the linear,
   intuitive efficiency metric (higher is better, unlike pace/HR or HR/pace,
   which are reciprocal and average badly). No schema change — compute on
   read.
   - **Helper** (`analysis/efficiency.py`): `m_per_beat(distance_m,
     duration_s, avg_hr) = distance_m / (avg_hr * duration_s / 60)`, plus
     `activity_efficiency`, `interval_efficiency`, and
     `aggregate_efficiency` = **Σdistance / Σbeats**, never the mean of
     ratios. Drop samples missing HR, distance, or duration.
   - **Session report**: `- Efficiency: 1.24 m/beat` after Pace / Avg HR.
   - **Activities table**: an `eff` column (2 decimals), not in the defaults.
   - **subT**: `SubtPoint` gains `efficiency` plus the raw `distance_m` /
     `beats` so every aggregate stays weighted. Print it on the work-rep
     lines and add a weighted Efficiency column to the subT summary tables.
   - **subT chart**: a third panel in `plot_subt` ("Efficiency", m/beat)
     beside Pace and HR, with the same category colors and window — the
     efficiency analogue of the existing two panels. Smooth with a rolling
     **weighted** mean (Σdistance / Σbeats), not an EWMA of per-point ratios;
     document which one ships.
   - **subT EWMA report**: an efficiency row/section using the same weighted
     aggregation.
   - **Compare page**: add `efficiency` to `COMPARE_METRICS`. It is not
     additive like volume/time, so the daily value is Σdistance/Σbeats over
     days with HR data, and rest days carry the previous value forward
     instead of contributing 0. Axis label `m / beat`.
   - **Axis range**: pick a fixed range like the other charts (roughly
     1.0–1.6 m/beat for runs) or keep it auto until the data settles.
   - **Caveats**: HR lag understates short reps (compare same rep lengths,
     prefer ≥5 min); heat, terrain and fatigue move the number, so it is a
     within-similar-conditions trend. Runs only for display; the helper stays
     sport-agnostic but rides are a different scale.
   - **Tests**: known value (10 000 m / 3 600 s / 150 bpm → 1.111 m/beat),
     missing pieces → `None`, weighted aggregate vs naive mean, subT group
     with partial HR coverage, compare series skipping rest days, and `-` in
     the renderers when absent.
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
