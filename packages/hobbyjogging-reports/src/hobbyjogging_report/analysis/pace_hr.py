"""Per-run pace vs heart rate for aerobic-efficiency analysis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from statistics import median

from hobbyjogging_core.model import Activity

from .common import RUN_TYPES, pace_s_per_km
from .efficiency import excess_beats
from ..model import PaceHrPoint


def pace_hr_points(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    resting_hr_baseline: Callable[[date], float | None] | None = None,
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

        resting_hr = (
            resting_hr_baseline(activity.date)
            if resting_hr_baseline is not None
            else None
        )
        beats = excess_beats(
            activity.duration_s,
            activity.avg_hr,
            resting_hr,
        )

        points.append(
            PaceHrPoint(
                date=activity.date,
                pace_s_per_km=pace,
                avg_hr=activity.avg_hr,
                name=activity.name or "",
                resting_hr=resting_hr,
                distance_m=activity.distance_m or 0,
                excess_beats=beats or 0,
            )
        )

    return sorted(points, key=lambda point: point.date)


@dataclass(frozen=True)
class PaceHrTrend:
    """Least-squares heart rate against speed for one half of the data."""

    label: str
    points: int
    speed_low: float
    speed_high: float
    slope: float
    intercept: float
    correlation: float

    def at(self, speed: float) -> float:
        return self.intercept + self.slope * speed


def pace_hr_trends(points: list[PaceHrPoint]) -> list[PaceHrTrend]:
    """Fit HR against speed for the older and newer half of the points."""
    ordered = sorted(points, key=lambda point: point.date)

    if len(ordered) < 4:
        return []

    split = len(ordered) // 2
    halves = (("first half", ordered[:split]), ("second half", ordered[split:]))
    trends = []

    for label, chunk in halves:
        xs = [point.speed_m_s for point in chunk]
        ys = [point.avg_hr for point in chunk]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        variance = sum((value - mean_x) ** 2 for value in xs)

        if variance == 0:
            continue

        covariance = sum(
            (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)
        )
        slope = covariance / variance
        intercept = mean_y - slope * mean_x
        var_y = sum((value - mean_y) ** 2 for value in ys)
        correlation = (
            covariance / (variance ** 0.5 * var_y ** 0.5)
            if var_y
            else 0.0
        )
        trends.append(
            PaceHrTrend(
                label=label,
                points=len(chunk),
                speed_low=min(xs),
                speed_high=max(xs),
                slope=slope,
                intercept=intercept,
                correlation=correlation,
            )
        )

    return trends


@dataclass(frozen=True)
class PaceHrEfficiencyLine:
    """One half's efficiency model ``HR = RHR + v * 60 / E``."""

    label: str
    points: int
    speed_low: float
    speed_high: float
    resting_hr: float
    efficiency: float
    slope: float
    intercept: float

    def at(self, speed: float) -> float:
        return self.intercept + self.slope * speed


def pace_hr_efficiency_lines(
    points: list[PaceHrPoint],
) -> list[PaceHrEfficiencyLine]:
    """Draw one efficiency line per half, beside the free regressions.

    ``E`` is the weighted aggregate ``sum(distance) / sum(excess beats)``,
    so it matches the efficiency reported elsewhere. The intercept is the
    half's median resting-HR baseline. Points without a baseline are left
    out of the fit but stay in the scatter.
    """
    ordered = sorted(points, key=lambda point: point.date)

    if len(ordered) < 4:
        return []

    split = len(ordered) // 2
    halves = (
        ("first half", ordered[:split]),
        ("second half", ordered[split:]),
    )
    lines = []

    for label, chunk in halves:
        usable = [
            point
            for point in chunk
            if point.distance_m > 0
            and point.excess_beats > 0
            and point.resting_hr is not None
        ]

        if len(usable) < 2:
            continue

        distance = sum(point.distance_m for point in usable)
        beats = sum(point.excess_beats for point in usable)

        if distance <= 0 or beats <= 0:
            continue

        efficiency = distance / beats
        resting_hr = median(
            point.resting_hr for point in usable
        )
        speeds = [point.speed_m_s for point in usable]

        lines.append(
            PaceHrEfficiencyLine(
                label=label,
                points=len(usable),
                speed_low=min(speeds),
                speed_high=max(speeds),
                resting_hr=resting_hr,
                efficiency=efficiency,
                slope=60 / efficiency,
                intercept=resting_hr,
            )
        )

    return lines
