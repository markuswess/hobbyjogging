"""Per-run pace vs heart rate for aerobic-efficiency analysis."""

from __future__ import annotations

from datetime import date

from hobbyjogging_core.model import Activity

from .common import RUN_TYPES, pace_s_per_km
from ..model import PaceHrPoint


def pace_hr_points(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[PaceHrPoint]:
    """One point per run with distance, time, and average heart rate."""
    points = []

    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue
        if not (start <= activity.date <= end):
            continue
        if not activity.avg_hr or not activity.distance_m:
            continue

        pace = pace_s_per_km(
            activity.duration_s or 0,
            activity.distance_m,
        )

        if pace is None:
            continue

        points.append(
            PaceHrPoint(
                date=activity.date,
                pace_s_per_km=pace,
                avg_hr=activity.avg_hr,
                name=activity.name or "",
            )
        )

    return sorted(points, key=lambda point: point.date)
