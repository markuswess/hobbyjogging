"""EWMA and rolling-average helpers shared by load, distance, and time."""

from __future__ import annotations

from datetime import date, timedelta

from ..model import AverageWindows
from ..series import alpha_from_time_constant, daily_sums, ewma

DEFAULT_AVERAGE_WINDOWS = AverageWindows()
AVERAGE_WARMUP_FACTOR = 5


def average_warmup_days(windows: AverageWindows | None = None) -> int:
    """Days of history needed before a load chart's display range."""
    windows = windows or DEFAULT_AVERAGE_WINDOWS
    return AVERAGE_WARMUP_FACTOR * max(
        windows.base,
        windows.fitness,
        windows.fatigue,
    )


def _ewma_columns(
    series: list[tuple[date, float]],
    windows: AverageWindows,
) -> tuple[list[float], list[float], list[float]]:
    """Return the base, fitness, and fatigue EWMA columns."""
    values = [value for _, value in series]

    return (
        ewma(values, alpha_from_time_constant(windows.base)),
        ewma(values, alpha_from_time_constant(windows.fitness)),
        ewma(values, alpha_from_time_constant(windows.fatigue)),
    )


def _average_rows(
    series: list[tuple[date, float]],
    start: date,
    windows: AverageWindows,
    *,
    projected_start: date | None = None,
) -> list[tuple[date, float, float, float, float, bool]]:
    """Return ``(date, value, base, fitness, fatigue, projected)`` rows."""
    base, fitness, fatigue = _ewma_columns(series, windows)

    return [
        (
            day,
            value,
            base_value,
            fitness_value,
            fatigue_value,
            projected_start is not None and day > projected_start,
        )
        for (day, value), base_value, fitness_value, fatigue_value in zip(
            series,
            base,
            fitness,
            fatigue,
        )
        if day >= start
    ]


def _extend_series(
    series: list[tuple[date, float]],
    planned: list[tuple[date, float]],
    projected_end: date,
) -> list[tuple[date, float]]:
    """Continue a daily series with planned values, zero-filling rest days."""
    next_day = series[-1][0] + timedelta(days=1)
    return series + daily_sums(dict(planned), next_day, projected_end)
