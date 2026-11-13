"""Race detection, distance buckets, PBs, and Riegel estimates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core.model import Activity, Event, Lap

from .common import RUN_TYPES, pace_s_per_km

RACE_BUCKETS = (
    ("5k", 4.0, 6.2),
    ("10k", 9.5, 10.7),
    ("HM", 19.0, 23.0),
    ("M", 40.0, 44.5),
)
OTHER_BUCKET = "Other"
TRAIL_BUCKET = "Trail"
BUCKET_ORDER = ("5k", "10k", "HM", "M", TRAIL_BUCKET, OTHER_BUCKET)
PB_DISTANCE_TOLERANCE = 0.02
STANDARD_DISTANCES = {
    "5k": 5000.0,
    "10k": 10000.0,
    "HM": 21097.5,
    "M": 42195.0,
}
STANDARD_BUCKETS = tuple(STANDARD_DISTANCES)
RAW_BUCKETS = (TRAIL_BUCKET, OTHER_BUCKET)


def bucket_label(bucket: str) -> str:
    """Bucket name, marked raw when it has no standard distance."""
    return f"{bucket} (raw)" if bucket in RAW_BUCKETS else bucket


def is_race(activity: Activity) -> bool:
    """True when the activity carries a race method or target."""
    return "race" in set(activity.workout_methods) | set(
        activity.workout_targets
    )


def race_bucket(activity: Activity) -> str:
    """Distance bucket with a tolerance for GPS/shortened courses."""
    if activity.type == "trail_run":
        return TRAIL_BUCKET

    km = (activity.distance_m or 0) / 1000

    for name, low, high in RACE_BUCKETS:
        if low <= km <= high:
            return name

    return OTHER_BUCKET


@dataclass(frozen=True)
class RaceResult:
    activity: Activity
    bucket: str
    pace_s_per_km: float | None


def race_results(activities: list[Activity]) -> list[RaceResult]:
    """Race activities newest first, with their bucket and pace."""
    results = [
        RaceResult(
            activity=activity,
            bucket=race_bucket(activity),
            pace_s_per_km=pace_s_per_km(
                activity.duration_s,
                activity.distance_m,
            ),
        )
        for activity in activities
        if activity.type in RUN_TYPES and is_race(activity)
    ]

    return sorted(
        results,
        key=lambda result: result.activity.date,
        reverse=True,
    )


def personal_bests(results: list[RaceResult]) -> list[RaceResult]:
    """Fastest race in each bucket, in bucket order.

    Standard-distance buckets only count races whose measured distance is
    within ``PB_DISTANCE_TOLERANCE`` of the standard, so a 4.2 km race cannot
    win the 5k PB. Trail and Other keep the fastest raw time because they have
    no standard distance.
    """
    best: dict[str, RaceResult] = {}

    for result in results:
        if not _qualifies_for_pb(result):
            continue

        current = best.get(result.bucket)

        if current is None or result.activity.duration_s < current.activity.duration_s:
            best[result.bucket] = result

    return [
        best[bucket]
        for bucket in BUCKET_ORDER
        if bucket in best
    ]


def _qualifies_for_pb(result: RaceResult) -> bool:
    standard = STANDARD_DISTANCES.get(result.bucket)

    if standard is None:
        return True

    distance = result.activity.distance_m or 0

    return abs(distance - standard) / standard <= PB_DISTANCE_TOLERANCE


@dataclass(frozen=True)
class PbProgression:
    """Chronological PB improvements for one bucket."""

    bucket: str
    steps: tuple[RaceResult, ...]


def pb_progressions(results: list[RaceResult]) -> list[PbProgression]:
    """Standard-distance PB improvements per bucket, oldest first.

    Only 5k/10k/HM/M produce a line. Trail and Other have no standard
    distance, so a step there is a distance change, not a PB; their raw
    times stay in the tables. Equal times do not advance a line.
    """
    ordered = sorted(
        (result for result in results if _qualifies_for_pb(result)),
        key=lambda result: (
            result.activity.date,
            result.activity.duration_s,
        ),
    )
    best: dict[str, RaceResult] = {}
    steps: dict[str, list[RaceResult]] = {}

    for result in ordered:
        current = best.get(result.bucket)

        if (
            current is None
            or result.activity.duration_s < current.activity.duration_s
        ):
            best[result.bucket] = result
            steps.setdefault(result.bucket, []).append(result)

    return [
        PbProgression(bucket, tuple(steps[bucket]))
        for bucket in STANDARD_BUCKETS
        if bucket in steps
    ]


def upcoming_races(
    events: list[Event],
    today: date,
    *,
    days: int = 180,
) -> list[Event]:
    """Race events from today through the horizon."""
    horizon = today + timedelta(days=days)

    return sorted(
        [
            event
            for event in events
            if today <= event.date <= horizon
            and "race" in set(event.workout_methods)
            | set(event.workout_targets)
        ],
        key=lambda event: event.date,
    )


@dataclass(frozen=True)
class RiegelFit:
    """Log-log duration fit: time grows as distance ** exponent."""

    exponent: float
    intercept: float
    r2: float
    points: int


def fit_riegel(results: list[RaceResult]) -> RiegelFit | None:
    """Fit log(time) against log(distance) over the race results."""
    points = [
        result
        for result in results
        if result.activity.distance_m and result.activity.duration_s
    ]

    if len(points) < 3:
        return None

    xs = [math.log(result.activity.distance_m / 1000) for result in points]
    ys = [math.log(result.activity.duration_s / 60) for result in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

    if sxx == 0:
        return None

    exponent = sxy / sxx
    intercept = mean_y - exponent * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum(
        (y - (intercept + exponent * x)) ** 2
        for x, y in zip(xs, ys)
    )
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0

    return RiegelFit(
        exponent=exponent,
        intercept=intercept,
        r2=r2,
        points=len(points),
    )


def riegel_time(
    reference: RaceResult,
    fit: RiegelFit,
    distance_m: float,
) -> float:
    """Predicted time at a distance, anchored on the reference race.

    This is the line the equivalent times and the race chart share: it always
    passes through the reference result, which a free least-squares line does
    not.
    """
    activity = reference.activity

    return activity.duration_s * (
        distance_m / activity.distance_m
    ) ** fit.exponent


def riegel_reference(results: list[RaceResult]) -> RaceResult | None:
    """The race the predictions and their line are anchored to.

    The most recent road 10k, falling back to the most recent road race.
    Trail results are not used as the reference.
    """
    race = next(
        (result for result in results if result.bucket == "10k"),
        None,
    )

    if race is None:
        race = next(
            (
                result
                for result in results
                if result.bucket not in (TRAIL_BUCKET, OTHER_BUCKET)
            ),
            None,
        )

    return race


def equivalent_times(
    results: list[RaceResult],
    fit: RiegelFit | None,
) -> list[tuple[str, float, float | None]]:
    """Predicted standard-distance times plus the current PB in each bucket.

    The predictions scale :func:`riegel_reference` by the fitted exponent;
    the PB column is all-time.
    """
    race = riegel_reference(results)

    if race is None or fit is None:
        return []

    rows = []

    for label, distance_m in STANDARD_DISTANCES.items():
        predicted = riegel_time(race, fit, distance_m)
        pb = next(
            (
                result.activity.duration_s
                for result in personal_bests(results)
                if result.bucket == label
            ),
            None,
        )
        rows.append((label, predicted, pb))

    return rows


@dataclass(frozen=True)
class HalfSplit:
    """First- and second-half pace from device laps."""

    first_pace_s_per_km: float | None
    second_pace_s_per_km: float | None

    @property
    def delta_s_per_km(self) -> float | None:
        if (
            self.first_pace_s_per_km is None
            or self.second_pace_s_per_km is None
        ):
            return None
        return self.second_pace_s_per_km - self.first_pace_s_per_km


def half_split(laps: list[Lap]) -> HalfSplit | None:
    """Pace for the first and second half of the lap distance."""
    usable = [
        lap for lap in laps
        if lap.distance_m > 0 and lap.duration_s > 0
    ]

    if len(usable) < 2:
        return None

    total_distance = sum(lap.distance_m for lap in usable)
    total_time = sum(lap.duration_s for lap in usable)
    midpoint = total_distance / 2
    covered = 0.0
    first_time = 0.0

    for lap in usable:
        if covered + lap.distance_m <= midpoint:
            first_time += lap.duration_s
            covered += lap.distance_m
            continue

        remaining = midpoint - covered
        first_time += lap.duration_s * remaining / lap.distance_m
        break

    first_pace = pace_s_per_km(first_time, midpoint)
    second_pace = pace_s_per_km(
        total_time - first_time,
        total_distance - midpoint,
    )

    return HalfSplit(first_pace, second_pace)
