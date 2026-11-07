# hobbyjogging-reports

This package is part of the `hobbyjogging` workspace. Run the commands below
from the repository root.

Generate daily, weekly and monthly summaries from the canonical hobbyjogging
database (default) or directly from Intervals.icu.

## Data sources

Reports depend on the `DataSource` protocol from `hobbyjogging-core`. Two
adapters are currently available:

- `IntervalsSource` — direct Intervals.icu API access.
- `DatabaseSource` — reads the canonical SQLite database.

The command-line wrapper uses `DatabaseSource` by default. Select the API
explicitly with `--source intervals` when you want to compare against
Intervals.icu. `debug` still dumps raw API payloads and ignores `--source`.

## What it does

Reads activity, wellness and planned-session data through a `DataSource`
(canonical database by default, or the
[Intervals.icu](https://intervals.icu) API) and produces Markdown training
reports:

- **daily** — Yesterday's activities, today's planned workout,
  and recovery (HRV / RHR / sleep) from the last nights.
- **weekly** — Aggregated running and cross-training stats,
  quality sessions and recovery over the last 7 days.
- **monthly** — Same summary over the last 30 days.
- **yearly** — Same summary over the last 365 days.
- **all** — Daily + weekly + monthly + yearly in one report.
- **report** — A summary report for an arbitrary inclusive date range
  (`--days`, `--from`, `--to`).
- **subt-report** — All subT and LT1 sessions in a range, grouped by
  short/medium/long/LT1. Shows work-block and summary tables.
- **planned** — Upcoming planned workouts as a compact key-facts table
  (date, weekday, workout, sport, distance, time, load); next 28 days
  by default.
- **session [date|id|last]** — Detailed report for one session, chosen by
  date, activity id, or `last` (the default): category, totals, zones,
  description, the full interval table, and subT/LT1 work reps.
- **debug** — Dump raw API data (activities, wellness, events,
  intervals).
- **volume** — Weekly running volume chart with 182/42/7-day
  distance averages and the planned weekly distance; last 90 days by
  default.
- **load** — Daily training load with 182-day base, 42-day fitness,
  and 7-day fatigue exponentially weighted averages, plus planned load.
- **time** — Weekly running time stacked by HR zone, with
  182/42/7-day time averages, a per-zone EWMA panel, and planned weekly
  time including planned HR zone distributions.
- **recovery** — HRV, resting HR, and sleep trends with a rolling
  calendar-day average and planned-workout markers.
- **subt** — subT and LT1 work intervals over the last 365 days by
  default, with pace and average HR as two stacked panels sharing a
  date axis. Dots are color-coded by rep length (short/medium/long)
  or LT1; pace ranges show fastest–slowest, HR ranges show
  average–max, and both metrics have rolling averages.
- **classify** — Print the workout category for each activity over
  the last N days (default 30).
- **activities** — Table of recent activities (default: last 20), with
  selectable columns.

## Setup

Install dependencies:

    uv sync

Create environment (`.env`):

    export HOBBYJOGGING_DB=~/projects/laufen_private/data/db/hobbyjogging.db
    export INTERVALS_ATHLETE_ID=<your-athlete-id>
    export INTERVALS_API_KEY=<your-api-key>

The Intervals.icu variables are only needed for `--source intervals` and
`debug`.

Run:

    uv run --env-file .env python -m hobbyjogging_report daily
    uv run --env-file .env python -m hobbyjogging_report weekly
    uv run --env-file .env python -m hobbyjogging_report monthly
    uv run --env-file .env python -m hobbyjogging_report yearly
    uv run --env-file .env python -m hobbyjogging_report all
    uv run --env-file .env python -m hobbyjogging_report report --days 90
    uv run --env-file .env python -m hobbyjogging_report subt-report --days 90
    uv run --env-file .env python -m hobbyjogging_report planned
    uv run --env-file .env python -m hobbyjogging_report activities --limit 20
    uv run --env-file .env python -m hobbyjogging_report session
    uv run --env-file .env python -m hobbyjogging_report session 2026-02-22
    uv run --env-file .env python -m hobbyjogging_report session 7a2bf884-2b25-585f-8430-530749f80afa
    uv run --env-file .env python -m hobbyjogging_report debug
    uv run --env-file .env python -m hobbyjogging_report volume [output.png]
    uv run --env-file .env python -m hobbyjogging_report load [output.png]
    uv run --env-file .env python -m hobbyjogging_report time [output.png]
    uv run --env-file .env python -m hobbyjogging_report recovery [output.png]
    uv run --env-file .env python -m hobbyjogging_report subt [output.png]
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
    ./reports.sh monthly
    ./reports.sh report --days 90
    ./reports.sh report --from 2026-01-01 --to 2026-03-31
    ./reports.sh subt-report --days 90
    ./reports.sh planned
    ./reports.sh planned --days 56
    ./reports.sh session 2026-10-22
    ./reports.sh session 7a2bf884-2b25-585f-8430-530749f80afa
    ./reports.sh session last
    ./reports.sh weekly --source intervals

The clipboard receives the original Markdown before terminal
formatting, so pasting gives clean Markdown. Use `NO_COPY=1` to skip
the clipboard, `NO_COLOR=1` to disable ANSI colours, or `NO_PRETTY=1`
to print raw Markdown.

When stdout is a terminal, the direct CLI also displays reports with
the same formatting. Redirected or piped output remains raw Markdown.

### Quick charts

`charts.sh` wraps the chart commands and prints the generated file path:

    ./charts.sh                          # weekly volume, last 90 days
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
    ./charts.sh subt --source intervals

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
stacked by HR zone. It uses running activities only and defaults to four
zones (`Z1`–`Z4`).

The top panel overlays the 182/42/7-day averages of total running time,
scaled to weekly hours. The lower panel stacks the zone EWMAs for the
selected `--zone-window` (`base`, `fitness`, or `fatigue`; default
`fitness` / 42 days), also in weekly hours. Its boundary lines are
cumulative: `Z4`, `Z3+Z4`, `Z2+Z3+Z4`, then all zones.

Planned running workouts that carry an HR zone distribution are drawn as
hatched stacked bars over the actual week. Zones beyond `--zones` fold
into the last displayed zone, and `SS` buckets are ignored. Weeks whose
planned workouts have no HR zones keep the dashed total-time outline.
The lower EWMA panel remains actual-only.

    ./charts.sh time
    ./charts.sh time --days 90
    ./charts.sh time --zones 4 --zone-window base
    ./charts.sh time --base-days 182 --fitness-days 42 --fatigue-days 7

Time outside recorded HR zones is shown as an `Unzoned` segment, so each
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

### Planned workouts

The volume, load, time, and recovery charts include planned workouts.
Unless `--to` is given, they extend the right edge of the chart by
`--planned-days N` (default 28); `--planned-days 0` disables the
extension.

- **volume** — planned running distance per Monday–Sunday week, as a
  dashed target line.
- **time** — planned running time per week, as an outlined bar over the
  actual zone stack. Planned HR zone distributions, when available, are
  drawn as hatched stacked bars; other planned events keep the
  total-time outline.
- **load** — planned load per day for all sports, as outlined daily
  bars.
- **recovery** — one tick per planned workout along the bottom of the
  sleep panel.

Events without a sport type (illness or travel notes) are ignored.
The volume chart also skips planned events without a distance.

The 182/42/7-day EWMA lines continue through the planned days as dashed
segments, using planned daily distance, time, or load and treating
unplanned days as rest. The time chart's weekly zone stack includes
planned HR zone distributions; its lower EWMA panel and the recovery
averages stay actual-only.

### Data source selection

All report and chart commands accept:

    --source database     read the canonical SQLite database (default)
    --source intervals    read directly from the Intervals.icu API

Examples:

    ./reports.sh report --days 90 --source database
    ./reports.sh report --days 90 --source intervals
    ./reports.sh --source intervals weekly
    ./charts.sh subt --days 365 --source intervals

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
load, RPE, feel. `--columns` replaces them (in the order given); `--add`
appends. Available columns: id, date, started (UTC), sport, name, duration,
elapsed, distance, pace, avg_hr, load, rpe, feel, intensity, category.
The category is only computed when requested, and uses intervals for
subT/LT1-named sessions.

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

## Static dashboard (planned)

The next renderer is a static HTML dashboard generated from the same analysis
layer as the Markdown reports: weekly overview (load, volume/time, zones, plan
vs actual), activity list and detail, and a data-health banner (open review
items, exclusions, missing data). It is generated on the homelab, written
atomically, and served read-only; Markdown reports remain the terminal view.

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
- `debug.py` — raw Intervals.icu payload dump.
- `sources/__init__.py` — source selection.
- `sources/database.py` — canonical SQLite database adapter.
- `sources/intervals_api.py` — the only module that knows raw
  Intervals.icu field names.
- `analysis.py` — pure metrics over model objects (no API, no plotting).
- `series.py` — pure daily-series, moving-average, and EWMA helpers.
- `summary.py` — period totals, quality-session lists, and recovery averages.
- `classify.py` — workout categorization (quality / non-quality /
  cross-training / unknown).
- `charts.py` — matplotlib rendering of analysis output.
- `format.py` — model-based report formatting helpers.
- `mdpretty.py` — dependency-free terminal Markdown renderer.
- `daily.py`, `period_report.py`, `subt_report.py` — the Markdown reports;
  one file per report, obtaining model objects through a `DataSource`.
- `activity_list.py` — the recent-activities table (selection, columns,
  rendering).

Only `sources/intervals_api.py` knows Intervals.icu field names; the
`debug` command is the one place that still dumps raw payloads.

To add a visualization: compute the metric in `analysis.py` from model
objects, then plot it in `charts.py`. To add another data source, implement
the `DataSource` protocol and register it in `sources/__init__.py`; everything
downstream stays unchanged.
