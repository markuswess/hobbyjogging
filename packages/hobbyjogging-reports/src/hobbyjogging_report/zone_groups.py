"""Grouped running-zone series used by charts and the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.model import Activity, Event

from .analysis import (
    daily_planned_time,
    daily_planned_zone_time,
    daily_run_time,
    daily_zone_time,
)
from .model import AverageWindows
from .series import alpha_from_time_constant, date_range, ewma


@dataclass(frozen=True)
class ZoneGroupPoint:
    """Daily easy/hard time with 7/42/182-day EWMAs."""

    date: date
    easy_s: float
    hard_s: float
    unzoned_s: float
    easy_7: float
    easy_42: float
    easy_182: float
    hard_7: float
    hard_42: float
    hard_182: float
    total_7: float
    total_42: float
    total_182: float
    projected: bool = False


@dataclass(frozen=True)
class ZoneGroupSeries:
    points: list[ZoneGroupPoint]


def daily_zone_groups(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    zone_count: int = 4,
) -> list[tuple[date, float, float, float]]:
    """Daily running seconds as ``(low, high, unzoned)``.

    ``low`` is Z1+Z2, ``high`` is Z3+Z4, and ``unzoned`` is running time not
    covered by the recorded pace zones.
    """
    zones_by_day = dict(
        daily_zone_time(
            activities,
            start,
            end,
            zone_count=zone_count,
        )
    )
    totals = dict(daily_run_time(activities, start, end))
    rows = []

    for day in date_range(start, end):
        zones = zones_by_day.get(day, [0.0] * zone_count)
        low = sum(zones[:2])
        high = sum(zones[2:4])
        unzoned = max(totals.get(day, 0.0) - low - high, 0.0)
        rows.append((day, low, high, unzoned))

    return rows


def planned_daily_zone_groups(
    events: list[Event],
    start: date,
    end: date,
    *,
    zone_count: int = 4,
) -> list[tuple[date, float, float, float]]:
    """Planned running seconds as ``(low, high, unzoned)`` per day.

    ``low``/``high`` come from planned pace zones; planned running events
    without pace zones become ``unzoned``.
    """
    if start > end:
        return []

    zones_by_day = dict(
        daily_planned_zone_time(
            events,
            start,
            end,
            kind="pace",
            zone_count=zone_count,
        )
    )
    totals = dict(daily_planned_time(events, start, end))
    rows = []

    for day in date_range(start, end):
        zones = zones_by_day.get(day, [0.0] * zone_count)
        low = sum(zones[:2])
        high = sum(zones[2:4])
        unzoned = max(totals.get(day, 0.0) - low - high, 0.0)
        rows.append((day, low, high, unzoned))

    return rows


def planned_bars_without_actual(
    events: list[Event],
    actual_bars: list[tuple[date, float, float, float]],
    start: date,
    end: date,
    *,
    zone_count: int = 4,
) -> list[tuple[date, float, float, float]]:
    """Planned bars, dropping days that already have actual running time."""
    actual_days = {
        day
        for day, low, high, unzoned in actual_bars
        if low + high + unzoned > 0
    }

    return [
        row
        for row in planned_daily_zone_groups(
            events,
            start,
            end,
            zone_count=zone_count,
        )
        if row[0] not in actual_days
    ]


def zone_group_series(
    activities: list[Activity],
    events: list[Event],
    start: date,
    end: date,
    *,
    chart_start: date | None = None,
    projection_start: date | None = None,
    zone_count: int = 4,
    windows: AverageWindows | None = None,
) -> ZoneGroupSeries:
    """Build easy/hard EWMAs from actual data and planned rest days.

    Days with recorded running time use actual values; other days fall back
    to planned values. The EWMA starts at ``start``, so pass a warm-up range.
    ``projection_start`` marks the first day rendered as projection; it
    defaults to ``end``.
    """
    if start > end:
        return ZoneGroupSeries(points=[])

    windows = windows or AverageWindows()
    projection_start = projection_start or end
    actual = {
        row[0]: row
        for row in daily_zone_groups(
            activities,
            start,
            end,
            zone_count=zone_count,
        )
    }
    planned = {
        row[0]: row
        for row in planned_daily_zone_groups(
            events,
            start,
            end,
            zone_count=zone_count,
        )
    }
    days = date_range(start, end)
    rows = []

    for day in days:
        actual_row = actual.get(day)
        actual_total = (
            sum(actual_row[1:])
            if actual_row is not None
            else 0.0
        )

        if actual_total > 0:
            rows.append((day, *actual_row[1:], False))
            continue

        planned_row = planned.get(day)

        rows.append(
            (
                day,
                *(planned_row[1:] if planned_row is not None else (0.0, 0.0, 0.0)),
                True,
            )
        )

    easy = [row[1] for row in rows]
    hard = [row[2] for row in rows]
    total = [
        row[1] + row[2] + row[3]
        for row in rows
    ]
    taus = (windows.fatigue, windows.fitness, windows.base)

    def columns(series):
        return {
            tau: ewma(series, alpha_from_time_constant(tau))
            for tau in taus
        }

    easy_columns = columns(easy)
    hard_columns = columns(hard)
    total_columns = columns(total)
    points = []

    for index, (day, easy_s, hard_s, unzoned_s, _used_planned) in enumerate(
        rows
    ):
        if chart_start is not None and day < chart_start:
            continue

        points.append(
            ZoneGroupPoint(
                date=day,
                easy_s=easy_s,
                hard_s=hard_s,
                unzoned_s=unzoned_s,
                easy_7=easy_columns[windows.fatigue][index],
                easy_42=easy_columns[windows.fitness][index],
                easy_182=easy_columns[windows.base][index],
                hard_7=hard_columns[windows.fatigue][index],
                hard_42=hard_columns[windows.fitness][index],
                hard_182=hard_columns[windows.base][index],
                total_7=total_columns[windows.fatigue][index],
                total_42=total_columns[windows.fitness][index],
                total_182=total_columns[windows.base][index],
                projected=(
                    _used_planned
                    and day >= projection_start
                ),
            )
        )

    return ZoneGroupSeries(points=points)
