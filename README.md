# Intervals Training Reports

Generate daily, weekly and monthly summaries from Intervals.icu.

## Setup

Install dependencies:

    uv sync

Create environment:

    cp .env.example .env

Run:

    uv run --env-file .env intervals_report.py daily
    uv run --env-file .env intervals_report.py weekly
    uv run --env-file .env intervals_report.py monthly
