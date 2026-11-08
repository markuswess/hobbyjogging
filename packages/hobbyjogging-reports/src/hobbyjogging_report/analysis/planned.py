"""Planned-event aggregates for charts and reports."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from hobbyjogging_core.model import Event

from .common import _planned_events, week_start


def weekly_planned_distance(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned running distance (km) per week, oldest first.

    Events without a planned distance are skipped.
    """
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end, running_only=True):
        if event.distance_m:
            totals[week_start(event.date)] += event.distance_m

    return [(week, totals[week] / 1000) for week in sorted(totals)]


def weekly_planned_time(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned running time (seconds) per week, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end, running_only=True):
        if event.duration_s:
            totals[week_start(event.date)] += event.duration_s

    return [(week, totals[week]) for week in sorted(totals)]


def daily_planned_distance(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned running distance (km) per day, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end, running_only=True):
        if event.distance_m:
            totals[event.date] += event.distance_m / 1000

    return sorted(totals.items())


def daily_planned_time(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned running time (seconds) per day, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end, running_only=True):
        if event.duration_s:
            totals[event.date] += event.duration_s

    return sorted(totals.items())


def daily_planned_load(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned training load per day, oldest first.

    All sports are included; days without planned load are skipped.
    """
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end):
        if event.training_load:
            totals[event.date] += event.training_load

    return sorted(totals.items())


def planned_workout_dates(
    events: list[Event],
    start: date,
    end: date,
) -> list[date]:
    """One date per planned workout, oldest first.

    Events without a sport type are notes (illness, travel) and are skipped.
    Multiple workouts on one day produce repeated dates.
    """
    return sorted(
        event.date
        for event in _planned_events(events, start, end)
    )
