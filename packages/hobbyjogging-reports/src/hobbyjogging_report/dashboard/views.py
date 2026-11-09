"""View data collected for the static dashboard."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.model import Activity, Event

from ..analysis import (
    RUN_TYPES,
    daily_planned_time,
    daily_planned_zone_time,
    daily_run_distance,
    daily_run_time,
    daily_training_load,
    daily_zone_time,
    event_zone_time,
)
from ..model import AverageWindows
from ..series import (
    alpha_from_time_constant,
    date_range,
    ewma,
)
from ..summary import summarize_training


@dataclass(frozen=True)
class WindowSummary:
    runs: int
    cross: int
    run_time_s: float
    cross_time_s: float
    run_distance_m: float
    run_load: float
    load: float
    z3_z4_s: float
    quality: list[Activity]


@dataclass(frozen=True)
class PlannedSummary:
    events: list[Event]
    run_time_s: float
    run_distance_m: float
    load: float


@dataclass(frozen=True)
class EwmaRow:
    key: str
    label: str
    kind: str
    values: dict[int, float]


@dataclass(frozen=True)
class PlannedOverview:
    runs: int = 0
    cross: int = 0
    run_time_s: float = 0
    run_distance_m: float = 0
    load: float = 0
    z3_z4_s: float = 0


def planned_overview(
    events: list[Event],
    start: date,
    end: date,
) -> PlannedOverview:
    """Planned totals for the next overview period."""
    selected = [
        event
        for event in events
        if event.type and start <= event.date <= end
    ]
    runs = [event for event in selected if event.type in RUN_TYPES]
    cross = [event for event in selected if event.type not in RUN_TYPES]

    return PlannedOverview(
        runs=len(runs),
        cross=len(cross),
        run_time_s=sum(event.duration_s or 0 for event in runs),
        run_distance_m=sum(event.distance_m or 0 for event in runs),
        load=sum(event.training_load or 0 for event in selected),
        z3_z4_s=sum(
            event_zone_time(event, (3, 4)) or 0
            for event in runs
        ),
    )


def overview_ewma(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    windows: AverageWindows | None = None,
) -> list[EwmaRow]:
    """Weekly-equivalent EWMAs of daily training metrics ending at ``end``."""
    if start > end:
        return []

    windows = windows or AverageWindows()
    days = date_range(start, end)
    runs_by_day: dict[date, float] = defaultdict(float)
    cross_by_day: dict[date, float] = defaultdict(float)

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        if activity.type in RUN_TYPES:
            runs_by_day[activity.date] += 1
        else:
            cross_by_day[activity.date] += 1

    runs = [runs_by_day.get(day, 0.0) for day in days]
    cross = [cross_by_day.get(day, 0.0) for day in days]
    run_time = [value for _, value in daily_run_time(activities, start, end)]
    run_distance = [
        value for _, value in daily_run_distance(activities, start, end)
    ]
    load = [value for _, value in daily_training_load(activities, start, end)]
    z3_z4 = [
        sum(zones[2:4])
        for _, zones in daily_zone_time(
            activities,
            start,
            end,
            zone_count=4,
        )
    ]
    taus = (windows.fatigue, windows.fitness, windows.base)

    def weekly(series: list[float]) -> dict[int, float]:
        return {
            tau: ewma(
                series,
                alpha_from_time_constant(tau),
            )[-1] * 7
            for tau in taus
        }

    return [
        EwmaRow("runs", "Runs / week", "count", weekly(runs)),
        EwmaRow("cross", "Cross / week", "count", weekly(cross)),
        EwmaRow("run_time_s", "Run time / week", "time", weekly(run_time)),
        EwmaRow(
            "run_distance_m",
            "Run km / week",
            "distance",
            weekly(run_distance),
        ),
        EwmaRow("load", "Load / week", "load", weekly(load)),
        EwmaRow("z3_z4_s", "Z3+4 / week", "time", weekly(z3_z4)),
    ]


def summarize_window(activities: list[Activity]) -> WindowSummary:
    training = summarize_training(activities)
    runs = sum(
        1 for activity in activities if activity.type in RUN_TYPES
    )

    return WindowSummary(
        runs=runs,
        cross=len(activities) - runs,
        run_time_s=training["run_time"],
        cross_time_s=training["cross_time"],
        run_distance_m=training["run_distance"],
        run_load=training["run_load"],
        load=training["run_load"] + training["cross_load"],
        z3_z4_s=training["z3_z4_time"],
        quality=training["quality"],
    )


def in_window(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[Activity]:
    return [
        activity
        for activity in activities
        if start <= activity.date <= end
    ]


def planned_summary(events: list[Event]) -> PlannedSummary:
    runs = [event for event in events if event.type in RUN_TYPES]

    return PlannedSummary(
        events=events,
        run_time_s=sum(event.duration_s or 0 for event in runs),
        run_distance_m=sum(event.distance_m or 0 for event in runs),
        load=sum(event.training_load or 0 for event in runs),
    )


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
