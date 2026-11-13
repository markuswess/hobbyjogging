"""Garmin VO2max trend with short and long EWMAs."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from hobbyjogging_core.model import Activity

from ..model import Vo2maxMeasurement, Vo2maxPoint
from ..series import alpha_from_time_constant, date_range, ewma
from .common import RUN_TYPES

VO2MAX_SHORT_DAYS = 7
VO2MAX_LONG_DAYS = 42
VO2MAX_WARMUP_DAYS = 5 * VO2MAX_LONG_DAYS


def vo2max_measurements(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[Vo2maxMeasurement]:
    """Raw Garmin VO2max readings, one per activity, without averaging."""
    return sorted(
        (
            Vo2maxMeasurement(
                date=activity.date,
                value=activity.vo2max_garmin,
            )
            for activity in activities
            if activity.type in RUN_TYPES
            and activity.vo2max_garmin is not None
            and activity.vo2max_garmin > 0
            and start <= activity.date <= end
        ),
        key=lambda measurement: (measurement.date, measurement.value),
    )


def vo2max_points(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[Vo2maxPoint]:
    """Return daily running Garmin VO2max with its two EWMAs.

    Values are averaged per day. Only running activities with a positive
    Garmin VO2max are used; Runalyze estimates and other sports are ignored.
    Days without a measurement carry the previous value forward so the
    averages describe the metric's standing value, not a zero-filled gap.
    """
    if start > end:
        return []

    by_day: dict[date, list[float]] = defaultdict(list)

    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue

        value = activity.vo2max_garmin

        if value is None or value <= 0 or activity.date > end:
            continue

        by_day[activity.date].append(value)

    if not by_day:
        return []

    daily = {
        day: sum(values) / len(values)
        for day, values in by_day.items()
    }
    first = min(daily)
    days = date_range(first, end)
    series = []
    carried = None

    for day in days:
        if day in daily:
            carried = daily[day]

        series.append(carried)

    short = ewma(
        series,
        alpha_from_time_constant(VO2MAX_SHORT_DAYS),
        initial=series[0],
    )
    long = ewma(
        series,
        alpha_from_time_constant(VO2MAX_LONG_DAYS),
        initial=series[0],
    )

    return [
        Vo2maxPoint(
            date=day,
            value=daily.get(day),
            avg_7=short[index],
            avg_42=long[index],
        )
        for index, day in enumerate(days)
        if day >= start
    ]
