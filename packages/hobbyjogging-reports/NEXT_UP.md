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
  Spec and root-session follow-ups remain in the handoff below.

## Handoff: synthetic demo database

> **Done (reports side).** `demo-db`, the `--demo-label` badge, tests, and
> README docs are implemented. The root session still owns `demo.sh`, the
> Pages workflow, and the repo docs.

Root session asked for a public, representative dashboard on GitHub Pages
without any personal data. Build the generator and badge here; the root session
owns `demo.sh`, the Pages workflow, and the repo docs.

### Goal

A deterministic synthetic athlete (no real rows, no `data/laufen.ods`, no real
DB access) that produces a demo DB rich enough for every dashboard page,
roughly 18 months ending at the build date, 4–6 sessions per week, ~400
activities, 1–3 MB without raw payloads.

### Files

- `src/hobbyjogging_report/demo.py` — generator (seed, persona, plan, write).
- `src/hobbyjogging_report/report_commands.py` — `run_demo_command`.
- `src/hobbyjogging_report/cli.py` — `parse_demo_args`.
- `src/hobbyjogging_report/commands.py` — register `demo-db` with
  `needs_source=False`.
- `tests/test_demo.py` — generator tests.
- `README.md` — section with the command and the synthetic-data note.

### CLI

```bash
python -m hobbyjogging_report demo-db --out build/demo.db \
  [--months 18] [--seed 7] [--today YYYY-MM-DD] [--with-review-items]
```

- `--out` is required; refuse to overwrite unless `--force`.
- Never default to `HOBBYJOGGING_DB`; open `--out` explicitly with
  `open_database()` and write through `TrainingWriter`.
- `--today` defaults to the build date so the site stays current.

### Data to generate

- Activities with sport, dates, start times, names/descriptions from an
  invented vocabulary, duration/elapsed/moving, distance, avg HR, load,
  RPE/feel/intensity, VO2max trend.
- Workout methods/targets per session; quality is derived on read. Use
  `continuous` + `threshold` for sustained work (no `tempo` method).
- Pace and HR zone times whose seconds sum to the session duration.
- `activity_intervals` for quality sessions (4–8 reps with recoveries).
- Wellness every day (HRV, resting HR, sleep), correlated with 7-day load,
  plus one short illness dip and a travel week.
- Planned events for 12–16 weeks ahead plus 2 races inside the 180-day race
  window, with zone times and methods/targets.
- 4–6 fictional shoes linked to activities.
- No `source_records` (the database source then has no external links).
- Review state: none open by default; `--with-review-items` adds a couple for
  health-page screenshots.

### Realism model

Periodized blocks (3 build weeks + recovery week, base/build/peak/taper),
easy runs, long runs, intervals, sustained threshold, cross-training, and
strides. Threshold pace improves slowly and HR at pace declines; load follows
duration × intensity. Session mix and weekly volume should look plausible in
the overview, time-by-zone, load, recovery, and compare views.

### Dashboard badge

Add `--demo-label TEXT` to the dashboard parser and `build_dashboard`, rendered
as a small banner on every page (e.g. “Synthetic demo data — not a real
athlete”). Keep it opt-in so normal builds are unchanged. `dashboard.sh`
forwards the flag automatically.

### Tests

- Fixed seed → identical DB (ids, rows, counts).
- Activity/wellness/event/equipment counts in the expected ranges.
- Every run has distance, HR, load, and pace zones; zone seconds sum to the
  session duration.
- Races are in the future; planned events extend the horizon.
- No `source_records`; no open review items by default.
- DB size under a small cap (e.g. 5 MB).
- A generated DB builds a dashboard without errors and with a clean health
  banner.

### Done when

`demo-db` + `dashboard --demo-label ...` produce a complete site locally, the
tests pass, and the README documents the command. The root session then wires
`demo.sh` and GitHub Actions.

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
4. **Shoe mileage.** Distance per equipment item from canonical data:
   `equipment` → `activity_equipment` → `activities.distance_m`. No schema
   change — 10 shoes and 1,842 links are already there (e.g. Lunge C-Dur
   3,774 km / 283 runs, Brooks Adrenaline 20 2,878 km / 184 runs). Show total
   distance and session count per shoe, wear against `target_distance_m` when
   set (currently NULL for every shoe), and retirement candidates
   (`retired_on` empty, beyond the target). A `shoes` report plus a dashboard
   card; compute in `analysis/`, render separately.
5. **Session report completeness** (low priority, last). The `session` report
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
