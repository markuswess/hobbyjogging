"""Period summary reports (custom range, weekly, monthly, yearly)."""

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .analysis import activity_sort_key, is_lt1_activity, is_subt_activity
from .classify import category_breakdown
from .format import (
    fmt_time,
    format_category_table,
    format_feel,
    format_fenced_block,
    pace,
    work_summary_for_activity,
)
from .review import exclude_review, review_note
from .sources import DEFAULT_SOURCE, create_source
from .summary import recovery_summary, summarize_training


def period_report(
    start: date,
    end: date,
    title: str,
    source: DataSource | None = None,
    *,
    include_review: bool = False,
) -> str:
    """Render a summary for an inclusive date range."""
    if start > end:
        raise ValueError("start must not be after end")

    if source is None:
        with create_source(DEFAULT_SOURCE) as source:
            return period_report(
                start,
                end,
                title,
                source,
                include_review=include_review,
            )

    ndays = (end - start).days + 1

    activities, excluded = exclude_review(
        source.activities(start, end),
        include_review=include_review,
    )

    activities = sorted(activities, key=activity_sort_key)

    training = summarize_training(activities)

    # subT/LT1 names need intervals for their work-interval details.
    intervals_by_id = {}

    for activity in activities:

        if not (
            is_subt_activity(activity)
            or is_lt1_activity(activity)
        ):
            continue

        try:
            intervals_by_id[activity.id] = (
                source.activity_intervals(activity.id)
            )
        except Exception:
            continue

    breakdown = category_breakdown(activities, intervals_by_id)

    recovery = recovery_summary(
        source.wellness(start, end)
    )

    lines = []

    lines.append(
        f"# {title}"
    )

    lines.append(
        f"{start} → {end}"
    )

    note = review_note(excluded)
    if note:
        lines.append(f"\n> {note}")

    lines.append("\n## Running (avg. per week)")

    lines.append(
        f"- Time: {fmt_time(training['run_time']/ndays*7)}"
    )

    lines.append(
        f"- Distance: "
        f"{training['run_distance']/1000/ndays*7:.1f} km"
    )

    lines.append(
        f"- Load: "
        f"{training['run_load']/ndays*7:.0f}"
    )

    lines.append(
        f"- RPE: "
        f"{training['rpe']/ndays*7:.0f}"
    )

    if training["run_feel_count"]:
        lines.append(
            f"- Feel: "
            f"{training['run_feel']/training['run_feel_count']:.1f} avg"
        )

    lines.append(
        f"- Time in Zones 3 and 4: "
        f"{fmt_time(training['z3_z4_time']/ndays*7)}"
    )

    lines.append("\n## Cross training (avg. per week)")

    lines.append(
        f"- Time: {fmt_time(training['cross_time']/ndays*7)}"
    )

    lines.append(
        f"- Load: "
        f"{training['cross_load']/ndays*7:.0f}"
    )

    if training["cross_feel_count"]:
        lines.append(
            f"- Feel: "
            f"{training['cross_feel']/training['cross_feel_count']:.1f} avg"
        )

    lines.append("\n## Categories (period totals)")

    lines.extend(
        format_category_table(breakdown)
    )

    if len(training["quality"]) < 10:
        lines.append("\n## Quality sessions")

        for q in training["quality"]:

            intervals = intervals_by_id.get(q.id)

            if intervals is None:
                intervals = source.activity_intervals(q.id)

            work = work_summary_for_activity(q, intervals)

            hr = f"{q.avg_hr:.0f}" if q.avg_hr is not None else "-"

            feel = (
                f", feel {format_feel(q.feel)}"
                if q.feel is not None
                else ""
            )

            lines.append(f"\n### {q.name}")
            lines.append(
                f"- Totals: {fmt_time(q.duration_s)}, "
                f"{pace(q)}, {hr} BpM{feel}"
            )

            if work:
                lines.append("- Work intervals done:")
                for line in work:
                    lines.append(f"  - {line}")

            if q.description and q.description.strip():
                lines.append("- Comments:")
                lines.extend(
                    format_fenced_block(q.description, "  ")
                )

    lines.append("\n## Recovery")

    lines.append(
        f"- HRV avg: {recovery['hrv']}"
    )

    lines.append(
        f"- RHR avg: {recovery['rhr']}"
    )

    lines.append(
        f"- Sleep avg: {fmt_time(recovery['sleep'])}"
    )

    return "\n".join(lines)


def summary(
    period,
    source: DataSource | None = None,
    *,
    include_review: bool = False,
    today: date | None = None,
):
    """Render one of the fixed weekly, monthly or yearly reports."""
    today = today or date.today()
    end = today - timedelta(days=1)

    if period == "weekly":
        ndays = 7

    elif period == "monthly":
        ndays = 30

    elif period == "yearly":
        ndays = 365

    else:
        raise ValueError(period)

    start = today - timedelta(days=ndays)

    return period_report(
        start,
        end,
        f"{period.title()} Training Report",
        source=source,
        include_review=include_review,
    )
