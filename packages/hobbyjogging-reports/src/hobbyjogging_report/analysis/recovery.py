"""Wellness recovery trends."""

from __future__ import annotations

from datetime import date

from hobbyjogging_core.model import WellnessDay

from ..model import RecoveryPoint
from ..series import rolling_mean_by_date


def recovery_trends(
    wellness: list[WellnessDay],
    start: date,
    end: date,
    *,
    window_days: int = 7,
) -> list[RecoveryPoint]:
    """Return wellness points in range with rolling calendar-day averages."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")

    ordered = sorted(wellness, key=lambda day: day.date)

    if not ordered:
        return []

    hrv_avg = rolling_mean_by_date(
        [(day.date, day.hrv) for day in ordered],
        window_days,
    )
    rhr_avg = rolling_mean_by_date(
        [(day.date, day.resting_hr) for day in ordered],
        window_days,
    )
    sleep_avg = rolling_mean_by_date(
        [(day.date, day.sleep_s) for day in ordered],
        window_days,
    )

    points = []

    for index, day in enumerate(ordered):
        if not (start <= day.date <= end):
            continue

        points.append(
            RecoveryPoint(
                date=day.date,
                hrv=day.hrv,
                resting_hr=day.resting_hr,
                sleep_s=day.sleep_s,
                hrv_avg=hrv_avg[index],
                resting_hr_avg=rhr_avg[index],
                sleep_avg=sleep_avg[index],
            )
        )

    return points
