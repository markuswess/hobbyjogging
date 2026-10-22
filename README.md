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

## Setup

Install dependencies:

    uv sync

Create environment (`.env`):

    export INTERVALS_ATHLETE_ID=<your-athlete-id>
    export INTERVALS_API_KEY=<your-api-key>

Run:

    uv run --env-file .env intervals_report.py daily
    uv run --env-file .env intervals_report.py weekly
    uv run --env-file .env intervals_report.py monthly
    uv run --env-file .env intervals_report.py yearly
    uv run --env-file .env intervals_report.py all
    uv run --env-file .env intervals_report.py debug
