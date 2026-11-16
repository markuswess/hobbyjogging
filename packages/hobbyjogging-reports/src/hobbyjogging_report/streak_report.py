"""Running-streak report: the current streak and the longest ones."""

from __future__ import annotations

from datetime import date

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    DEFAULT_STREAK_LIMIT,
    MIN_STREAK_RUN_S,
    RunStreak,
    streak_summary,
)
from .command_support import activity_start
from .format import fmt_time
from .review import exclude_review


def _distance(streak: RunStreak) -> str:
    return f"{streak.distance_m / 1000:.1f} km"


def _days(streak: RunStreak) -> str:
    return "1 day" if streak.days == 1 else f"{streak.days} days"


def _line(streak: RunStreak) -> str:
    return (
        f"{_days(streak)}, {streak.start} → {streak.end}, "
        f"{_distance(streak)}, {fmt_time(streak.duration_s)}"
    )


def streaks_report(
    source: DataSource,
    *,
    today: date | None = None,
    limit: int = DEFAULT_STREAK_LIMIT,
    include_review: bool = False,
) -> str:
    """Render the current and longest running streaks."""
    today = today or date.today()
    activities, excluded = exclude_review(
        source.activities(activity_start(source, today), today),
        include_review=include_review,
    )
    summary = streak_summary(activities, today, limit=limit)

    lines = ["# Running streaks", f"Through {today}"]

    if excluded:
        lines.append(f"\n> {excluded} activities excluded (import review)")

    if not summary.run_days:
        lines.extend(["", "- No runs yet"])
        return "\n".join(lines)

    if summary.current is None:
        lines.append(f"\n- Current: none (last run {summary.last_run})")
    else:
        state = "today run" if summary.today_run else "today not run yet"
        lines.append(f"\n- Current: {_line(summary.current)} ({state})")

    minutes = MIN_STREAK_RUN_S // 60
    lines.extend([
        "",
        f"- A streak day needs one run of at least {minutes} minutes; a rest "
        "day ends the streak and a ride never extends it.",
        "",
        "## Longest streaks",
        "",
        "| Start | End | Days | Distance | Time |",
        "|---|---|---:|---:|---:|",
    ])

    for streak in summary.longest:
        lines.append(
            f"| {streak.start} | {streak.end} | {streak.days} | "
            f"{_distance(streak)} | {fmt_time(streak.duration_s)} |"
        )

    if len(summary.longest) < summary.streak_count:
        lines.extend([
            "",
            f"Showing the {len(summary.longest)} longest of "
            f"{summary.streak_count} streaks.",
        ])

    return "\n".join(lines)
