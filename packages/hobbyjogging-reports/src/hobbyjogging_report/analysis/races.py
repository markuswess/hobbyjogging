"""Race detection, distance buckets, PBs, and Riegel estimates."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core.model import (
    Activity,
    Event,
    Lap,
    RaceResult as OfficialRaceResult,
)

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
PROJECTION_DISTANCES = {
    "5k": 5000.0,
    "7k": 7000.0,
    "10k": 10000.0,
    "15k": 15000.0,
    "HM": 21097.5,
    "30k": 30000.0,
    "M": 42195.0,
}
RAW_BUCKETS = (TRAIL_BUCKET, OTHER_BUCKET)


def bucket_label(bucket: str) -> str:
    """Bucket name, marked raw when it has no standard distance."""
    return f"{bucket} (raw)" if bucket in RAW_BUCKETS else bucket


def is_race(activity: Activity) -> bool:
    """True when the activity carries a race method or target."""
    return "race" in set(activity.workout_methods) | set(
        activity.workout_targets
    )


def race_bucket(activity: Activity, distance_m: float | None = None) -> str:
    """Distance bucket with a tolerance for GPS/shortened courses.

    Trail is decided by the activity type; every other bucket uses
    ``distance_m`` when the caller has an effective distance (the official
    race distance) and the measured activity distance otherwise.
    """
    if activity.type == "trail_run":
        return TRAIL_BUCKET

    km = (activity.distance_m if distance_m is None else distance_m or 0) / 1000

    for name, low, high in RACE_BUCKETS:
        if low <= km <= high:
            return name

    return OTHER_BUCKET


def official_pair(official: OfficialRaceResult | None) -> bool:
    """True when the official result supplies both a distance and a time."""
    return bool(
        official is not None
        and official.official_distance_m
        and official.official_time_s
    )


def official_by_activity(
    results: Iterable[OfficialRaceResult],
) -> dict[str, OfficialRaceResult]:
    """Index official race results by activity for the race analysis."""
    return {result.activity_id: result for result in results}


@dataclass(frozen=True)
class RaceResult:
    """A race activity with the distance, time and placement it is ranked on.

    ``distance_m`` and ``time_s`` are the official pair when the race has
    one, so every consumer (PB, Riegel, tables, charts) ranks the same values.
    ``official`` keeps the row for its placement and the official flags.
    """

    activity: Activity
    bucket: str
    pace_s_per_km: float | None
    distance_m: float
    time_s: float
    official: OfficialRaceResult | None = None

    @property
    def official_used(self) -> bool:
        return official_pair(self.official)

    @property
    def official_name(self) -> str:
        """The race's own title, when the official result carries one."""
        return (self.official.name if self.official else "") or ""

    @property
    def place_overall(self) -> int | None:
        return self.official.place_total if self.official else None

    @property
    def participants_overall(self) -> int | None:
        return self.official.participants_total if self.official else None

    @property
    def place_ageclass(self) -> int | None:
        return self.official.place_ageclass if self.official else None

    @property
    def participants_ageclass(self) -> int | None:
        return self.official.participants_ageclass if self.official else None


def race_results(
    activities: list[Activity],
    official_by_id: Mapping[str, OfficialRaceResult] | None = None,
) -> list[RaceResult]:
    """Race activities newest first, with their bucket and effective values.

    ``official_by_id`` is the activity-keyed official result set. When a row
    carries both an official distance and time, those replace the measured
    activity values for the bucket, PB selection, fit and tables; the measured
    activity remains the identity and the source of HR, load and links.
    """
    official_by_id = official_by_id or {}
    results = []

    for activity in activities:
        if activity.type not in RUN_TYPES or not is_race(activity):
            continue

        official = official_by_id.get(activity.id)
        distance_m = activity.distance_m or 0.0
        time_s = activity.duration_s or 0.0

        if official_pair(official):
            distance_m = official.official_distance_m or 0.0
            time_s = official.official_time_s or 0.0

        results.append(
            RaceResult(
                activity=activity,
                bucket=race_bucket(activity, distance_m),
                pace_s_per_km=pace_s_per_km(time_s, distance_m),
                distance_m=distance_m,
                time_s=time_s,
                official=official,
            )
        )

    return sorted(
        results,
        key=lambda result: result.activity.date,
        reverse=True,
    )


def personal_bests(results: list[RaceResult]) -> list[RaceResult]:
    """Fastest race in each bucket, in bucket order.

    Standard-distance buckets only count races whose effective distance is
    within ``PB_DISTANCE_TOLERANCE`` of the standard, so a 4.2 km measured
    race cannot win the 5k PB unless its official distance is 5k. Trail and
    Other keep the fastest raw time because they have no standard distance.
    """
    best: dict[str, RaceResult] = {}

    for result in results:
        if not _qualifies_for_pb(result):
            continue

        current = best.get(result.bucket)

        if current is None or result.time_s < current.time_s:
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

    return abs(result.distance_m - standard) / standard <= PB_DISTANCE_TOLERANCE


@dataclass(frozen=True)
class PbProgression:
    """Chronological PB improvements for one bucket, and the other races."""

    bucket: str
    steps: tuple[RaceResult, ...]
    others: tuple[RaceResult, ...] = ()


def pb_progressions(results: list[RaceResult]) -> list[PbProgression]:
    """Standard-distance PB improvements per bucket, oldest first.

    Only 5k/10k/HM/M produce a line. Trail and Other have no standard
    distance, so a level there is a distance change, not a PB; their raw
    times stay in the tables. Equal times do not advance a line. Every other
    standard-distance race in the bucket is kept in ``others`` for the chart
    to draw as a hollow dot.
    """
    ordered = sorted(
        (result for result in results if _qualifies_for_pb(result)),
        key=lambda result: (
            result.activity.date,
            result.time_s,
        ),
    )
    best: dict[str, RaceResult] = {}
    steps: dict[str, list[RaceResult]] = {}
    others: dict[str, list[RaceResult]] = {}

    for result in ordered:
        current = best.get(result.bucket)

        if current is None or result.time_s < current.time_s:
            best[result.bucket] = result
            steps.setdefault(result.bucket, []).append(result)
        else:
            others.setdefault(result.bucket, []).append(result)

    return [
        PbProgression(
            bucket,
            tuple(steps[bucket]),
            tuple(others.get(bucket, [])),
        )
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
    r2: float
    points: int


def fit_riegel(results: list[RaceResult]) -> RiegelFit | None:
    """Fit log(time) against log(distance) over the race results."""
    points = [
        result
        for result in results
        if result.distance_m and result.time_s
    ]

    if len(points) < 3:
        return None

    xs = [math.log(result.distance_m / 1000) for result in points]
    ys = [math.log(result.time_s / 60) for result in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

    if sxx == 0:
        return None

    exponent = sxy / sxx
    # Only the R² needs the intercept; the prediction line is anchored on
    # the reference race, not on the free fit.
    intercept = mean_y - exponent * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum(
        (y - (intercept + exponent * x)) ** 2
        for x, y in zip(xs, ys)
    )
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0

    return RiegelFit(
        exponent=exponent,
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
    return reference.time_s * (
        distance_m / reference.distance_m
    ) ** fit.exponent


RIEGEL_EXPONENT = 1.06


def riegel_pace_at_duration(
    distance_m: float,
    time_s: float,
    duration_s: float = 3600.0,
    *,
    exponent: float = RIEGEL_EXPONENT,
) -> float | None:
    """Pace (s/km) at a target duration, scaled from one race by Riegel.

    The distance that takes ``duration_s`` at the race's effort is
    ``d * (duration_s / time_s) ** (1 / exponent)``; the returned pace is
    that duration divided by it.
    """
    if distance_m <= 0 or time_s <= 0 or duration_s <= 0:
        return None

    equivalent_distance = distance_m * (
        duration_s / time_s
    ) ** (1 / exponent)

    return duration_s / equivalent_distance * 1000


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


@dataclass(frozen=True)
class EquivalentTime:
    """One projected distance: the Riegel time, its PB, and both paces."""

    label: str
    distance_m: float
    predicted_s: float
    pb_s: float | None = None
    pb_distance_m: float | None = None

    @property
    def predicted_pace_s_per_km(self) -> float | None:
        return pace_s_per_km(self.predicted_s, self.distance_m)

    @property
    def pb_pace_s_per_km(self) -> float | None:
        if self.pb_s is None or self.pb_distance_m is None:
            return None

        return pace_s_per_km(self.pb_s, self.pb_distance_m)


def equivalent_times(
    results: list[RaceResult],
    fit: RiegelFit | None,
) -> list[EquivalentTime]:
    """Projected times from 5k to marathon, plus the current PB at each.

    7k, 15k and 30k have no PB bucket, so they carry a prediction only. The
    predictions scale :func:`riegel_reference` by the fitted exponent; the
    PB column is all-time.
    """
    race = riegel_reference(results)

    if race is None or fit is None:
        return []

    pbs = {result.bucket: result for result in personal_bests(results)}
    rows = []

    for label, distance_m in PROJECTION_DISTANCES.items():
        pb = pbs.get(label)
        rows.append(
            EquivalentTime(
                label=label,
                distance_m=distance_m,
                predicted_s=riegel_time(race, fit, distance_m),
                pb_s=pb.time_s if pb else None,
                pb_distance_m=pb.distance_m if pb else None,
            )
        )

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
