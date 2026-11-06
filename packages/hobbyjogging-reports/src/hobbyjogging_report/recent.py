"""Widening-lookback search shared by session and activity selection."""

from datetime import date, timedelta
from typing import Callable

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import Activity

from .review import exclude_review

SESSION_LOOKBACK_STEPS = (30, 90, 365, 1825, 7300)


def search_recent(
    source: DataSource,
    *,
    include_review: bool = False,
    today: date | None = None,
    enough: Callable[[list[Activity]], bool],
) -> tuple[list[Activity], int]:
    """Search widening windows until ``enough`` holds.

    Windows are ``SESSION_LOOKBACK_STEPS`` days back from ``today``. The
    returned activities and excluded count come from the window that
    satisfied ``enough``, or from the last window searched.
    """
    today = today or date.today()

    activities: list[Activity] = []
    excluded = 0

    for days in SESSION_LOOKBACK_STEPS:
        activities, excluded = exclude_review(
            source.activities(today - timedelta(days=days), today),
            include_review=include_review,
        )

        if enough(activities):
            break

    return activities, excluded
