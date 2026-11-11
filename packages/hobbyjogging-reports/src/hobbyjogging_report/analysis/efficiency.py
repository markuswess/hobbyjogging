"""Efficiency in meters per heartbeat.

Higher is better and the metric is linear, unlike pace/HR or HR/pace which
are reciprocal. Aggregates must always be ``sum(distance) / sum(beats)``,
never the mean of per-sample ratios.
"""

from __future__ import annotations

from collections.abc import Iterable

from hobbyjogging_core.model import Activity, Interval

from .common import RUN_TYPES

EFFICIENCY_UNIT = "m/beat"


def beats(duration_s: float | None, avg_hr: float | None) -> float | None:
    """Heartbeats during a session: average HR times minutes."""
    if not duration_s or not avg_hr:
        return None

    if duration_s <= 0 or avg_hr <= 0:
        return None

    return avg_hr * duration_s / 60


def m_per_beat(
    distance_m: float | None,
    duration_s: float | None,
    avg_hr: float | None,
) -> float | None:
    """Meters covered per heartbeat, or ``None`` when a piece is missing."""
    total_beats = beats(duration_s, avg_hr)

    if not distance_m or distance_m <= 0 or total_beats is None:
        return None

    return distance_m / total_beats


def activity_efficiency(activity: Activity) -> float | None:
    """Running efficiency for one activity."""
    if activity.type not in RUN_TYPES:
        return None

    return m_per_beat(
        activity.distance_m,
        activity.duration_s,
        activity.avg_hr,
    )


def interval_efficiency(interval: Interval) -> float | None:
    """Running efficiency for one interval."""
    return m_per_beat(
        interval.distance_m,
        interval.duration_s,
        interval.avg_hr,
    )


def aggregate_efficiency(
    samples: Iterable[tuple[float | None, float | None, float | None]],
) -> float | None:
    """Weighted efficiency over ``(distance_m, duration_s, avg_hr)`` samples."""
    total_distance = 0.0
    total_beats = 0.0

    for distance_m, duration_s, avg_hr in samples:
        sample_beats = beats(duration_s, avg_hr)

        if not distance_m or distance_m <= 0 or sample_beats is None:
            continue

        total_distance += distance_m
        total_beats += sample_beats

    if total_beats <= 0:
        return None

    return total_distance / total_beats
