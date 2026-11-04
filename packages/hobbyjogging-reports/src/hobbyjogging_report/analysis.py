"""Source-agnostic analysis.

Functions here take model objects (see ``hobbyjogging_core.model``) and return
plain Python structures. They never touch the API, a database, or plotting.
"""

from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from hobbyjogging_core.model import Activity, Interval

from .model import SubtPoint

RUN_TYPES = {"run", "trail_run"}

CATEGORY_SHORT = "short"
CATEGORY_MEDIUM = "medium"
CATEGORY_LONG = "long"
SUBT_CATEGORIES = (CATEGORY_SHORT, CATEGORY_MEDIUM, CATEGORY_LONG)

LT1_WORDS = ("lt1", "lt 1")

# Average rep duration thresholds (seconds), matching the report logic.
SHORT_MAX_S = 240
MEDIUM_MAX_S = 420

# Work interval filtering. Older Intervals.icu activities mark warm-up,
# cool-down and recovery jogs as WORK; work reps form the fast pace cluster.
WORK_MIN_DURATION_S = 60


def activity_sort_key(activity: Activity) -> tuple[date, str]:
    """Order activities chronologically, including same-day sessions."""
    return (activity.date, activity.started_at_utc)
WORK_MIN_DISTANCE_M = 100
WORK_PACE_BAND = 1.20
WORK_MIN_HR_SHARE = 0.85
WORK_SLOW_PACE_BAND = 1.10


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
    """True if the name marks the session as a subT workout.

    Only the name is used: descriptions often mention alternatives
    ("did 3x10@LT1 instead of subT") and would pull LT1 sessions in.
    """
    return "subt" in a.name.lower()


def is_lt1_activity(a: Activity) -> bool:
    """True if the name marks the session as an LT1 workout."""
    text = a.name.lower()
    return any(word in text for word in LT1_WORDS)


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


def work_intervals(intervals: list[Interval]) -> list[Interval]:
    """Return the intervals that are actual work reps.

    Older Intervals.icu data labels warm-up, cool-down and recovery jogs as
    WORK as well. Work reps are the fast pace cluster; everything else is
    slower. Strides and GPS artifacts are ignored. When there is not enough
    pace data to separate the clusters, all WORK intervals are returned.
    """
    work = [
        i for i in intervals
        if i.type == "WORK" and i.duration_s > 0
    ]

    paced = [
        i for i in work
        if i.duration_s >= WORK_MIN_DURATION_S
        and i.distance_m >= WORK_MIN_DISTANCE_M
    ]

    if len(paced) < 3:
        return work

    def pace(i: Interval) -> float:
        return i.duration_s / i.distance_m * 1000

    ordered = sorted(paced, key=pace)

    # Use the fastest third as the reference so a single flier cannot pull
    # the band down, while recovery jogs cannot pull it up.
    fastest = ordered[:max(1, len(ordered) // 3)]
    reference = median(pace(i) for i in fastest)

    reps = [
        i for i in paced
        if pace(i) <= reference * WORK_PACE_BAND
    ]

    if not reps:
        return work

    # Warm-ups can sit just inside the pace band, but their heart rate is
    # still clearly below the work reps. Only drop slow, low-HR intervals so
    # short reps with heart-rate lag are kept.
    hrs = [i.avg_hr for i in reps if i.avg_hr is not None]

    if not hrs:
        return reps

    median_pace = median(pace(i) for i in reps)
    min_hr = max(hrs) * WORK_MIN_HR_SHARE

    filtered = [
        i for i in reps
        if not (
            i.avg_hr is not None
            and i.avg_hr < min_hr
            and pace(i) > median_pace * WORK_SLOW_PACE_BAND
        )
    ]

    return filtered or reps


def _subt_point(
    activity: Activity,
    intervals: list[Interval],
    category: str | None = None,
) -> SubtPoint | None:
    """Aggregate a list of work reps into one pace point."""
    total_time = sum(i.duration_s for i in intervals)
    total_distance = sum(i.distance_m for i in intervals)

    pace = pace_s_per_km(total_time, total_distance)
    if pace is None:
        return None

    # Time-weighted average heart rate.
    hr_pairs = [
        (i.avg_hr, i.duration_s)
        for i in intervals
        if i.avg_hr is not None
    ]

    avg_hr = None
    if hr_pairs:
        avg_hr = (
            sum(hr * t for hr, t in hr_pairs)
            / sum(t for _, t in hr_pairs)
        )

    max_hr = max(
        (i.max_hr for i in intervals if i.max_hr is not None),
        default=None,
    )

    rep_paces = []
    for interval in intervals:
        rep_pace = pace_s_per_km(interval.duration_s, interval.distance_m)
        if rep_pace is not None:
            rep_paces.append(rep_pace)

    return SubtPoint(
        date=activity.date,
        category=category or classify_interval(total_time / len(intervals)),
        pace_s_per_km=pace,
        count=len(intervals),
        avg_hr=avg_hr,
        max_hr=max_hr,
        avg_rep_s=total_time / len(intervals),
        fastest_pace_s_per_km=min(rep_paces) if rep_paces else None,
        slowest_pace_s_per_km=max(rep_paces) if rep_paces else None,
    )


def _paced_work(intervals: list[Interval]) -> list[Interval]:
    return [
        i for i in work_intervals(intervals)
        if i.duration_s and i.distance_m
    ]


def subt_work_points(
    activity: Activity,
    intervals: list[Interval],
) -> list[SubtPoint]:
    """One point per WORK interval group (set of reps) in an activity."""
    work = _paced_work(intervals)

    groups: dict[str, list[Interval]] = {}

    for index, interval in enumerate(work):
        key = interval.group_id or f"interval-{index}"
        groups.setdefault(key, []).append(interval)

    points = []

    for group in groups.values():
        point = _subt_point(activity, group)
        if point is not None:
            points.append(point)

    return points


def subt_session_point(
    activity: Activity,
    intervals: list[Interval],
    category: str | None = None,
) -> SubtPoint | None:
    """One point per activity, aggregating all of its work reps.

    ``category`` can override the rep-length category, e.g. for LT1.
    """
    work = _paced_work(intervals)

    if not work:
        return None

    return _subt_point(activity, work, category=category)
