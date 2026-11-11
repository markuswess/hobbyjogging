"""Session-RPE series with base, fitness, and fatigue EWMAs."""

from __future__ import annotations

from datetime import date, timedelta

from hobbyjogging_core.model import Activity

from .averages import DEFAULT_AVERAGE_WINDOWS, average_warmup_days
from ..model import AverageWindows, RpePoint
from ..series import alpha_from_time_constant, date_range, ewma


def daily_session_rpe(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Mean RPE per day for rated sessions, oldest first.

    Days without a rated session are skipped rather than treated as zero:
    rest days describe no effort at all, not an easy session.
    """
    by_day: dict[date, list[float]] = {}

    for activity in activities:
        if activity.rpe is None or not (start <= activity.date <= end):
            continue

        by_day.setdefault(activity.date, []).append(activity.rpe)

    return [
        (day, sum(values) / len(values))
        for day, values in sorted(by_day.items())
    ]


def rpe_metrics(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    windows: AverageWindows | None = None,
    warmup_days: int | None = None,
) -> list[RpePoint]:
    """Standing session RPE with base, fitness, and fatigue EWMAs.

    ``activities`` must include the warm-up range before ``start``. Between
    rated sessions the standing value carries forward, matching how the
    VO2max series treats days without a measurement; the EWMAs therefore
    describe recent perceived effort, not daily training volume.
    """
    windows = windows or DEFAULT_AVERAGE_WINDOWS

    if warmup_days is None:
        warmup_days = average_warmup_days(windows)

    if start > end:
        return []

    warm_start = start - timedelta(days=warmup_days)
    measured = dict(daily_session_rpe(activities, warm_start, end))

    if not measured:
        return []

    first = min(measured)
    series_days = [
        day for day in date_range(warm_start, end) if day >= first
    ]
    carried = None
    values: list[float] = []

    for day in series_days:
        if day in measured:
            carried = measured[day]

        values.append(carried)

    base = ewma(
        values,
        alpha_from_time_constant(windows.base),
        initial=values[0],
    )
    fitness = ewma(
        values,
        alpha_from_time_constant(windows.fitness),
        initial=values[0],
    )
    fatigue = ewma(
        values,
        alpha_from_time_constant(windows.fatigue),
        initial=values[0],
    )

    return [
        RpePoint(
            date=day,
            rpe=measured.get(day),
            base=base[index],
            fitness=fitness[index],
            fatigue=fatigue[index],
        )
        for index, day in enumerate(series_days)
        if day >= start
    ]
