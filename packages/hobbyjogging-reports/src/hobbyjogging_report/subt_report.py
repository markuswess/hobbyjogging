"""subT and LT1 work-block report."""

from __future__ import annotations

from datetime import date

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    is_lt1_activity,
    is_subt_activity,
    running_thresholds,
    subt_report_blocks,
    subt_report_summary,
    threshold_at,
)
from .command_support import resting_hr_lookup
from .format import (
    format_subt_block_table,
    format_subt_summary_table,
    subt_category_label,
)
from .review import exclude_review, review_note
from .sources import create_source


def subt_report(
    start: date,
    end: date,
    title: str = "subT Report",
    source: DataSource | None = None,
    *,
    include_review: bool = False,
):
    """Render subT and LT1 work blocks grouped by category."""
    if start > end:
        raise ValueError("start must not be after end")

    if source is None:
        with create_source() as source:
            return subt_report(
                start,
                end,
                title,
                source,
                include_review=include_review,
            )

    activities, excluded = exclude_review(
        source.activities(start, end),
        include_review=include_review,
    )

    activities = [
        activity
        for activity in activities
        if is_subt_activity(activity) or is_lt1_activity(activity)
    ]

    intervals_by_id = {}

    for activity in activities:
        try:
            intervals_by_id[activity.id] = (
                source.activity_intervals(activity.id)
            )
        except Exception:
            intervals_by_id[activity.id] = []

    blocks = subt_report_blocks(
        activities,
        intervals_by_id,
        resting_hr=resting_hr_lookup(source, start, end),
    )
    thresholds = running_thresholds(source.athlete_thresholds())

    def threshold_pace(day):
        point = threshold_at(thresholds, day)
        return point.pace_s_per_km if point else None

    lookup = threshold_pace if thresholds else None

    lines = [f"# {title}", f"{start} → {end}"]

    note = review_note(excluded)
    if note:
        lines.append(f"\n> {note}")

    if not blocks:
        lines.append("\n- No subT or LT1 sessions with work data")
        return "\n".join(lines)

    summaries, total = subt_report_summary(blocks)

    ndays = (end - start).days + 1

    lines.append("\n## Summary")
    lines.extend(
        format_subt_summary_table(summaries, total, ndays)
    )

    unique_sessions = {block.activity_id for block in blocks}

    if len(unique_sessions) < len(blocks):
        lines.append(
            "\nSessions with work in more than one category appear in "
            "each group."
        )

    if lookup is not None:
        lines.append(
            "\nΔ threshold is the work pace minus the run threshold "
            "setting in effect; positive is slower."
        )

    by_category = {}

    for block in blocks:
        by_category.setdefault(block.category, []).append(block)

    for summary in summaries:
        category_blocks = by_category.get(summary.category)

        if not category_blocks:
            continue

        lines.append(f"\n## {subt_category_label(summary.category)}")

        if any(block.derived for block in category_blocks):
            lines.append(
                "Work reps marked (derived) come from device laps, not a "
                "measured interval set."
            )
            lines.append("")

        lines.extend(
            format_subt_block_table(
                category_blocks,
                threshold_lookup=lookup,
            )
        )

    return "\n".join(lines)
