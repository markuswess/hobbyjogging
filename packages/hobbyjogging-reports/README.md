# hobbyjogging-reports

This package is part of the `hobbyjogging` workspace. Run the commands below
from the repository root.

Generate daily, weekly and monthly summaries from the canonical hobbyjogging
database.

## Data sources

Reports depend on the `DataSource` protocol from `hobbyjogging-core`. The
only adapter is `DatabaseSource`, which reads the canonical SQLite database;
raw payloads stay in `source_records`, so there is no live API path to keep
in sync with the importers.

## What it does

Reads activity, wellness and planned-session data through the canonical
database `DataSource` and produces Markdown training reports plus a static
HTML dashboard:

- **daily** — Yesterday's activities, today's planned workout,
  and recovery (HRV / RHR / sleep) from the last nights.
- **overview** — 7/42/182-day EWMAs for runs, cross sessions, run time,
  km, load, and Z3+4, plus the planned weekly average for the next 14
  days.
- **weekly** — Aggregated running and cross-training stats,
  quality sessions and recovery over the last 7 days.
- **monthly** — Same summary over the last 30 days.
- **yearly** — Same summary over the last 365 days.
- **all** — Daily + weekly + monthly + yearly in one report.
- **dashboard** — Generate the static HTML dashboard (weekly overview,
  recovery and health, activity list, activity detail pages, data health);
  writes a directory and prints its path.
- **report** — A summary report for an arbitrary inclusive date range
  (`--days`, `--from`, `--to`).
- **subt-report** — All subT and LT1 sessions in a range, grouped by
  short/medium/long/LT1. Shows work-block and summary tables.
- **subt-ewma-report** — 7/42/182-day EWMAs of the work-interval pace and
  session heart rate for short, medium, long, and LT1, ending today.
- **recovery-report** — HRV, resting HR, and sleep with simple 7/42/182-day
  moving averages ending today, plus the last four nights' values in the
  same layout as the daily report. Missing days are skipped.
- **planned** — Upcoming planned workouts starting tomorrow, as a compact
  key-facts table (date, weekday, workout, sport, distance, time, planned
  Z3+4 time, load); ends with weekly-average total time and Z3+4 time.
  Next 28 days by default.
- **session [date|id|last]** — Detailed report for one session, chosen by
  date, activity id, or `last` (the default): category, workout methods and
  targets, totals, zones, description, the full interval table, subT/LT1 work
  reps, and Intervals/Garmin Connect links when the source knows them.
- **debug** — Dump raw API data (activities, wellness, events,
  intervals).
- **overview-chart** — the main training chart (`./charts.sh overview`):
  daily running minutes on a 0–90 minute axis, stacked hard (Z3+Z4) /
  easy (Z1+Z2) / unzoned, with hard and total 7/42/182-day EWMAs and
  hatched planned days, plus the Garmin VO2max standing value as a black
  line on a second axis on the right. Bars above 90 minutes are marked
  and clipped.
- **volume** — Weekly running volume chart with 182/42/7-day
  distance averages and the planned weekly distance; last 90 days by
  default. The axis is fixed at 0–130 km/week; larger weeks are marked.
- **load** — Daily training load with 182-day base, 42-day fitness,
  and 7-day fatigue exponentially weighted averages, plus planned load and
  the three session-RPE EWMAs on a right-hand axis (RPE carries the last
  rated value between sessions). The axis is fixed at 0–150 load with the
  RPE axis at 0–6, so one RPE point lines up with 25 load units.
- **time** — Weekly running time stacked by pace zone (Z1 on top, higher zones
  at the bottom; Z1/Z2 in blues and Z3/Z4 in reds), with 182/42/7-day time
  averages, a share-of-week panel, a per-zone EWMA panel, and planned weekly
  time including planned pace zone distributions. The axis is fixed at
  0–10 h/week; larger weeks are marked.
- **recovery** — HRV, resting HR, and sleep trends with a rolling
  calendar-day average and planned-workout markers. Readiness bands shade
  the background: HRV green at/above its 42-day baseline, amber within one
  standard deviation below, red below; resting HR mirrored; sleep green
  7–9 h, amber 6–7 h or 9–10 h, red outside.
- **subt** — subT and LT1 work intervals over the last 365 days by
  default, with pace and average HR as two stacked panels sharing a
  date axis. Dots are color-coded by rep length (short/medium/long)
  or LT1; pace ranges show fastest–slowest, HR ranges show
  average–max, and both metrics have a 42-day EWMA trend line. The pace
  axis is fixed at 4:20–3:15 min/km (faster up) and HR at 140–180 bpm.
- **vo2max** — Garmin running VO2max values as daily dots with 7- and
  42-day exponentially weighted averages; last 365 days by default.
- **pace-hr** — Scatter of average speed vs average heart rate, one point
  per run, for aerobic-efficiency analysis. The x axis is linear speed
  (m/s) labelled in min/km ticks; the point colour runs from blue (oldest)
  to red (newest) with a year colour bar, and a least-squares line is fitted
  to the older and newer half of the runs (parameters on the chart and
  printed by the CLI).
- **compare** — One EWMA line per calendar year over a fixed Jan–Dec axis;
  `--metric volume|time|load|runs` and `--window N` (default 182) choose the
  metric and smoothing. The EWMA is computed over the whole history, so
  each year starts on the previous year's closing value. The current year
  is partial and marks today.
- **classify** — Print the workout category for each activity over
  the last N days (default 30).
- **activities** — Table of recent activities (default: last 20), with
  selectable columns.

## Setup

Install dependencies:

    uv sync

Create environment (`.env`):

    export HOBBYJOGGING_DB=~/projects/laufen_private/data/db/hobbyjogging.db
    export HOBBYJOGGING_DASHBOARD_DIR=~/projects/laufen_private/reports

The dashboard is written to
`$HOBBYJOGGING_DASHBOARD_DIR/dashboard` when that variable is set, and to
`data/dashboard` otherwise.

Run:

    uv run --env-file .env python -m hobbyjogging_report daily
    uv run --env-file .env python -m hobbyjogging_report overview
    uv run --env-file .env python -m hobbyjogging_report weekly
    uv run --env-file .env python -m hobbyjogging_report monthly
    uv run --env-file .env python -m hobbyjogging_report yearly
    uv run --env-file .env python -m hobbyjogging_report all
    uv run --env-file .env python -m hobbyjogging_report dashboard
    uv run --env-file .env python -m hobbyjogging_report report --days 90
    uv run --env-file .env python -m hobbyjogging_report subt-report --days 90
    uv run --env-file .env python -m hobbyjogging_report planned
    uv run --env-file .env python -m hobbyjogging_report activities --limit 20
    uv run --env-file .env python -m hobbyjogging_report session
    uv run --env-file .env python -m hobbyjogging_report session 2026-02-22
    uv run --env-file .env python -m hobbyjogging_report session 7a2bf884-2b25-585f-8430-530749f80afa
    uv run --env-file .env python -m hobbyjogging_report debug
    uv run --env-file .env python -m hobbyjogging_report volume [output.png]
    uv run --env-file .env python -m hobbyjogging_report overview-chart [output.png]
    uv run --env-file .env python -m hobbyjogging_report load [output.png]
    uv run --env-file .env python -m hobbyjogging_report time [output.png]
    uv run --env-file .env python -m hobbyjogging_report recovery [output.png]
    uv run --env-file .env python -m hobbyjogging_report subt [output.png]
    uv run --env-file .env python -m hobbyjogging_report vo2max [output.png]
    uv run --env-file .env python -m hobbyjogging_report classify [days]

Every command supports `--help`, for example:

    uv run --env-file .env python -m hobbyjogging_report time --help
    ./charts.sh time --help
    ./reports.sh session --help

### Quick reports

`reports.sh` wraps the long `uv run` command, copies the generated
Markdown to the clipboard with `wl-copy`, and renders headings, lists
and tables for the terminal:

    ./reports.sh                 # daily
    ./reports.sh daily
    ./reports.sh overview
    ./reports.sh monthly
    ./reports.sh report --days 90
    ./reports.sh report --from 2026-01-01 --to 2026-03-31
    ./reports.sh subt-report --days 90
    ./reports.sh planned
    ./reports.sh planned --days 56
    ./reports.sh session 2026-10-22
    ./reports.sh session 7a2bf884-2b25-585f-8430-530749f80afa
    ./reports.sh session last

The static dashboard has its own wrapper:

    ./dashboard.sh
    ./dashboard.sh --days 30 --activities 100
    ./dashboard.sh --reports overview,daily,planned
    ./dashboard.sh --no-open

`dashboard.sh` also opens the generated `index.html` in the browser. Use
`--no-open` or `NO_OPEN=1` to skip that.

The clipboard receives the original Markdown before terminal
formatting, so pasting gives clean Markdown. Use `NO_COPY=1` to skip
the clipboard, `NO_COLOR=1` to disable ANSI colours, or `NO_PRETTY=1`
to print raw Markdown.

When stdout is a terminal, the direct CLI also displays reports with
the same formatting. Redirected or piped output remains raw Markdown.

### Quick charts

`charts.sh` wraps the chart commands and prints the generated file path:

    ./charts.sh                          # weekly volume, last 90 days
    ./charts.sh overview
    ./charts.sh overview --chart-days 90 --future-days 21
    ./charts.sh volume --days 90
    ./charts.sh volume --output dist.png
    ./charts.sh volume --planned-days 0
    ./charts.sh load --days 180
    ./charts.sh load --base-days 182 --fitness-days 42 --fatigue-days 7
    ./charts.sh time --days 90
    ./charts.sh time --zones 4 --zone-window base
    ./charts.sh recovery --days 90
    ./charts.sh subt --days 365
    ./charts.sh subt --output subt.png
    ./charts.sh subt --from 2026-01-01 --to 2026-06-30 --output subt.png
    ./charts.sh vo2max --days 365

Charts accept the same `--days` / `--from` / `--to` / `--output` options
as the direct CLI.

### Load chart

`load` shows daily training load as bars plus three exponentially weighted
averages:

- **Base (182d)** — long-term training base
- **Fitness (42d)** — medium-term fitness
- **Fatigue (7d)** — short-term fatigue

The averages use time-constant EWMA (`alpha = 1 - exp(-1 / days)`) and are
computed with history before the displayed range. Planned load continues
the averages into the future as dashed lines. Change the horizons with
`--base-days`, `--fitness-days`, and `--fatigue-days`.

Activities without `training_load` are treated as zero load and get a note.
The database currently only has load data from late 2025, so the 182-day
line will still be warming up in earlier charts.

The `volume` chart applies the same three windows to daily running
distance and scales them to weekly equivalents, so volume and its trends
share one `km / week` axis. Volume bars are Monday–Sunday weeks.

### Time chart

`time` shows weekly running time in hours as Monday–Sunday bars,
stacked by pace zone. It uses running activities only and defaults to
four zones (`Z1`–`Z4`).

The top panel overlays the 182/42/7-day averages of total running time,
scaled to weekly hours. The lower panel stacks the pace-zone EWMAs for the
selected `--zone-window` (`base`, `fitness`, or `fatigue`; default
`fitness` / 42 days), also in weekly hours. Its boundary lines are
cumulative: `Z4`, `Z3+Z4`, `Z2+Z3+Z4`, then all zones.

Planned running workouts that carry a pace zone distribution are drawn as
hatched stacked bars over the actual week. Zones beyond `--zones` fold
into the last displayed zone, and `SS` buckets are ignored. Planned zones
of other kinds (HR or power) are ignored so the stack matches the actual
pace zones. Weeks whose planned workouts have no pace zones keep the
dashed total-time outline. The lower EWMA panel continues through planned
pace zones as dashed projections, using planned daily zone time and
treating unplanned days as rest.

    ./charts.sh time
    ./charts.sh time --days 90
    ./charts.sh time --zones 4 --zone-window base
    ./charts.sh time --base-days 182 --fitness-days 42 --fatigue-days 7

Time outside recorded pace zones is shown as an `Unzoned` segment, so each
bar still totals the recorded running time. Weekly charts expand the
requested range to whole Monday–Sunday weeks.

### Recovery chart

`recovery` shows HRV, resting HR, and sleep as three panels sharing a
date axis:

- daily values as points,
- a calendar-day rolling average (default 7 days).

    ./charts.sh recovery
    ./charts.sh recovery --days 90
    ./charts.sh recovery --window 14

Missing values are skipped rather than treated as zero, so a gap in the
wellness data does not pull an average down.

### VO2max chart

`vo2max` plots Garmin's running VO2max as one dot per day, with 7-day
and 42-day exponentially weighted averages. It uses running activities
only and ignores Runalyze estimates and cycling/swimming VO2max values.

Same-day Garmin values are averaged. Days without a measurement carry
the last value forward, so the averages track the metric's standing
value rather than dropping to zero. The averages use
`alpha = 1 - exp(-1 / days)` and 210 days of history before the display
range. The chart defaults to the last 365 days.

    ./charts.sh vo2max
    ./charts.sh vo2max --days 365
    ./charts.sh vo2max --from 2026-01-01 --to 2026-06-30

### Planned workouts

The volume, load, time, and recovery charts include planned workouts.
Unless `--to` is given, they extend the right edge of the chart by
`--planned-days N` (default 28); `--planned-days 0` disables the
extension.

- **volume** — planned running distance per Monday–Sunday week, as a
  dashed target line.
- **time** — planned running time per week, as an outlined bar over the
  actual pace-zone stack. Planned pace zone distributions, when
  available, are drawn as hatched stacked bars; other planned events
  keep the total-time outline.
- **load** — planned load per day for all sports, as outlined daily
  bars.
- **recovery** — one tick per planned workout along the bottom of the
  sleep panel.

Events without a sport type (illness or travel notes) are ignored.
The volume chart also skips planned events without a distance.

The 182/42/7-day EWMA lines continue through the planned days as dashed
segments, using planned daily distance, time, or load and treating
unplanned days as rest. The time chart's weekly pace-zone stack and its
pace-zone EWMA panel include planned pace zones; the recovery averages
stay actual-only.

## Session detail

`session` renders one detailed activity report at a time:

    ./reports.sh session                 # most recent session
    ./reports.sh session last            # same
    ./reports.sh session 2026-10-22      # all sessions on that day
    ./reports.sh session <activity-id>   # one exact activity

The report includes the activity id and date, category, duration/elapsed
time, distance and pace, HR/load/RPE/feel/intensity, equipment, pace and
HR zones, a fenced description block, a table of every recorded interval,
and the subT/LT1 work-rep summary when applicable.

Id lookup scans recent history and expands up to about 20 years. If an
activity is hidden by an open import review item, add `--include-review`.

## Planned workouts report

`planned` always starts tomorrow, even if `--from` is today or in the past.
The table lists the planned sessions and ends with a summary:

- total planned time per 7 days;
- planned Z3+4 time per 7 days.

Both are averaged over the report range; a range shorter or longer than a
week is scaled to a weekly rate.

## subT report

`subt-report` collects name-marked subT and LT1 sessions in a range and
groups their work into short, medium, long, and LT1 tables:

    ./reports.sh subt-report                 # last 90 days
    ./reports.sh subt-report --days 365
    ./reports.sh subt-report --from 2026-01-01 --to 2026-06-30

A row is one work block: all same-category reps in a session are merged.
A session with work in several categories therefore appears in each
relevant group. LT1 sessions always go to the LT1 group, and sessions
without usable work reps are omitted.

## subT EWMA report

`subt-ewma-report` smooths each category's work pace and session heart rate
over the last 7, 42, and 182 days:

    ./reports.sh subt-ewma-report

```
| Category | 7-day EWMA | 42-day EWMA | 182-day EWMA |
|---|---:|---:|---:|
| Short | 3:28/km | 3:29/km | 3:33/km |
| Medium | 3:38/km | 3:36/km | 3:41/km |
| Long | 3:43/km | 3:45/km | 3:47/km |
| LT1 | 3:48/km | 3:51/km | 3:58/km |
```

A second table repeats the shape for average heart rate. Days between
sessions keep the last measured value, so the lines describe the standing
pace and HR of each category. The report also tops the NSA dashboard tab.

The report starts with a summary table (sessions, reps, weekly work time
and distance, weighted pace, average/max HR) and then shows one table
per non-empty category. Work pace, fastest/slowest rep pace, and HR are
derived from the same work reps used by the classification and charts.

## Activities table

`activities` lists recent activities as a Markdown table.

    ./reports.sh activities                          # last 20 activities
    ./reports.sh activities --limit 50               # last 50
    ./reports.sh activities --days 30                # everything in the last 30 days
    ./reports.sh activities --days 90 --limit 10     # newest 10 from the last 90 days
    ./reports.sh activities --add id,category        # defaults plus id and category
    ./reports.sh activities --columns date,name,distance

Without a date range, the table covers the most recent activities up to
`--limit` (default 20). With a range, every activity in the range is shown,
capped by `--limit` if given. Rows are newest first.

Default columns: date, sport, name, duration, distance, pace, avg HR,
load, RPE, feel, methods, targets. `--columns` replaces them (in the order
given); `--add` appends. Available columns: id, date, started (UTC), sport,
name, duration, elapsed, distance, pace, avg_hr, load, rpe, feel, intensity,
category, methods, targets. The category is only computed when requested,
and uses intervals for subT/LT1-named sessions. Methods and targets are the
canonical set tokens with their display labels.

## Date ranges

`report`, `subt-report`, `volume`, `load`, `time`, `recovery`,
`subt`, `classify` and `activities` accept:

    --days N              look back N days from today
    --from YYYY-MM-DD     start date (inclusive)
    --to YYYY-MM-DD       end date (inclusive)

`planned` uses the same options but looks forward:

    --days N              next N days from today (default 28)
    --from YYYY-MM-DD     start date (inclusive)
    --to YYYY-MM-DD       end date (inclusive)

The chart commands also accept:

    --output FILE         chart output path

Examples:

    uv run --env-file .env python -m hobbyjogging_report report --days 90
    uv run --env-file .env python -m hobbyjogging_report report --from 2026-01-01 --to 2026-03-31
    uv run --env-file .env python -m hobbyjogging_report classify --days 90
    uv run --env-file .env python -m hobbyjogging_report classify --from 2026-01-01 --to 2026-03-31
    uv run --env-file .env python -m hobbyjogging_report subt --from 2026-02-01
    uv run --env-file .env python -m hobbyjogging_report subt --to 2026-06-30 --days 120 --output subt.png
    uv run --env-file .env python -m hobbyjogging_report planned
    uv run --env-file .env python -m hobbyjogging_report planned --days 56
    uv run --env-file .env python -m hobbyjogging_report planned --to 2026-12-31

Rules:

- `--from` and `--to` together select exactly that inclusive range.
- `--from` alone runs from that date through today.
- `--to` alone counts back `--days` (or the command default) from that date.
- With neither, count back `--days` (or the command default) from today.
- `planned` looks forward instead: `--from` alone runs `--days` from
  that date, `--to` alone runs from today through that date, and with
  neither it lists the next `--days` days (default 28).
- The old forms still work: `classify 30` and `subt out.png`.
  An explicit `--days` / `--output` wins when both are supplied.
- The fixed presets (`daily`, `weekly`, `monthly`, `yearly`, `all`)
  keep their existing windows; use `report` for a custom range.
  `report` defaults to the last 30 days when no range is given.

## Workout categories

```
quality
├── intervals
│   ├── subt-short   (avg rep <= 4:00)
│   ├── subt-medium  (avg rep 4:01-7:00)
│   ├── subt-long    (avg rep > 7:00)
│   ├── lt1
│   └── other
├── longrun          (> 90 min)
├── race
├── race-support     (warmup / cooldown)
└── tempo
non-quality
├── easy
└── recovery
cross-training
unknown
```

Weekly, monthly and yearly reports include a **category breakdown**
table: sessions, time, load, and each category's share of the period.
SubT sessions are refined by rep length when interval data is available.

Rules (`classify.py`):

- **quality**: RPE > 3. RPE exactly 3 can also be quality when the
  session has explicit quality content (race/subT/LT1/tempo) or its
  intensity/zones indicate quality. If RPE is missing, infer from
  intensity (IF >= 0.85 or >= 25% of time in Z3+); if impossible ->
  `unknown`.
- **longrun**: activity longer than 90 min, even with low RPE —
  unless race/subt/lt1/tempo content takes precedence.
- **recovery**: RPE = 1 and shorter than 40 min.
- **race-support**: race warm-ups and cool-downs, identified by name
  (`warm up` / `cool down`); overrides the RPE rule, since they are
  usually RPE 1–3.
- **cross-training**: any non-run activity (hiking, cycling, kayaking).
- Sub-type keywords come from the activity **name** only; descriptions
  often mention alternatives (e.g. "did 3x10@LT1 instead of subT").
  Execution (RPE/intensity) normally decides *whether* the session was
  quality; at RPE 3, explicit content (or a sustained block) can tip it
  into quality.
- **LT1 wins over subT** when both appear in the name.
- Rep length ignores work intervals shorter than 60 s (strides).
- Older activities may label warm-up, cool-down and recovery jogs as
  `WORK`. Work reps are detected as the fast pace cluster (strides and
  GPS artifacts ignored, slow low-HR warm-ups removed), so
  classification, reports and the subT chart use the same reps.

## Feel ratings

Intervals.icu's 1–5 feel rating is shown alongside RPE in the daily
and session reports (`- Feel: 2 (Good)`). Weekly, monthly and yearly
reports show the average feel for running and cross-training
separately. The scale is reversed compared with some watches:

| Feel | Meaning |
|---:|---|
| 1 | Strong |
| 2 | Good |
| 3 | Normal |
| 4 | Poor |
| 5 | Weak |

## Static dashboard

`dashboard` writes a self-contained static HTML site to
`$HOBBYJOGGING_DASHBOARD_DIR/dashboard` when that variable is set, or to
`data/dashboard` otherwise. `--output DIR` overrides the location exactly.
`./dashboard.sh` prints the generated directory and opens the browser;
`./sync.sh` regenerates it after a successful sync without opening a browser.

    ./dashboard.sh
    ./dashboard.sh --days 30 --activities 100
    ./dashboard.sh --chart-days 90 --future-days 21
    ./dashboard.sh --reports overview,daily,planned
    ./dashboard.sh --output /tmp/dashboard

Pages:

- `index.html` — a 7/42/182-day EWMA overview (weekly equivalents of runs,
  cross sessions, time, km, load, and Z3+4) plus a planned weekly average for
  the next 14 days; the main overview chart; the daily report; upcoming
  races in the next 180 days; and the planned workouts for the next 14 days.
  The EWMA overview, the daily report, and the planned section are the
  rendered `overview`, `daily`, and `planned` Markdown reports; the chart
  uses the last 182 days plus the next 14 by default.
- `activities.html` — the recent activity table (default 50) with workout
  methods and targets, linked to per-activity pages.
- `analysis.html` — the weekly volume, weekly time-by-pace-zone, and load/RPE
  charts, plus the pace-vs-heart-rate scatter, over the last two years
  (`--analysis-days`, default 731).
- `nsa.html` (NSA) — the subT EWMA report (7/42/182-day pace and heart-rate
  EWMAs per category), the subT/LT1 chart, and the `subT Report` over the
  last year.
- `compare.html` — volume and time EWMA lines per calendar year over a fixed
  Jan–Dec axis (`--compare-window`, default 182) plus the year and month
  comparison reports.
- `activity/<id>.html` — the session report body (metrics, workout methods and
  targets, zone times, description, interval table, and subT/LT1 work reps),
  exactly as `reports.sh session` renders it.
- `recovery.html` — the `recovery-report` (7/42/182-day moving averages and
  the last four nights), then HRV, resting HR, and sleep as interactive
  plotly panels over the last 186 days (`--recovery-days`) with 7-day
  averages, readiness bands, and a data-completeness note.
- `reports.html` — the Markdown reports selected with `--reports`, rendered
  as HTML with the same content as `reports.sh`.
- `health.html` (Data Health) — the open review queue (severity, category,
  detail, linked activity, reported date), the activities hidden by review,
  and missing-data counts.

`--reports` accepts a comma-separated list of Markdown reports:
`overview`, `recovery-report`, `daily`, `weekly`, `monthly`, `yearly`,
`report`, `planned`, `subt-report`, `compare-years`, and `compare-months`.
The same report code used by `reports.sh` is converted to HTML and embedded,
so changing a report also changes the dashboard. Select no reports to leave
the Reports page empty.

The main chart shows daily running **minutes** on a **0–90 minute** axis,
stacked as **hard (Z3+Z4)** at the base, **easy (Z1+Z2)** above it, and
**unzoned** on top. It draws 7/42/182-day EWMAs for **hard** and **total**
running, with the hard lines in reds at the base and the total lines in blues
above them, and the Garmin VO2max standing value as a black line on a second
axis on the right. It defaults to **182 days back and 14 days forward**;
`--chart-days` and `--future-days` change those. Planned workouts appear as
hatched bars on days without a recorded run, including today, so an
uncompleted planned session is visible; once a run is recorded, the actual bar
replaces the plan bar. Events without pace zones count as unzoned.

Charts are plotly figures built by one shared layer: the CLI writes PNGs via
kaleido, and the dashboard embeds the exact same figures as HTML, so the
overview can be zoomed and panned. The pages remain static snapshots: there
is no client-side data fetching and no server-side report process.
`plotly.min.js` is bundled into the generated site so it works offline.

Generation builds a temporary directory and atomically swaps it into place.
It refuses to replace a non-empty directory unless it is a previous
dashboard (marked with `.hobbyjogging-dashboard`).

The data-health banner counts activities with open review items, missing
load, missing pace zones, missing HR, and missing distance. The individual
queue is available through `DataSource.review_items(status="open",
category=...)`, which returns `ReviewItem` objects; rendering the categories
is a follow-up.

## Architecture

Data access and analysis are separated so the data source can be
replaced (e.g. Intervals.icu API → local database) without touching
analysis or chart code:

- `hobbyjogging_core/model.py` — source-agnostic types (`Activity`,
  `WellnessDay`, `Event`, `Interval`).
- `hobbyjogging_core/datasource.py` — the `DataSource` protocol.
- `cli.py` — shared command-line date-range and source parsing.
- `commands.py` — command registry and per-command help.
- `command_support.py` — shared review/fetch helpers for CLI handlers.
- `report_commands.py` — report command handlers.
- `chart_commands.py` — chart command handlers.
- `recent.py` — widening-lookback search shared by session and activity
  selection.
- `sessions.py` — session selection and the detailed session report.
- `debug.py` — raw stored payload dump (reads `source_records`).
- `sources/__init__.py` — the data-source factory.
- `sources/database.py` — canonical SQLite database adapter.
- `analysis/` — pure metrics over model objects (no API, no plotting),
  split into `common`, `averages`, `load`, `zones`, `subt`, `planned`, and
  `recovery` modules.
- `series.py` — pure daily-series, moving-average, and EWMA helpers.
- `summary.py` — period totals, quality-session lists, and recovery averages.
- `classify.py` — workout categorization (quality / non-quality /
  cross-training / unknown). It prefers the stored workout classification
  (`activity_workout_methods/targets`) and falls back to the heuristic for
  unclassified activities.
- `charts.py` — plotly chart builders shared by the CLI and dashboard.
- `format.py` — model-based report formatting helpers.
- `links.py` — Intervals and Garmin Connect URLs for canonical activities.
- `mdpretty.py` — dependency-free terminal Markdown renderer.
- `daily.py`, `period_report.py`, `subt_report.py` — the Markdown reports;
  one file per report, obtaining model objects through a `DataSource`.
- `activity_list.py` — the recent-activities table (selection, columns,
  rendering).

The `debug` command dumps the payloads already stored in the database.

To add a visualization: compute the metric in `analysis/` from model
objects, then plot it in `charts.py`.
