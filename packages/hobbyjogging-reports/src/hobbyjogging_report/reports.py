"""Markdown training reports."""

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    activity_sort_key,
    is_lt1_activity,
    is_subt_activity,
    subt_report_blocks,
    subt_report_summary,
)
from .classify import category_breakdown
from .format import (
    fmt_time,
    format_activity,
    format_category_table,
    format_feel,
    format_fenced_block,
    format_subt_block_table,
    format_subt_summary_table,
    last_four_nights,
    pace,
    sport_label,
    subt_category_label,
    work_summary_for_activity,
)
from .sources import DEFAULT_SOURCE, create_source
from .review import exclude_review, review_note
from .summary import recovery_summary, summarize_training


def _format_event(event) -> list[str]:
    """Render one planned event as Markdown lines."""
    lines = [f"\n### {event.name}"]

    if event.type:
        lines.append(f"- Type: {sport_label(event)}")

    description = event.description.strip("\n") if event.description else ""

    if description.strip():
        # Planned descriptions are Markdown themselves. Render them as a
        # fenced block nested under the bullet so their headings, lists and
        # blank lines cannot disturb the report layout.
        lines.append("- Description:")
        lines.extend(format_fenced_block(description, "  "))

    if event.duration_s:
        lines.append(f"- Duration: {fmt_time(event.duration_s)}")

    if event.distance_m:
        lines.append(f"- Distance: {event.distance_m/1000:.1f} km")

    return lines


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


def _activity_lines(source, activities, prefix: str = ""):
    lines = []

    for activity in sorted(activities, key=activity_sort_key):
        heading = f"{prefix}{sport_label(activity)} {activity.name}"
        lines.extend(format_activity(source, activity, heading))

    return lines


def _night_lines(wellness):
    lines = ["\n## Night"]

    for day in reversed(last_four_nights(wellness)):
        hrv = day.hrv
        rhr = day.resting_hr
        sleep = day.sleep_s

        lines.append(
            f"- {day.date}: "
            + (f"HRV {hrv:.0f} ms, " if hrv is not None else "HRV N/A, ")
            + (
                f"RHR {rhr:.0f} bpm"
                if rhr is not None
                else "RHR N/A"
            )
            + (
                f", Sleep {fmt_time(sleep)}"
                if sleep
                else ", Sleep N/A"
            )
        )

    return lines


def _plan_lines(events, heading: str, empty_message: str):
    lines = [f"\n## {heading}"]

    if not events:
        lines.append(empty_message)
        return lines

    for event in events:
        lines.extend(_format_event(event))

    return lines


def daily(
    source: DataSource | None = None,
    *,
    include_review: bool = False,
):

    if source is None:
        with create_source(DEFAULT_SOURCE) as source:
            return daily(source, include_review=include_review)

    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    activities, excluded = exclude_review(
        source.activities(yesterday, yesterday),
        include_review=include_review,
    )
    activities_today, excluded_today = exclude_review(
        source.activities(today, today),
        include_review=include_review,
    )
    excluded_total = excluded + excluded_today

    wellness = source.wellness(
        today - timedelta(days=4),
        today
    )

    events = source.events(
        today,
        today
    )

    events_tomorrow = source.events(
        tomorrow,
        tomorrow
    )

    lines = [f"# Daily Training Report {today}"]

    note = review_note(excluded_total)
    if note:
        lines.append(f"\n> {note}")

    lines.append("\n## Yesterday")

    if activities:
        lines.extend(_activity_lines(source, activities))
    else:
        lines.append("- No activity")

    lines.extend(_night_lines(wellness))

    if activities_today:
        lines.extend(
            _activity_lines(
                source,
                activities_today,
                prefix="Today:  ",
            )
        )
        # Today already has a session; show what is planned for tomorrow.
        lines.extend(
            _plan_lines(
                events_tomorrow,
                "Planned Tomorrow",
                "- No planned session",
            )
        )
    else:
        # No session today; show what is still planned for today.
        lines.extend(
            _plan_lines(
                events,
                "Planned Today",
                "- No more planned session today",
            )
        )

    return "\n".join(lines)

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
):
    """Render one of the fixed weekly, monthly or yearly reports."""
    today = date.today()
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
