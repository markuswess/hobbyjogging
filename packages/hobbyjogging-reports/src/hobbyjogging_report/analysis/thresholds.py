"""Athlete threshold snapshots and official race paces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.model import AthleteThreshold, RaceResult

from .common import pace_s_per_km

RUN_THRESHOLD_SPORT = "run"


@dataclass(frozen=True)
class ThresholdPoint:
    """One dated run threshold snapshot in chart units."""

    date: date
    lthr: float | None
    max_hr: float | None
    pace_s_per_km: float | None


@dataclass(frozen=True)
class RacePacePoint:
    """One official race result's pace, for the threshold chart."""

    date: date
    pace_s_per_km: float
    name: str
    distance_m: float


def running_thresholds(
    thresholds: list[AthleteThreshold],
) -> list[ThresholdPoint]:
    """Run threshold snapshots, oldest first, with pace in s/km."""
    points = [
        ThresholdPoint(
            date=snapshot.effective_from,
            lthr=snapshot.lthr,
            max_hr=snapshot.max_hr,
            pace_s_per_km=(
                1000.0 / snapshot.threshold_pace_mps
                if snapshot.threshold_pace_mps
                else None
            ),
        )
        for snapshot in thresholds
        if snapshot.sport == RUN_THRESHOLD_SPORT
    ]
    return sorted(points, key=lambda point: point.date)


def threshold_at(
    thresholds: list[ThresholdPoint],
    day: date,
) -> ThresholdPoint | None:
    """The latest run threshold snapshot in effect on ``day``."""
    latest = None

    for point in thresholds:
        if point.date > day:
            break
        latest = point

    return latest


def race_pace_points(results: list[RaceResult]) -> list[RacePacePoint]:
    """Official race results with a usable distance and time."""
    points = []

    for result in results:
        if result.date is None or not result.official_distance_m:
            continue
        if not result.official_time_s:
            continue

        pace = pace_s_per_km(
            result.official_time_s,
            result.official_distance_m,
        )

        if pace is None:
            continue

        points.append(
            RacePacePoint(
                date=result.date,
                pace_s_per_km=pace,
                name=result.name or "Race",
                distance_m=result.official_distance_m,
            )
        )

    return sorted(points, key=lambda point: point.date)
