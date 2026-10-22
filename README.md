# Intervals Training Reports

Generate daily, weekly and monthly summaries from Intervals.icu.

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
- **debug** — Dump raw API data (activities, wellness, events,
  intervals).
- **chart** — Weekly running distance chart (matplotlib) for the
  last 90 days.
- **subt-chart** — subT work interval pace per category
  (short/medium/long) over the last 365 days, with per-session dots
  and rolling averages.
- **classify** — Print the workout category for each activity over
  the last N days (default 30).

## Setup

Install dependencies:

    uv sync

Create environment (`.env`):

    export INTERVALS_ATHLETE_ID=<your-athlete-id>
    export INTERVALS_API_KEY=<your-api-key>

Run:

    uv run --env-file .env python -m intervals_report daily
    uv run --env-file .env python -m intervals_report weekly
    uv run --env-file .env python -m intervals_report monthly
    uv run --env-file .env python -m intervals_report yearly
    uv run --env-file .env python -m intervals_report all
    uv run --env-file .env python -m intervals_report debug
    uv run --env-file .env python -m intervals_report chart [output.png]
    uv run --env-file .env python -m intervals_report subt-chart [output.png]
    uv run --env-file .env python -m intervals_report classify [days]

## Workout categories

```
quality
├── intervals
│   ├── subt-short   (avg rep <= 4:00)
│   ├── subt-medium  (avg rep 4:01-5:50)
│   ├── subt-long    (avg rep > 5:50)
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

- **quality**: RPE >= 4. If RPE is missing, infer from intensity
  (IF >= 0.85 or >= 25% of time in Z3+); if impossible -> `unknown`.
- **longrun**: activity longer than 90 min, even with RPE < 4 —
  unless race/subt/lt1/tempo content takes precedence.
- **recovery**: RPE = 1 and shorter than 40 min.
- **race-support**: race warm-ups and cool-downs, identified by name
  (`warm up` / `cool down`); overrides the RPE rule, since they are
  usually RPE 1–3.
- **cross-training**: any non-run activity (hiking, cycling, kayaking).
- Sub-type keywords come from the activity **name** only; descriptions
  often mention alternatives (e.g. "did 3x10@LT1 instead of subT").
  Execution (RPE/duration) decides *whether* the session was quality.
- **LT1 wins over subT** when both appear in the name.
- Rep length ignores work intervals shorter than 60 s (strides).

## Architecture

Data access and analysis are separated so the data source can be
replaced (e.g. Intervals.icu API → local database) without touching
analysis or chart code:

- `model.py` — source-agnostic types (`Activity`, `WellnessDay`,
  `Event`, `Interval`).
- `sources/base.py` — the `DataSource` protocol.
- `sources/intervals_api.py` — the only module that knows raw
  Intervals.icu field names.
- `analysis.py` — pure metrics over model objects (no API, no plotting).
- `classify.py` — workout categorization (quality / non-quality /
  cross-training / unknown).
- `charts.py` — matplotlib rendering of analysis output.
- `reports.py` — the Markdown reports.

To add a visualization: compute the metric in `analysis.py` from model
objects, then plot it in `charts.py`. To switch to a local database,
add another `DataSource` implementation; everything downstream stays
unchanged.
