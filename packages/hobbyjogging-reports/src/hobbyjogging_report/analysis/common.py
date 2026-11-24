"""Shared analysis helpers: dates, activity classes, work reps, event zones."""

from __future__ import annotations

from datetime import date, timedelta

from hobbyjogging_core.classify import (
    CATEGORY_LONG,
    CATEGORY_MEDIUM,
    CATEGORY_SHORT,
    LT1_WORDS,
    SUBT_CATEGORIES,
    classify_interval,
    work_intervals,
)
from hobbyjogging_core.model import Activity, Event, Interval
from hobbyjogging_core.sports import RUN_SPORTS

RUN_TYPES = RUN_SPORTS

SUBT_CATEGORY_ORDER = (*SUBT_CATEGORIES, "lt1")

DEFAULT_ZONE_COUNT = 4


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


def _is_fartlek(activity: Activity) -> bool:
    """A stored fartlek method marks unstructured quality, not reps."""
    return any(
        method.strip().lower() == "fartlek"
        for method in activity.workout_methods
    )


def _targets(activity: Activity) -> set[str]:
    """The session's stored workout targets, lower-cased."""
    return {
        target.strip().lower()
        for target in activity.workout_targets
    }


def is_subt_activity(a: Activity) -> bool:
    """True if the session is a subT workout.

    A stored ``subthreshold`` target wins over the name, so a Runalyze-only
    athlete without session names still reaches the subT report and work reps.
    A stored ``lt1`` target excludes it, and a stored fartlek never belongs in
    the subT buckets. Without a relevant target the name is the fallback, and
    only the name is used for that: descriptions often mention alternatives
    ("did 3x10@LT1 instead of subT") and would pull LT1 sessions in.
    """
    if _is_fartlek(a):
        return False

    targets = _targets(a)

    if "lt1" in targets:
        return False
    if "subthreshold" in targets:
        return True

    return "subt" in a.name.lower()


def is_lt1_activity(a: Activity) -> bool:
    """True if the session is an LT1 workout.

    A stored ``lt1`` target wins over the name; a stored ``subthreshold``
    target excludes it; otherwise the name is the fallback, as above.
    """
    if _is_fartlek(a):
        return False

    targets = _targets(a)

    if "lt1" in targets:
        return True
    if "subthreshold" in targets:
        return False

    text = a.name.lower()
    return any(word in text for word in LT1_WORDS)


def pace_s_per_km(duration_s: float, distance_m: float) -> float | None:
    """Average pace in seconds per km."""
    if duration_s <= 0 or distance_m <= 0:
        return None
    return duration_s / distance_m * 1000


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
