"""Training-load and running-distance series with EWMA trends."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from hobbyjogging_core.model import Activity, Event

from .averages import (
    DEFAULT_AVERAGE_WINDOWS,
    _average_rows,
    _extend_series,
    average_warmup_days,
)
from .common import RUN_TYPES, week_start
from ..model import AverageWindows, DistancePoint, LoadPoint
from .planned import daily_planned_distance, daily_planned_load
from ..series import daily_sums


def weekly_run_distance(activities: list[Activity]) -> list[tuple[date, float]]:
    """Run distance (km) per week, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for a in activities:
        if a.type in RUN_TYPES:
            totals[week_start(a.date)] += a.distance_m

    return [(week, totals[week] / 1000) for week in sorted(totals)]


def daily_training_load(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Sum training load per day, filling rest days with zero."""
    by_day: dict[date, float] = {}

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        by_day[activity.date] = (
            by_day.get(activity.date, 0.0)
            + (activity.training_load or 0.0)
        )

    return daily_sums(by_day, start, end)


def daily_run_distance(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Sum running distance (km) per day, filling rest days with zero."""
    by_day: dict[date, float] = {}

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        if activity.type not in RUN_TYPES:
            continue

        by_day[activity.date] = (
            by_day.get(activity.date, 0.0)
            + activity.distance_m / 1000
        )

    return daily_sums(by_day, start, end)


def load_metrics(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    windows: AverageWindows | None = None,
    warmup_days: int | None = None,
    events: list[Event] | None = None,
    projected_end: date | None = None,
    projection_start: date | None = None,
) -> list[LoadPoint]:
    """Return daily load with base, fitness, and fatigue EWMAs.

    ``activities`` must include the warm-up range before ``start`` so the
    long average does not begin at zero mid-report. When ``events`` and
    ``projected_end`` are given, the averages continue through planned
    load; those points are marked ``projected``.
    """
    windows = windows or DEFAULT_AVERAGE_WINDOWS

    if warmup_days is None:
        warmup_days = average_warmup_days(windows)

    projection_start = projection_start or end
    projected = (
        events is not None
        and projected_end is not None
        and projected_end > projection_start
    )
    series_end = projection_start if projected else end

    warm_start = start - timedelta(days=warmup_days)
    series = daily_training_load(activities, warm_start, series_end)

    if projected:
        series = _extend_series(
            series,
            daily_planned_load(
                events,
                series_end + timedelta(days=1),
                projected_end,
            ),
            projected_end,
        )
    else:
        projection_start = None

    rows = _average_rows(
        series,
        start,
        windows,
        projected_start=projection_start,
    )

    return [
        LoadPoint(
            date=day,
            load=value,
            base=base,
            fitness=fitness,
            fatigue=fatigue,
            projected=projected_value,
        )
        for day, value, base, fitness, fatigue, projected_value in rows
    ]


def distance_averages(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    windows: AverageWindows | None = None,
    warmup_days: int | None = None,
    events: list[Event] | None = None,
    projected_end: date | None = None,
    projection_start: date | None = None,
) -> list[DistancePoint]:
    """Return daily running distance with its three EWMAs.

    ``activities`` must include the warm-up range before ``start``. When
    ``events`` and ``projected_end`` are given, the averages continue
    through planned distance; those points are marked ``projected``.
    """
    windows = windows or DEFAULT_AVERAGE_WINDOWS

    if warmup_days is None:
        warmup_days = average_warmup_days(windows)

    projection_start = projection_start or end
    projected = (
        events is not None
        and projected_end is not None
        and projected_end > projection_start
    )
    series_end = projection_start if projected else end

    warm_start = start - timedelta(days=warmup_days)
    series = daily_run_distance(activities, warm_start, series_end)

    if projected:
        series = _extend_series(
            series,
            daily_planned_distance(
                events,
                series_end + timedelta(days=1),
                projected_end,
            ),
            projected_end,
        )
    else:
        projection_start = None

    rows = _average_rows(
        series,
        start,
        windows,
        projected_start=projection_start,
    )

    return [
        DistancePoint(
            date=day,
            distance_km=value,
            base=base,
            fitness=fitness,
            fatigue=fatigue,
            projected=projected_value,
        )
        for day, value, base, fitness, fatigue, projected_value in rows
    ]
