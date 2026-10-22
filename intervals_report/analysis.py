"""Source-agnostic analysis.

Functions here take model objects (see ``model.py``) and return plain Python
structures. They never touch the API, a database, or plotting.
"""

from collections import defaultdict
from datetime import date, timedelta

from .model import Activity, Interval, SubtPoint

RUN_TYPES = {"run", "trail_run"}

CATEGORY_SHORT = "short"
CATEGORY_MEDIUM = "medium"
CATEGORY_LONG = "long"
SUBT_CATEGORIES = (CATEGORY_SHORT, CATEGORY_MEDIUM, CATEGORY_LONG)

# Average rep duration thresholds (seconds), matching the report logic.
SHORT_MAX_S = 240
MEDIUM_MAX_S = 350


def week_start(d: date) -> date:
    """Monday of the week containing ``d``."""
    return d - timedelta(days=d.weekday())


def weekly_run_distance(activities: list[Activity]) -> list[tuple[date, float]]:
    """Run distance (km) per week, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for a in activities:
        if a.type in RUN_TYPES:
            totals[week_start(a.date)] += a.distance_m

    return [(week, totals[week] / 1000) for week in sorted(totals)]


def weekly_training_load(activities: list[Activity]) -> list[tuple[date, float]]:
    """Total training load per week, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for a in activities:
        if a.training_load:
            totals[week_start(a.date)] += a.training_load

    return [(week, totals[week]) for week in sorted(totals)]


def is_subt_activity(a: Activity) -> bool:
    """True if the activity looks like a subT workout."""
    return "subt" in f"{a.name} {a.description}".lower()


def classify_interval(duration_s: float) -> str:
    """Classify an interval by its (average rep) duration."""
    if duration_s <= SHORT_MAX_S:
        return CATEGORY_SHORT
    if duration_s <= MEDIUM_MAX_S:
        return CATEGORY_MEDIUM
    return CATEGORY_LONG


def pace_s_per_km(duration_s: float, distance_m: float) -> float | None:
    """Average pace in seconds per km."""
    if duration_s <= 0 or distance_m <= 0:
        return None
    return duration_s / distance_m * 1000


def subt_work_points(
    activity: Activity,
    intervals: list[Interval],
) -> list[SubtPoint]:
    """One point per WORK interval group (set of reps) in an activity."""
    work = [
        i for i in intervals
        if i.type == "WORK" and i.duration_s and i.distance_m
    ]

    groups: dict[str, list[Interval]] = {}

    for index, interval in enumerate(work):
        key = interval.group_id or f"interval-{index}"
        groups.setdefault(key, []).append(interval)

    points = []

    for group in groups.values():
        total_time = sum(i.duration_s for i in group)
        total_distance = sum(i.distance_m for i in group)

        pace = pace_s_per_km(total_time, total_distance)
        if pace is None:
            continue

        # Time-weighted average heart rate.
        hr_pairs = [
            (i.avg_hr, i.duration_s)
            for i in group
            if i.avg_hr is not None
        ]

        avg_hr = None
        if hr_pairs:
            avg_hr = (
                sum(hr * t for hr, t in hr_pairs)
                / sum(t for _, t in hr_pairs)
            )

        points.append(SubtPoint(
            date=activity.date,
            category=classify_interval(total_time / len(group)),
            pace_s_per_km=pace,
            count=len(group),
            avg_hr=avg_hr,
        ))

    return points
