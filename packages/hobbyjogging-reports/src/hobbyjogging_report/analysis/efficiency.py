"""Efficiency in metres per excess heartbeat.

Higher is better and the metric is linear, unlike pace/HR or HR/pace, which
are reciprocal. Aggregates must always be ``sum(distance) / sum(excess
beats)``, never the mean of per-sample ratios.

The raw ``distance / (HR * min)`` ratio is biased by the heart-rate offset.
A fit on the real data gives ``HR ≈ 52.5 + 26.2 * v`` (R² = 0.54), with the
intercept matching the median resting HR (51 bpm). ``v / HR`` spreads 11.3%
across speed quartiles, while ``v / (HR - RHR)`` spreads only 3.3%, so the
resting baseline is subtracted to make paces comparable.

The baseline is the median resting HR over the trailing 365 days, falling
back to an expanding median when there is less history, and ``None`` when
there is none at all. A short window must not be used: the Feb-Mar 2026
illness moved RHR 51 -> 59 -> 47, and a 42-day median still read ~57 in
March. That inflated March efficiency to 2.40 vs 2.22 for the long
baseline (+8%), larger than the 3.3% pace bias this metric exists to
remove. The 180-day, 365-day, and fixed medians agree within 0.01 over the
whole series; 365 days is about six times the episode.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

from hobbyjogging_core.model import Activity, Interval, WellnessDay

from .baseline import robust_baselines
from .common import RUN_TYPES

EFFICIENCY_UNIT = "m/excess beat"
RESTING_HR_WINDOW_DAYS = 365
MIN_EXCESS_HR = 10


def resting_hr_baseline(
    wellness: Iterable[WellnessDay],
    day: date,
    *,
    window_days: int = RESTING_HR_WINDOW_DAYS,
) -> float | None:
    """Median resting HR over the trailing window ending on ``day``.

    When the window is empty the median expands over all earlier values;
    with no values at all the result is ``None``.
    """
    return resting_hr_baselines(wellness, window_days=window_days)(day)


def resting_hr_baselines(
    wellness: Iterable[WellnessDay],
    *,
    window_days: int = RESTING_HR_WINDOW_DAYS,
) -> Callable[[date], float | None]:
    """Build a per-day resting-HR baseline lookup from wellness days.

    The lookup is pure: callers fetch the wellness (with a year of lead-in)
    and pass the resulting function through the rendering stack.
    """
    lookup = robust_baselines(
        ((entry.date, entry.resting_hr) for entry in wellness),
        window_days=window_days,
    )

    def baseline(day: date) -> float | None:
        result = lookup(day)
        return None if result is None else result.center

    return baseline


def excess_beats(
    duration_s: float | None,
    avg_hr: float | None,
    resting_hr: float | None,
) -> float | None:
    """Heartbeats above resting during a session, or ``None`` when unusable."""
    if not duration_s or duration_s <= 0:
        return None

    if avg_hr is None or resting_hr is None:
        return None

    excess = avg_hr - resting_hr

    if excess < MIN_EXCESS_HR:
        return None

    return excess * duration_s / 60


def m_per_excess_beat(
    distance_m: float | None,
    duration_s: float | None,
    avg_hr: float | None,
    resting_hr: float | None,
) -> float | None:
    """Metres per excess heartbeat, or ``None`` when a piece is missing."""
    total_beats = excess_beats(duration_s, avg_hr, resting_hr)

    if not distance_m or distance_m <= 0 or total_beats is None:
        return None

    return distance_m / total_beats


def activity_efficiency(
    activity: Activity,
    resting_hr: float | None,
) -> float | None:
    """Running efficiency for one activity."""
    if activity.type not in RUN_TYPES:
        return None

    return m_per_excess_beat(
        activity.distance_m,
        activity.duration_s,
        activity.avg_hr,
        resting_hr,
    )


def interval_efficiency(
    interval: Interval,
    resting_hr: float | None,
) -> float | None:
    """Running efficiency for one interval."""
    return m_per_excess_beat(
        interval.distance_m,
        interval.duration_s,
        interval.avg_hr,
        resting_hr,
    )


def aggregate_efficiency(
    samples: Iterable[
        tuple[float | None, float | None, float | None, float | None]
    ],
) -> float | None:
    """Weighted efficiency over ``(distance, duration, HR, resting HR)``."""
    total_distance = 0.0
    total_beats = 0.0

    for distance_m, duration_s, avg_hr, resting_hr in samples:
        sample_beats = excess_beats(duration_s, avg_hr, resting_hr)

        if not distance_m or distance_m <= 0 or sample_beats is None:
            continue

        total_distance += distance_m
        total_beats += sample_beats

    if total_beats <= 0:
        return None

    return total_distance / total_beats
