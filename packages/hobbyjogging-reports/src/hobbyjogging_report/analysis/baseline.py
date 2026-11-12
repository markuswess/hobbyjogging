"""Robust, date-aware baselines for wellness metrics.

The center is the median of the trailing window and the spread is
``1.4826 * median absolute deviation`` (a consistent estimator of the
standard deviation for normal data). A mean/SD baseline is too sensitive
to a single bad night, and a short window slowly *becomes* an illness, so
both the readiness bands and the efficiency baseline use a one-year
window with an expanding fallback.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

MAD_TO_SIGMA = 1.4826
BASELINE_WINDOW_DAYS = 365


@dataclass(frozen=True)
class RobustBaseline:
    """Median and MAD-derived spread of the values in the baseline set."""

    center: float
    spread: float
    count: int


def robust_baselines(
    samples: Iterable[tuple[date, float | None]],
    *,
    window_days: int = BASELINE_WINDOW_DAYS,
    min_values: int = 1,
) -> Callable[[date], RobustBaseline | None]:
    """Build a per-day robust-baseline lookup from dated samples.

    When the trailing window has fewer than ``min_values`` measurements,
    the lookup expands over all earlier values; it returns ``None`` when
    even that is not enough.
    """
    if window_days <= 0:
        raise ValueError("window must be positive")
    if min_values <= 0:
        raise ValueError("min_values must be positive")

    points = sorted(
        (day, value)
        for day, value in samples
        if value is not None
    )
    days = [point[0] for point in points]
    values = [point[1] for point in points]

    def baseline(day: date) -> RobustBaseline | None:
        end = bisect_right(days, day)

        if not end:
            return None

        start = bisect_left(
            days,
            day - timedelta(days=window_days - 1),
        )
        window = values[start:end]
        chosen = window if len(window) >= min_values else values[:end]

        if len(chosen) < min_values:
            return None

        center = median(chosen)
        mad = median(abs(value - center) for value in chosen)

        return RobustBaseline(
            center=center,
            spread=MAD_TO_SIGMA * mad,
            count=len(chosen),
        )

    return baseline


def robust_baseline(
    samples: Iterable[tuple[date, float | None]],
    day: date,
    *,
    window_days: int = BASELINE_WINDOW_DAYS,
    min_values: int = 1,
) -> RobustBaseline | None:
    """Robust baseline for one day; see :func:`robust_baselines`."""
    return robust_baselines(
        samples,
        window_days=window_days,
        min_values=min_values,
    )(day)
