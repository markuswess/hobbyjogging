"""Derive typed WORK/RECOVERY reps from device laps when none were imported.

Intervals.icu is the only typed source. A Runalyze+Garmin athlete has device
laps but no WORK/RECOVERY typing, so a structured session shows splits but no
subT reps. This recompute infers them, conservatively:

- a measured set always wins: any interval whose source is not ``derived``
  stops the task for that activity;
- the gate is the Runalyze type (the stored ``intervals`` method or
  ``subthreshold`` target after item 49) or a strong lap-pace spread;
- a work lap is at least 60 s and within 20 % of the fastest third's pace;
- at least two work laps and one slower recovery lap are required.

The result is written with ``source='derived'`` so the reports can label it.
"""

from __future__ import annotations

from statistics import median

from hobbyjogging_core.classify import WORK_MIN_DURATION_S, WORK_PACE_BAND
from hobbyjogging_core.model import Interval, Lap
from hobbyjogging_core.sports import RUN_SPORTS

from ..context import TaskContext
from ..registry import task
from ..workouts import scoped_activities

SOURCE = "derived"

# A lap needs enough distance to have a meaningful pace.
MIN_LAP_DISTANCE_M = 100.0
# Without an intervals-type signal, the slowest and fastest qualifying lap must
# differ this much before a session counts as structured.
MIN_PACE_SPREAD = 1.50
MIN_WORK_REPS = 2

_COUNT_ORDER = (
    "activities",
    "derived",
    "unchanged",
    "has_measured",
    "not_run",
    "no_laps",
    "uniform",
    "too_few_reps",
)


@task(
    "derived_intervals_current",
    kind="recompute",
    description=(
        "Infer WORK/RECOVERY reps from device laps when no typed set exists."
    ),
)
def derived_intervals_current(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    for activity in activities:
        context.count("activities")

        if activity.type not in RUN_SPORTS:
            context.count("not_run")
            continue

        existing = context.repository.activity_intervals(activity.id)
        if any(interval.source != SOURCE for interval in existing):
            context.count("has_measured")
            continue

        laps = context.repository.activity_laps(activity.id)
        qualifying = [lap for lap in laps if _qualifies(lap)]
        if len(qualifying) < 2:
            context.count("no_laps")
            continue

        paces = [_pace(lap) for lap in qualifying]
        structured = (
            "intervals" in activity.workout_methods
            or "subthreshold" in activity.workout_targets
        )
        reference = median(sorted(paces)[: max(1, len(paces) // 3)])
        work = [
            lap
            for lap in qualifying
            if _pace(lap) <= reference * WORK_PACE_BAND
        ]
        recovery = [
            lap
            for lap in qualifying
            if _pace(lap) > reference * WORK_PACE_BAND
        ]

        if not recovery or (
            not structured and max(paces) / min(paces) < MIN_PACE_SPREAD
        ):
            context.count("uniform")
            continue
        if len(work) < MIN_WORK_REPS:
            context.count("too_few_reps")
            continue

        derived = [
            _interval(lap, "WORK" if lap in work else "RECOVERY")
            for lap in qualifying
        ]
        if _same(existing, derived):
            context.count("unchanged")
            continue

        context.writer.replace_derived_intervals(activity.id, derived)
        context.count("derived")

    context.order_counts(_COUNT_ORDER)


def _qualifies(lap: Lap) -> bool:
    return (
        lap.duration_s >= WORK_MIN_DURATION_S
        and lap.distance_m >= MIN_LAP_DISTANCE_M
    )


def _pace(lap: Lap) -> float:
    """Seconds per kilometre."""
    return lap.duration_s / lap.distance_m * 1000.0


def _interval(lap: Lap, kind: str) -> Interval:
    return Interval(
        type=kind,
        start_time=lap.start_time_utc,
        duration_s=lap.duration_s,
        distance_m=lap.distance_m,
        avg_hr=lap.avg_hr,
        max_hr=lap.max_hr,
        source=SOURCE,
    )


def _same(existing: list[Interval], derived: list[Interval]) -> bool:
    if len(existing) != len(derived):
        return False
    for current, proposed in zip(existing, derived):
        if (
            current.type != proposed.type
            or current.start_time != proposed.start_time
            or abs(current.duration_s - proposed.duration_s) > 0.5
            or abs(current.distance_m - proposed.distance_m) > 0.5
        ):
            return False
    return True
