"""Derive local zone configs from manual threshold snapshots.

Intervals supplies zone boundaries on its own activities; an Intervals-less
athlete has none, and Runalyze's zone percentages are shares of an unknown
config, not boundaries. This recompute builds a config from the dated
threshold snapshot that applies to the activity:

- HR, from LTHR with upper bounds ``[0.80, 0.89, 1.00, 1.10]``; when only
  max HR exists, ``[0.60, 0.70, 0.80, 0.90]`` of max HR;
- pace, as speed with upper bounds ``[0.75, 0.85, 1.00, 1.10]`` of threshold
  speed (m/s), so a faster lap lands in a higher zone.

Boundaries are stored in their native unit (bpm, m/s). Zone times are summed
from device laps where a lap carries an average HR or a pace; an activity with
no zone config, or no threshold that applies to its date, stays unzoned rather
than borrowing a later guess. Existing Intervals configs and times always win.
"""

from __future__ import annotations

from datetime import date

from hobbyjogging_core.model import Activity, AthleteThreshold, Lap

from ..context import TaskContext
from ..registry import task
from ..workouts import scoped_activities

SOURCE = "thresholds"

HR_LTHR_SHARES = (0.80, 0.89, 1.00, 1.10)
HR_MAX_SHARES = (0.60, 0.70, 0.80, 0.90)
PACE_SPEED_SHARES = (0.75, 0.85, 1.00, 1.10)

_COUNT_ORDER = (
    "activities",
    "configs",
    "zone_times",
    "already",
    "no_threshold",
    "no_laps",
    "unchanged",
)


@task(
    "derived_zone_configs_current",
    kind="recompute",
    description=(
        "Build local HR/pace zone configs and lap zone times from manual "
        "thresholds."
    ),
)
def derived_zone_configs_current(context: TaskContext) -> None:
    thresholds = context.repository.athlete_thresholds()
    if not thresholds:
        context.note("No threshold snapshots stored.")
        return

    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    for activity in activities:
        context.count("activities")

        current = context.connection.execute(
            """
            SELECT hr_zone_config_id, pace_zone_config_id
            FROM activities WHERE id = ?
            """,
            (activity.id,),
        ).fetchone()
        hr_id = current["hr_zone_config_id"]
        pace_id = current["pace_zone_config_id"]

        wanted_hr = hr_id is None
        wanted_pace = pace_id is None
        if not wanted_hr and not wanted_pace:
            context.count("already")
            continue

        threshold = _threshold_for(
            thresholds,
            activity.type,
            activity.date,
        )
        if threshold is None:
            context.count("no_threshold")
            continue

        if wanted_hr:
            boundaries = _hr_boundaries(threshold)
            if boundaries:
                hr_id = context.writer.upsert_zone_config(
                    kind="hr",
                    boundaries=boundaries,
                    source=SOURCE,
                )
                context.count("configs")

        if wanted_pace:
            boundaries = _pace_boundaries(threshold)
            if boundaries:
                pace_id = context.writer.upsert_zone_config(
                    kind="pace",
                    boundaries=boundaries,
                    source=SOURCE,
                )
                context.count("configs")

        if hr_id == current["hr_zone_config_id"] and pace_id == current[
            "pace_zone_config_id"
        ]:
            context.count("unchanged")
            continue

        context.writer.set_activity_zone_configs(
            activity.id,
            hr_zone_config_id=hr_id,
            pace_zone_config_id=pace_id,
        )

        laps = context.repository.activity_laps(activity.id)
        if not laps:
            context.count("no_laps")
            continue

        if wanted_hr and hr_id is not None:
            _write_zone_times(
                context,
                activity,
                laps,
                kind="hr",
                boundaries=_hr_boundaries(threshold),
            )
        if wanted_pace and pace_id is not None:
            _write_zone_times(
                context,
                activity,
                laps,
                kind="pace",
                boundaries=_pace_boundaries(threshold),
            )

    if context.counts.get("no_threshold"):
        first = min(row.effective_from for row in thresholds)
        context.note(
            f"{context.counts['no_threshold']} activities have no threshold "
            f"snapshot in force for their sport; the first snapshot is "
            f"{first.isoformat()}"
        )

    context.order_counts(_COUNT_ORDER)


def _threshold_for(
    thresholds: list[AthleteThreshold],
    sport: str,
    day: date,
) -> AthleteThreshold | None:
    eligible = [
        row
        for row in thresholds
        if row.sport == sport and row.effective_from <= day
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda row: row.effective_from)


def _hr_boundaries(threshold: AthleteThreshold) -> list[float]:
    if threshold.lthr:
        return [
            round(share * threshold.lthr, 1)
            for share in HR_LTHR_SHARES
        ]
    if threshold.max_hr:
        return [
            round(share * threshold.max_hr, 1)
            for share in HR_MAX_SHARES
        ]
    return []


def _pace_boundaries(threshold: AthleteThreshold) -> list[float]:
    if not threshold.threshold_pace_mps:
        return []
    return [
        round(share * threshold.threshold_pace_mps, 3)
        for share in PACE_SPEED_SHARES
    ]


def _write_zone_times(
    context: TaskContext,
    activity: Activity,
    laps: list[Lap],
    *,
    kind: str,
    boundaries: list[float],
) -> None:
    if not boundaries:
        return

    seconds = [0.0] * len(boundaries)
    for lap in laps:
        value = _value(lap, kind)
        if value is None:
            continue
        index = _zone_index(value, boundaries)
        seconds[index - 1] += lap.duration_s

    if not any(seconds):
        return

    existing = [0.0] * len(boundaries)
    for row in context.connection.execute(
        """
        SELECT zone_index, seconds FROM activity_zone_times
        WHERE activity_id = ? AND kind = ?
        ORDER BY zone_index
        """,
        (activity.id, kind),
    ):
        index = int(row["zone_index"])
        if 1 <= index <= len(existing):
            existing[index - 1] = row["seconds"]
    if _same(existing, seconds):
        context.count("unchanged")
        return

    context.writer.set_activity_zone_times(activity.id, kind, seconds)
    context.count("zone_times")


def _value(lap: Lap, kind: str) -> float | None:
    if kind == "hr":
        return lap.avg_hr
    if lap.duration_s <= 0 or lap.distance_m <= 0:
        return None
    return lap.distance_m / lap.duration_s


def _zone_index(value: float, boundaries: list[float]) -> int:
    for index, boundary in enumerate(boundaries, start=1):
        if value <= boundary:
            return index
    return len(boundaries)


def _same(existing: list[float], seconds: list[float]) -> bool:
    if len(existing) != len(seconds):
        return False
    return all(
        abs(float(current) - proposed) < 0.5
        for current, proposed in zip(existing, seconds)
    )
