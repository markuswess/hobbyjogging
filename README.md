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
- `charts.py` — matplotlib rendering of analysis output.
- `reports.py` — the Markdown reports.

To add a visualization: compute the metric in `analysis.py` from model
objects, then plot it in `charts.py`. To switch to a local database,
add another `DataSource` implementation; everything downstream stays
unchanged.
