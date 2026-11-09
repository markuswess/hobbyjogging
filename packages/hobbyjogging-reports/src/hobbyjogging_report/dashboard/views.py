"""View data collected for the static dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.model import Activity, Event

from ..analysis import (
    RUN_TYPES,
    daily_planned_zone_time,
    weekly_time_by_zone,
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


def actual_zone_totals(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    zone_count: int = 4,
) -> tuple[list[float], float]:
    weeks = weekly_time_by_zone(
        activities,
        start,
        end,
        zone_count=zone_count,
    )
    zones = [
        sum(week.zones[index] for week in weeks)
        for index in range(zone_count)
    ]
    unzoned = sum(week.unzoned for week in weeks)
    return zones, unzoned


def planned_zone_totals(
    events: list[Event],
    start: date,
    end: date,
    *,
    zone_count: int = 4,
) -> list[float]:
    series = daily_planned_zone_time(
        events,
        start,
        end,
        kind="pace",
        zone_count=zone_count,
    )
    return [
        sum(zones[index] for _, zones in series)
        for index in range(zone_count)
    ]
