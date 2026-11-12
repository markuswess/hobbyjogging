"""7/42/182-day EWMAs of subT/LT1 work pace and session heart rate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .averages import DEFAULT_AVERAGE_WINDOWS
from ..model import AverageWindows, SubtPoint
from ..series import alpha_from_time_constant, date_range, ewma

CATEGORIES = ("short", "medium", "long", "lt1")


@dataclass(frozen=True)
class SubtEwmaRow:
    """One category's smoothed pace and heart rate."""

    category: str
    pace: dict[int, float | None]
    hr: dict[int, float | None]
    efficiency: dict[int, float | None]


def _daily_means(points: list[SubtPoint], category: str, start: date, end: date):
    """Return ``(pace_by_day, hr_by_day)`` means for one category."""
    paces: dict[date, list[float]] = {}
    hrs: dict[date, list[float]] = {}

    for point in points:
        if point.category != category or not (start <= point.date <= end):
            continue

        paces.setdefault(point.date, []).append(point.pace_s_per_km)

        if point.avg_hr is not None:
            hrs.setdefault(point.date, []).append(point.avg_hr)

    return (
        {day: sum(values) / len(values) for day, values in paces.items()},
        {day: sum(values) / len(values) for day, values in hrs.items()},
    )


def _daily_efficiency(
    points: list[SubtPoint],
    category: str,
    start: date,
    end: date,
) -> dict[date, float]:
    """Weighted metres per excess beat per day: distance / excess beats."""
    by_day: dict[date, tuple[float, float]] = {}

    for point in points:
        if point.category != category or not (start <= point.date <= end):
            continue

        if point.efficiency is None or point.beats <= 0 or not point.distance_m:
            continue

        distance, beats = by_day.get(point.date, (0.0, 0.0))
        by_day[point.date] = (
            distance + point.distance_m,
            beats + point.beats,
        )

    return {
        day: distance / beats
        for day, (distance, beats) in by_day.items()
        if beats > 0
    }


def _last_ewma(
    values_by_day: dict[date, float],
    start: date,
    end: date,
    alpha: float,
) -> float | None:
    """EWMA ending ``end``; the last value carries between sessions."""
    if not values_by_day:
        return None

    carried = None
    values = []

    for day in date_range(start, end):
        if day in values_by_day:
            carried = values_by_day[day]

        values.append(carried)

    first = next(
        (index for index, value in enumerate(values) if value is not None),
        None,
    )

    if first is None:
        return None

    return ewma(values[first:], alpha, initial=values[first])[-1]


def subt_ewma(
    points: list[SubtPoint],
    start: date,
    end: date,
    *,
    windows: AverageWindows | None = None,
) -> list[SubtEwmaRow]:
    """Return one row per category with its 7/42/182-day EWMAs at ``end``.

    ``points`` must include the warm-up range before ``start``. Days between
    sessions keep the last measured value, so the averages describe the
    standing work pace and heart rate of that category.
    """
    windows = windows or DEFAULT_AVERAGE_WINDOWS

    if start > end:
        return []

    taus = (windows.fatigue, windows.fitness, windows.base)
    rows = []

    for category in CATEGORIES:
        pace_by_day, hr_by_day = _daily_means(
            points,
            category,
            start,
            end,
        )
        efficiency_by_day = _daily_efficiency(
            points,
            category,
            start,
            end,
        )
        rows.append(
            SubtEwmaRow(
                category=category,
                pace={
                    tau: _last_ewma(
                        pace_by_day,
                        start,
                        end,
                        alpha_from_time_constant(tau),
                    )
                    for tau in taus
                },
                hr={
                    tau: _last_ewma(
                        hr_by_day,
                        start,
                        end,
                        alpha_from_time_constant(tau),
                    )
                    for tau in taus
                },
                efficiency={
                    tau: _last_ewma(
                        efficiency_by_day,
                        start,
                        end,
                        alpha_from_time_constant(tau),
                    )
                    for tau in taus
                },
            )
        )

    return rows
