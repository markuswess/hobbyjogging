# Intervals Training Reports

This package is part of the `hobbyjogging` workspace. Run the commands below
from the repository root.

Generate daily, weekly and monthly summaries from Intervals.icu or the
canonical hobbyjogging database.

## Data sources

Reports depend on the `DataSource` protocol from `hobbyjogging-core`. Two
adapters are currently available:

- `IntervalsSource` — direct Intervals.icu API access.
- `DatabaseSource` — reads the canonical SQLite database.

The command-line wrapper uses `DatabaseSource` by default. Select the API
explicitly with `--source intervals` when you want to compare against
Intervals.icu. `debug` still dumps raw API payloads and ignores `--source`.

## What it does

Pulls activity, wellness and planned-session data from the
[Intervals.icu](https://intervals.icu) API and produces Markdown
training reports:

- **daily** — Yesterday's activities, today's planned workout,
  and recovery (HRV / RHR / sleep) from the last nights.
- **weekly** — Aggregated running and cross-training stats,
  quality sessions and recovery over the last 7 days.
- **monthly** — Same summary over the last 30 days.
- **yearly** — Same summary over the last 365 days.
- **all** — Daily + weekly + monthly + yearly in one report.
- **report** — A summary report for an arbitrary inclusive date range
  (`--days`, `--from`, `--to`).
- **session [date|id|last]** — Detailed report for one session, chosen by
  date, activity id, or `last` (the default): category, totals, zones,
  description, the full interval table, and subT/LT1 work reps.
- **debug** — Dump raw API data (activities, wellness, events,
  intervals).
- **chart** — Weekly running distance chart (matplotlib); last 90
  days by default.
- **subt-chart** — subT and LT1 work interval pace over the last 365
  days by default, with per-session dots color-coded by rep length
  (short/medium/long) or LT1, vertical bars showing the fastest and
  slowest work interval, plus rolling averages.
- **subt-hr-chart** — the same work-interval chart using average
  heart rate, with vertical bars showing max HR.
- **classify** — Print the workout category for each activity over
  the last N days (default 30).

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
    uv run --env-file .env python -m hobbyjogging_report session
    uv run --env-file .env python -m hobbyjogging_report session 2026-02-22
    uv run --env-file .env python -m hobbyjogging_report session 7a2bf884-2b25-585f-8430-530749f80afa
    uv run --env-file .env python -m hobbyjogging_report debug
    uv run --env-file .env python -m hobbyjogging_report chart [output.png]
    uv run --env-file .env python -m hobbyjogging_report subt-chart [output.png]
    uv run --env-file .env python -m hobbyjogging_report subt-hr-chart [output.png]
    uv run --env-file .env python -m hobbyjogging_report classify [days]

### Quick reports

`reports.sh` wraps the long `uv run` command, copies the generated
Markdown to the clipboard with `wl-copy`, and renders headings, lists
and tables for the terminal:

    ./reports.sh                 # daily
    ./reports.sh daily
    ./reports.sh monthly
    ./reports.sh report --days 90
    ./reports.sh report --from 2026-01-01 --to 2026-03-31
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

### Data source selection

All report commands accept:

    --source database     read the canonical SQLite database (default)
    --source intervals    read directly from the Intervals.icu API

Examples:

    ./reports.sh report --days 90 --source database
    ./reports.sh report --days 90 --source intervals
    ./reports.sh --source intervals weekly

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

## Date ranges

`report`, `chart`, `subt-chart`, `subt-hr-chart` and `classify` accept:

    --days N              look back N days from today
    --from YYYY-MM-DD     start date (inclusive)
    --to YYYY-MM-DD       end date (inclusive)

The chart commands also accept:

    --output FILE         chart output path

Examples:

    uv run --env-file .env python -m hobbyjogging_report report --days 90
    uv run --env-file .env python -m hobbyjogging_report report --from 2026-01-01 --to 2026-03-31
    uv run --env-file .env python -m hobbyjogging_report classify --days 90
    uv run --env-file .env python -m hobbyjogging_report classify --from 2026-01-01 --to 2026-03-31
    uv run --env-file .env python -m hobbyjogging_report subt-chart --from 2026-02-01
    uv run --env-file .env python -m hobbyjogging_report subt-hr-chart --to 2026-06-30 --days 120 --output hr.png

Rules:

- `--from` and `--to` together select exactly that inclusive range.
- `--from` alone runs from that date through today.
- `--to` alone counts back `--days` (or the command default) from that date.
- With neither, count back `--days` (or the command default) from today.
- The old forms still work: `classify 30` and `subt-chart out.png`.
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

## Architecture

Data access and analysis are separated so the data source can be
replaced (e.g. Intervals.icu API → local database) without touching
analysis or chart code:

- `hobbyjogging_core/model.py` — source-agnostic types (`Activity`,
  `WellnessDay`, `Event`, `Interval`).
- `hobbyjogging_core/datasource.py` — the `DataSource` protocol.
- `cli.py` — shared command-line date-range and source parsing.
- `sources/__init__.py` — source selection.
- `sources/database.py` — canonical SQLite database adapter.
- `sources/intervals_api.py` — the only module that knows raw
  Intervals.icu field names.
- `analysis.py` — pure metrics over model objects (no API, no plotting).
- `classify.py` — workout categorization (quality / non-quality /
  cross-training / unknown).
- `charts.py` — matplotlib rendering of analysis output.
- `format.py` — model-based report formatting helpers.
- `mdpretty.py` — dependency-free terminal Markdown renderer.
- `reports.py` — the Markdown reports; they obtain model objects
  through a `DataSource`.

Only `sources/intervals_api.py` knows Intervals.icu field names; the
`debug` command is the one place that still dumps raw payloads.

To add a visualization: compute the metric in `analysis.py` from model
objects, then plot it in `charts.py`. To add another data source, implement
the `DataSource` protocol and register it in `sources/__init__.py`; everything
downstream stays unchanged.
