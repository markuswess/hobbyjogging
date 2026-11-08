"""Shared analysis helpers: dates, activity classes, work reps, event zones."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from hobbyjogging_core.model import Activity, Event, Interval
from hobbyjogging_core.sports import RUN_SPORTS

RUN_TYPES = RUN_SPORTS

CATEGORY_SHORT = "short"
CATEGORY_MEDIUM = "medium"
CATEGORY_LONG = "long"
SUBT_CATEGORIES = (CATEGORY_SHORT, CATEGORY_MEDIUM, CATEGORY_LONG)

LT1_WORDS = ("lt1", "lt 1")

# Average rep duration thresholds (seconds), matching the report logic.
SHORT_MAX_S = 240
MEDIUM_MAX_S = 420

SUBT_CATEGORY_ORDER = (*SUBT_CATEGORIES, "lt1")

DEFAULT_ZONE_COUNT = 4

# Work interval filtering. Older Intervals.icu activities mark warm-up,
# cool-down and recovery jogs as WORK; work reps form the fast pace cluster.
WORK_MIN_DURATION_S = 60
WORK_MIN_DISTANCE_M = 100
WORK_PACE_BAND = 1.20
WORK_MIN_HR_SHARE = 0.85
WORK_SLOW_PACE_BAND = 1.10


def activity_sort_key(activity: Activity) -> tuple[date, str]:
    """Order activities chronologically, including same-day sessions."""
    return (activity.date, activity.started_at_utc)


def week_start(d: date) -> date:
    """Monday of the week containing ``d``."""
    return d - timedelta(days=d.weekday())


def week_end(d: date) -> date:
    """Sunday of the week containing ``d``."""
    return week_start(d) + timedelta(days=6)


def week_bounds(start: date, end: date) -> tuple[date, date]:
    """Expand a date range to whole Monday–Sunday weeks."""
    return week_start(start), week_end(end)


def _planned_events(
    events: list[Event],
    start: date,
    end: date,
    *,
    running_only: bool = False,
):
    """Yield planned events in range, skipping undated notes without a sport."""
    for event in events:
        if not (start <= event.date <= end):
            continue
        if not event.type:
            continue
        if running_only and event.type not in RUN_TYPES:
            continue
        yield event


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


def _event_zone_index(zone) -> int | None:
    """Return an event zone's 1-based index, or ``None`` for ``SS``."""
    index = zone.zone_index

    if index is not None:
        return index

    label = (zone.zone_label or "").strip().upper()

    if not label.startswith("Z"):
        return None

    try:
        return int(label[1:])
    except ValueError:
        return None


def event_zone_seconds(
    event: Event,
    zone_count: int = DEFAULT_ZONE_COUNT,
) -> list[float] | None:
    """Normalize an event's planned zone times to ``zone_count`` buckets.

    Zones past ``zone_count`` fold into the last bucket so planned totals are
    preserved. ``SS`` and unparseable labels are ignored. Returns ``None``
    when the event has no usable zone times.
    """
    if zone_count <= 0:
        raise ValueError("zone_count must be positive")

    if not event.zone_times:
        return None

    result = [0.0] * zone_count
    found = False

    for zone in event.zone_times:
        index = _event_zone_index(zone)

        if index is None or index < 1 or (zone.seconds or 0) <= 0:
            continue

        result[min(index, zone_count) - 1] += zone.seconds
        found = True

    return result if found else None


def event_zone_time(
    event: Event,
    zone_indices: tuple[int, ...],
) -> float | None:
    """Sum planned seconds in the given 1-based zones.

    ``SS`` and unparseable labels are ignored. Returns ``None`` when the
    event has no usable zone times; otherwise returns the sum, which may be
    zero when the requested zones are empty.
    """
    if not event.zone_times:
        return None

    wanted = set(zone_indices)
    total = 0.0
    found = False

    for zone in event.zone_times:
        index = _event_zone_index(zone)

        if index is None or index < 1 or (zone.seconds or 0) <= 0:
            continue

        found = True

        if index in wanted:
            total += zone.seconds

    return total if found else None
