"""Shared helpers for CLI command handlers."""

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import Activity

from .review import exclude_review, review_note


def print_review_note(excluded: int) -> None:
    note = review_note(excluded)
    if note:
        print(f"note: {note}")


def print_count_note(
    count: int,
    singular: str,
    plural: str,
    message: str,
) -> None:
    if not count:
        return

    unit = singular if count == 1 else plural
    verb = "has" if count == 1 else "have"

    print(f"note: {count} {unit} {verb} {message}")


def reviewed_range(
    source: DataSource,
    start: date,
    end: date,
    include_review: bool,
) -> list[Activity]:
    """Return reviewed activities in range and print the review note."""
    activities, excluded = exclude_review(
        source.activities(start, end),
        include_review=include_review,
    )
    print_review_note(excluded)
    return activities


def warmup_reviewed(
    source: DataSource,
    start: date,
    end: date,
    warmup_days: int,
    include_review: bool,
) -> tuple[list[Activity], list[Activity]]:
    """Return display activities and the reviewed warm-up history."""
    warm_start = start - timedelta(days=warmup_days)
    all_activities = source.activities(warm_start, end)

    display, excluded = exclude_review(
        [
            activity
            for activity in all_activities
            if start <= activity.date <= end
        ],
        include_review=include_review,
    )
    print_review_note(excluded)

    activities, _ = exclude_review(
        all_activities,
        include_review=include_review,
    )

    return display, activities


def subt_session_points(
    source: DataSource,
    activities: list[Activity],
):
    """Collect subT/LT1 work points from activities, oldest first."""
    from .analysis import (
        activity_sort_key,
        is_lt1_activity,
        is_subt_activity,
        subt_session_point,
    )

    points = []

    for activity in sorted(activities, key=activity_sort_key):
        if is_lt1_activity(activity):
            category = "lt1"
        elif is_subt_activity(activity):
            category = None
        else:
            continue

        point = subt_session_point(
            activity,
            source.activity_intervals(activity.id),
            category=category,
        )

        if point is not None:
            points.append(point)

    return points
