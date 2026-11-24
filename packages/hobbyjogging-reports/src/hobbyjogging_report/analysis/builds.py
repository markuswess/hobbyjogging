"""Marathon builds: the weeks of training that lead into each marathon."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta

from hobbyjogging_core.classify import classify
from hobbyjogging_core.model import Activity, Event

from .common import RUN_TYPES, week_start
from .planned import weekly_planned_distance, weekly_planned_time
from .races import RaceResult
from .zones import weekly_planned_time_by_zone

MARATHON_BUCKET = "M"
MARATHON_WEEKS = 18
MARATHON_MIN_M = 40_000.0
MARATHON_MAX_M = 44_500.0


@dataclass(frozen=True)
class BuildWeek:
    """One week of a build, labelled by its distance to the race week.

    Actual values come from the log; ``planned_*`` values come from the event
    calendar and are only set on upcoming weeks. ``planned`` says which set the
    display should use.
    """

    label: str
    week_start: date
    distance_km: float = 0.0
    time_s: float = 0.0
    fast_s: float = 0.0
    quality: int = 0
    has_data: bool = False
    planned: bool = False
    planned_distance_km: float | None = None
    planned_time_s: float | None = None
    planned_fast_s: float | None = None
    planned_quality: int | None = None


@dataclass(frozen=True)
class MarathonBuild:
    """One marathon and its leading weeks, oldest build first."""

    name: str
    date: date
    result_s: float | None
    planned: bool
    weeks: list[BuildWeek]


def _fast_seconds(activity: Activity) -> float:
    """Seconds in Z3+Z4; a trail run may only have HR zones."""
    zones = activity.pace_zone_times or []

    if not zones and activity.type == "trail_run":
        zones = activity.hr_zone_times or []

    return float(sum(zones[2:4]))


def _quality_session(activity: Activity) -> bool:
    """A quality session, with race support/warm-ups left out."""
    category = classify(activity)

    return bool(category.quality and category.kind != "race-support")


def _week_starts(race_date: date, weeks: int) -> list[date]:
    race_week = week_start(race_date)
    first = race_week - timedelta(days=7 * (weeks - 1))

    return [first + timedelta(days=7 * index) for index in range(weeks)]


def _actual_weeks(
    activities: list[Activity],
    week_starts: list[date],
) -> list[BuildWeek]:
    buckets: dict[date, list[Activity]] = {
        start: [] for start in week_starts
    }

    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue

        bucket = buckets.get(week_start(activity.date))

        if bucket is not None:
            bucket.append(activity)

    weeks = []

    for index, start in enumerate(week_starts):
        chunk = buckets[start]
        weeks.append(
            BuildWeek(
                label=f"T-{len(week_starts) - 1 - index}",
                week_start=start,
                distance_km=sum(
                    activity.distance_m or 0 for activity in chunk
                ) / 1000,
                time_s=sum(
                    activity.duration_s or 0 for activity in chunk
                ),
                fast_s=sum(_fast_seconds(activity) for activity in chunk),
                quality=sum(
                    1 for activity in chunk if _quality_session(activity)
                ),
                has_data=bool(chunk),
            )
        )

    return weeks


def _planned_maps(
    events: list[Event],
    first: date,
    last: date,
) -> tuple[
    dict[date, float],
    dict[date, float],
    dict[date, float],
    dict[date, int],
]:
    distance = dict(weekly_planned_distance(events, first, last))
    time = dict(weekly_planned_time(events, first, last))
    zones = {
        week.week: sum(week.zones[2:4])
        for week in weekly_planned_time_by_zone(
            events,
            first,
            last,
            kind="pace",
        )
    }
    quality: dict[date, int] = defaultdict(int)

    for event in events:
        if (
            event.type in RUN_TYPES
            and event.quality
            and first <= event.date <= last
        ):
            quality[week_start(event.date)] += 1

    return distance, time, zones, quality


def _with_plan(
    weeks: list[BuildWeek],
    events: list[Event],
    today: date,
) -> list[BuildWeek]:
    """Use planned values on future weeks that have a plan."""
    distance, time, zones, quality = _planned_maps(
        events,
        weeks[0].week_start,
        weeks[-1].week_start + timedelta(days=6),
    )
    planned_weeks = (
        set(distance) | set(time) | set(zones) | set(quality)
    )

    return [
        replace(
            week,
            planned=True,
            planned_distance_km=distance.get(week.week_start),
            planned_time_s=time.get(week.week_start),
            planned_fast_s=zones.get(week.week_start),
            planned_quality=quality.get(week.week_start, 0),
        )
        if week.week_start > today and week.week_start in planned_weeks
        else week
        for week in weeks
    ]


def _is_marathon_event(event: Event) -> bool:
    methods = {method.strip().lower() for method in event.workout_methods}
    targets = {target.strip().lower() for target in event.workout_targets}

    return (
        event.type in RUN_TYPES
        and "race" in methods | targets
        and event.distance_m is not None
        and MARATHON_MIN_M <= event.distance_m <= MARATHON_MAX_M
    )


def _next_marathon(events: list[Event], today: date) -> Event | None:
    upcoming = [
        event
        for event in events
        if event.date > today and _is_marathon_event(event)
    ]

    return min(upcoming, key=lambda event: event.date, default=None)


def marathon_builds(
    activities: list[Activity],
    results: list[RaceResult],
    events: list[Event],
    today: date,
    *,
    weeks: int = MARATHON_WEEKS,
) -> list[MarathonBuild]:
    """One build per marathon result, plus the next planned marathon.

    Completed builds hold actual training only. The upcoming build shows
    actual values for weeks that have started and planned values (from the
    event calendar) for future weeks that carry a plan.
    """
    if weeks <= 0:
        raise ValueError("weeks must be positive")

    builds = []

    for result in sorted(
        (
            result
            for result in results
            if result.bucket == MARATHON_BUCKET
        ),
        key=lambda result: result.activity.date,
    ):
        name = (
            result.official_name
            or result.activity.name.strip()
            or "Marathon"
        )
        builds.append(
            MarathonBuild(
                name=name,
                date=result.activity.date,
                result_s=result.time_s,
                planned=False,
                weeks=_actual_weeks(
                    activities,
                    _week_starts(result.activity.date, weeks),
                ),
            )
        )

    upcoming = _next_marathon(events, today)

    if upcoming is not None:
        name = (upcoming.name or "").strip() or "Marathon"
        starts = _week_starts(upcoming.date, weeks)
        builds.append(
            MarathonBuild(
                name=name,
                date=upcoming.date,
                result_s=None,
                planned=True,
                weeks=_with_plan(
                    _actual_weeks(activities, starts),
                    events,
                    today,
                ),
            )
        )

    return builds
