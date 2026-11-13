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
STANDARD_DISTANCES = {
    "5k": 5000.0,
    "10k": 10000.0,
    "HM": 21097.5,
    "M": 42195.0,
}


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


@dataclass(frozen=True)
class RaceFilter:
    """Bucket, date, and row-limit filters for race reports."""

    bucket: str | None = None
    start: date | None = None
    end: date | None = None
    limit: int | None = None

    def filter_results(self, results: list[RaceResult]) -> list[RaceResult]:
        return [
            result
            for result in results
            if (self.bucket is None or result.bucket == self.bucket)
            and (self.start is None or result.activity.date >= self.start)
            and (self.end is None or result.activity.date <= self.end)
        ]

    def shown(self, results: list[RaceResult]) -> list[RaceResult]:
        """The rows to print; PBs and the fit still use every match."""
        return results if self.limit is None else results[:self.limit]

    def filter_upcoming(self, events: list[Event]) -> list[Event]:
        """Date filters scope upcoming races; bucket and limit never do."""
        if self.start is None and self.end is None:
            return events

        return [
            event
            for event in events
            if (self.start is None or event.date >= self.start)
            and (self.end is None or event.date <= self.end)
        ]

    def summary(self) -> str:
        parts = []

        if self.bucket is not None:
            parts.append(f"bucket {self.bucket}")
        if self.start is not None and self.end is not None:
            parts.append(f"{self.start} → {self.end}")
        elif self.start is not None:
            parts.append(f"from {self.start}")
        elif self.end is not None:
            parts.append(f"through {self.end}")
        if self.limit is not None:
            parts.append(f"latest {self.limit}")

        return " · ".join(parts)


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
    """Fastest race in each bucket, in bucket order."""
    best: dict[str, RaceResult] = {}

    for result in results:
        current = best.get(result.bucket)

        if current is None or result.activity.duration_s < current.activity.duration_s:
            best[result.bucket] = result

    return [
        best[bucket]
        for bucket in BUCKET_ORDER
        if bucket in best
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

    def duration_s(self, distance_m: float) -> float:
        return 60 * math.exp(
            self.intercept + self.exponent * math.log(distance_m / 1000)
        )


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


def equivalent_times(
    results: list[RaceResult],
    fit: RiegelFit | None,
) -> list[tuple[str, float, float | None]]:
    """Predicted standard-distance times plus the current PB in each bucket.

    The reference is the most recent road 10k, falling back to the most
    recent road race. Trail results are not used as the reference.
    """
    race = next(
        (
            result
            for result in results
            if result.bucket == "10k"
        ),
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

    if race is None or fit is None:
        return []

    reference = race.activity
    rows = []

    for label, distance_m in STANDARD_DISTANCES.items():
        predicted = reference.duration_s * (
            distance_m / reference.distance_m
        ) ** fit.exponent
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
