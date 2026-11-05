"""Pure time-series helpers for report metrics.

These functions operate on dates and numbers only. They know nothing about
activities, data sources, or plotting.
"""

import math
from datetime import date, timedelta


def date_range(start: date, end: date) -> list[date]:
    """Return every day from ``start`` to ``end`` inclusive."""
    if start > end:
        return []

    return [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
    ]


def daily_sums(
    values_by_day: dict[date, float],
    start: date,
    end: date,
    *,
    fill: float = 0.0,
) -> list[tuple[date, float]]:
    """Return a complete daily series, filling missing days with ``fill``."""
    return [
        (day, values_by_day.get(day, fill))
        for day in date_range(start, end)
    ]


def sma(values: list[float], window: int) -> list[float]:
    """Trailing simple moving average, including the current value."""
    if window <= 0:
        raise ValueError("window must be positive")

    result = []

    for index in range(len(values)):
        chunk = values[max(0, index - window + 1): index + 1]
        result.append(sum(chunk) / len(chunk))

    return result


def ewma(
    values: list[float],
    alpha: float,
    initial: float = 0.0,
) -> list[float]:
    """Exponentially weighted moving average with an explicit ``alpha``."""
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")

    result = []
    state = initial

    for value in values:
        state = alpha * value + (1 - alpha) * state
        result.append(state)

    return result


def ewma_series(
    points: list[tuple[date, float]],
    alpha: float,
    initial: float = 0.0,
) -> list[tuple[date, float]]:
    """Apply :func:`ewma` to a dated series."""
    values = ewma([value for _, value in points], alpha, initial)
    return [
        (day, smoothed)
        for (day, _), smoothed in zip(points, values)
    ]


def alpha_from_time_constant(tau_days: float) -> float:
    """Alpha for an exponential average with a time constant in days."""
    if tau_days <= 0:
        raise ValueError("tau_days must be positive")

    return 1 - math.exp(-1 / tau_days)


def alpha_from_half_life(half_life_days: float) -> float:
    """Alpha for an exponential average with a half-life in days."""
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")

    return 1 - 0.5 ** (1 / half_life_days)


def alpha_from_span(span: float) -> float:
    """Alpha using the common ``2 / (N + 1)`` span convention."""
    if span <= 0:
        raise ValueError("span must be positive")

    return 2 / (span + 1)
