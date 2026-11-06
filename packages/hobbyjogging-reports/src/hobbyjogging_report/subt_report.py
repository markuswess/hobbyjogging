"""subT and LT1 work-block report."""

from datetime import date

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    is_lt1_activity,
    is_subt_activity,
    subt_report_blocks,
    subt_report_summary,
)
from .format import (
    format_subt_block_table,
    format_subt_summary_table,
    subt_category_label,
)
from .review import exclude_review, review_note
from .sources import DEFAULT_SOURCE, create_source


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
        with create_source(DEFAULT_SOURCE) as source:
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

    blocks = subt_report_blocks(activities, intervals_by_id)

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

    by_category = {}

    for block in blocks:
        by_category.setdefault(block.category, []).append(block)

    for summary in summaries:
        category_blocks = by_category.get(summary.category)

        if not category_blocks:
            continue

        lines.append(f"\n## {subt_category_label(summary.category)}")
        lines.extend(format_subt_block_table(category_blocks))

    return "\n".join(lines)
