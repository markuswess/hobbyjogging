"""Running streaks: consecutive calendar days with a qualifying run.

A streak day needs one running activity of at least ``MIN_STREAK_RUN_S``. The
minimum keeps a token shuffle from holding a streak; rides never count, so a
cross-training day breaks the run streak like a rest day does. Two runs on one
day are one day, with both added to the streak's distance and time.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core.model import Activity

from .common import RUN_TYPES

MIN_STREAK_RUN_S = 10 * 60
DEFAULT_STREAK_LIMIT = 10


@dataclass(frozen=True)
class RunStreak:
    """One run of consecutive days with a qualifying run, oldest first."""

    start: date
    end: date
    days: int
    distance_m: float
    duration_s: float


@dataclass(frozen=True)
class StreakSummary:
    """The current streak, the longest ones, and the history behind them."""

    current: RunStreak | None
    today_run: bool
    longest: tuple[RunStreak, ...]
    last_run: date | None
    run_days: int
    streak_count: int
    current_rank: int | None = None


def is_streak_run(
    activity: Activity,
    *,
    min_duration_s: float = MIN_STREAK_RUN_S,
) -> bool:
    """True when a run is long enough to hold a streak day."""
    return (
        activity.type in RUN_TYPES
        and (activity.duration_s or 0) >= min_duration_s
    )


def _streak(
    start: date,
    end: date,
    distance_m: float,
    duration_s: float,
) -> RunStreak:
    return RunStreak(
        start=start,
        end=end,
        days=(end - start).days + 1,
        distance_m=distance_m,
        duration_s=duration_s,
    )


def run_streaks(
    activities: Iterable[Activity],
    *,
    min_duration_s: float = MIN_STREAK_RUN_S,
) -> list[RunStreak]:
    """Consecutive-day streaks over the activities, oldest first."""
    days: dict[date, tuple[float, float]] = {}

    for activity in activities:
        if not is_streak_run(activity, min_duration_s=min_duration_s):
            continue

        distance, duration = days.get(activity.date, (0.0, 0.0))
        days[activity.date] = (
            distance + (activity.distance_m or 0),
            duration + (activity.duration_s or 0),
        )

    streaks: list[RunStreak] = []
    start: date | None = None
    previous: date | None = None
    distance = 0.0
    duration = 0.0

    for day in sorted(days):
        day_distance, day_duration = days[day]

        if start is None:
            start = day
        elif (day - previous).days > 1:
            streaks.append(_streak(start, previous, distance, duration))
            start = day
            distance = 0.0
            duration = 0.0

        distance += day_distance
        duration += day_duration
        previous = day

    if start is not None and previous is not None:
        streaks.append(_streak(start, previous, distance, duration))

    return streaks


def streak_summary(
    activities: Iterable[Activity],
    today: date,
    *,
    limit: int | None = DEFAULT_STREAK_LIMIT,
    min_duration_s: float = MIN_STREAK_RUN_S,
) -> StreakSummary:
    """Current streak, the longest ones, and the run days behind them.

    The current streak ends today, or yesterday when today has no run yet;
    older runs leave no current streak. ``limit`` cuts only the longest list.
    """
    activities = list(activities)
    streaks = run_streaks(activities, min_duration_s=min_duration_s)
    run_days = sorted(
        {
            activity.date
            for activity in activities
            if is_streak_run(activity, min_duration_s=min_duration_s)
        }
    )
    last_run = run_days[-1] if run_days else None
    today_run = last_run == today
    current = None

    ongoing = (today, today - timedelta(days=1))

    if streaks and streaks[-1].end in ongoing:
        current = streaks[-1]

    ranked = sorted(
        streaks,
        key=lambda streak: (streak.days, streak.distance_m, streak.start),
        reverse=True,
    )
    current_rank = None

    if current is not None:
        for rank, streak in enumerate(ranked, start=1):
            if (streak.start, streak.end) == (current.start, current.end):
                current_rank = rank
                break

    longest = ranked if limit is None else ranked[:limit]

    return StreakSummary(
        current=current,
        today_run=today_run,
        longest=tuple(longest),
        last_run=last_run,
        run_days=len(run_days),
        streak_count=len(streaks),
        current_rank=current_rank,
    )


@dataclass(frozen=True)
class StreakTableRow:
    """One table row: a streak, or an ellipsis separator (streak None).

    ``rank`` is the position in the longest list (1 is the best). The
    ellipsis and a current streak appended below the cut have no rank.
    """

    streak: RunStreak | None
    current: bool = False
    rank: int | None = None


def streak_table_rows(summary: StreakSummary) -> list[StreakTableRow]:
    """Longest streaks with the current one always in the table.

    The longest list is numbered from 1. The current streak is marked even
    when it sits outside the cut; in that case an ellipsis row separates it
    from the listed streaks and the appended row carries no rank.
    """
    rows = []
    current_in_table = False

    for rank, streak in enumerate(summary.longest, start=1):
        is_current = summary.current is not None and (
            (streak.start, streak.end)
            == (summary.current.start, summary.current.end)
        )
        current_in_table = current_in_table or is_current
        rows.append(StreakTableRow(streak, is_current, rank))

    if summary.current is not None and not current_in_table:
        rows.append(StreakTableRow(None))
        rows.append(
            StreakTableRow(
                summary.current,
                True,
                summary.current_rank,
            )
        )

    return rows
