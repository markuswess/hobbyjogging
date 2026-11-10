"""Training overview EWMA report and its analysis helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import Activity, Event

from .analysis import (
    RUN_TYPES,
    average_warmup_days,
    daily_run_distance,
    daily_run_time,
    daily_training_load,
    daily_zone_time,
    event_zone_time,
)
from .format import fmt_time
from .model import AverageWindows
from .review import exclude_review, review_note
from .series import alpha_from_time_constant, date_range, ewma


@dataclass(frozen=True)
class EwmaRow:
    key: str
    label: str
    kind: str
    values: dict[int, float]


@dataclass(frozen=True)
class PlannedOverview:
    runs: int = 0
    cross: int = 0
    run_time_s: float = 0
    run_distance_m: float = 0
    load: float = 0
    z3_z4_s: float = 0


def overview_ewma(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    windows: AverageWindows | None = None,
) -> list[EwmaRow]:
    """Weekly-equivalent EWMAs of daily training metrics ending at ``end``."""
    if start > end:
        return []

    windows = windows or AverageWindows()
    days = date_range(start, end)
    runs_by_day: dict[date, float] = defaultdict(float)
    cross_by_day: dict[date, float] = defaultdict(float)

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        if activity.type in RUN_TYPES:
            runs_by_day[activity.date] += 1
        else:
            cross_by_day[activity.date] += 1

    runs = [runs_by_day.get(day, 0.0) for day in days]
    cross = [cross_by_day.get(day, 0.0) for day in days]
    run_time = [value for _, value in daily_run_time(activities, start, end)]
    run_distance = [
        value for _, value in daily_run_distance(activities, start, end)
    ]
    load = [value for _, value in daily_training_load(activities, start, end)]
    z3_z4 = [
        sum(zones[2:4])
        for _, zones in daily_zone_time(
            activities,
            start,
            end,
            zone_count=4,
        )
    ]
    taus = (windows.fatigue, windows.fitness, windows.base)

    def weekly(series: list[float]) -> dict[int, float]:
        return {
            tau: ewma(
                series,
                alpha_from_time_constant(tau),
            )[-1] * 7
            for tau in taus
        }

    return [
        EwmaRow("runs", "Runs / week", "count", weekly(runs)),
        EwmaRow("cross", "Cross / week", "count", weekly(cross)),
        EwmaRow("run_time_s", "Run time / week", "time", weekly(run_time)),
        EwmaRow(
            "run_distance_m",
            "Run km / week",
            "distance",
            weekly(run_distance),
        ),
        EwmaRow("load", "Load / week", "load", weekly(load)),
        EwmaRow("z3_z4_s", "Z3+4 / week", "time", weekly(z3_z4)),
    ]


def planned_overview(
    events: list[Event],
    start: date,
    end: date,
) -> PlannedOverview:
    """Planned totals for the next overview period."""
    selected = [
        event
        for event in events
        if event.type and start <= event.date <= end
    ]
    runs = [event for event in selected if event.type in RUN_TYPES]
    cross = [event for event in selected if event.type not in RUN_TYPES]

    return PlannedOverview(
        runs=len(runs),
        cross=len(cross),
        run_time_s=sum(event.duration_s or 0 for event in runs),
        run_distance_m=sum(event.distance_m or 0 for event in runs),
        load=sum(event.training_load or 0 for event in selected),
        z3_z4_s=sum(
            event_zone_time(event, (3, 4)) or 0
            for event in runs
        ),
    )


def _duration(seconds: float) -> str:
    return fmt_time(seconds) if seconds else "0min"


def _ewma_cell(row: EwmaRow, tau: int) -> str:
    value = row.values[tau]

    if row.kind == "count":
        return f"{value:.1f}"
    if row.kind == "time":
        return _duration(value)
    if row.kind == "distance":
        return f"{value:,.1f}"
    if row.kind == "load":
        return f"{value:.0f}"

    return f"{value:g}"


def _planned_cell(
    row: EwmaRow,
    planned: PlannedOverview,
    weeks: float,
) -> str:
    if weeks <= 0:
        return "-"

    value = getattr(planned, row.key) / weeks

    if row.kind == "count":
        return f"{value:.1f}"
    if row.kind == "time":
        return _duration(value)
    if row.kind == "distance":
        return f"{value / 1000:,.1f}"
    if row.kind == "load":
        return f"{value:.0f}"

    return f"{value:g}"


def overview_report(
    source: DataSource,
    *,
    future_days: int = 14,
    today: date | None = None,
    include_review: bool = False,
) -> str:
    """Render the 7/42/182-day EWMA training overview as Markdown."""
    if future_days < 0:
        raise ValueError("future_days must be zero or greater")

    today = today or date.today()
    windows = AverageWindows()
    warmup_days = average_warmup_days(windows)
    warm_start = today - timedelta(days=warmup_days)
    activities, excluded = exclude_review(
        source.activities(warm_start, today),
        include_review=include_review,
    )
    rows = overview_ewma(
        activities,
        warm_start,
        today,
        windows=windows,
    )
    planned_start = today + timedelta(days=1)
    planned_end = today + timedelta(days=future_days)
    events = [
        event
        for event in source.events(planned_start, planned_end)
        if event.type
    ]
    planned = planned_overview(events, planned_start, planned_end)
    weeks = future_days / 7 if future_days else 0
    planned_header = (
        f"Next {future_days} days (avg/week)"
        if future_days
        else "Next period (avg/week)"
    )
    planned_note = (
        f"the planned weekly average for the next {future_days} days"
        if future_days
        else "no future planning range"
    )

    lines = [
        "# Training Overview — EWMA",
        f"EWMA ending {today}",
    ]
    note = review_note(excluded)
    if note:
        lines.append(f"\n> {note}")

    lines.extend([
        "",
        f"| Metric | 7-day EWMA | 42-day EWMA | 182-day EWMA | "
        f"{planned_header} |",
        "|---|---:|---:|---:|---:|",
    ])

    for row in rows:
        lines.append(
            f"| {row.label} | {_ewma_cell(row, 7)} | "
            f"{_ewma_cell(row, 42)} | {_ewma_cell(row, 182)} | "
            f"{_planned_cell(row, planned, weeks)} |"
        )

    lines.extend([
        "",
        "Weekly equivalents of the daily EWMA ending today; the last column "
        f"is {planned_note}.",
    ])

    return "\n".join(lines)
