"""Daily training report."""

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    RESTING_HR_WINDOW_DAYS,
    activity_sort_key,
    resting_hr_baselines,
)
from .format import (
    fmt_time,
    format_activity,
    format_fenced_block,
    format_nights,
    sport_label,
)
from .review import exclude_review, review_note
from .sources import create_source


def format_event(event) -> list[str]:
    """Render one planned event as Markdown lines."""
    lines = [f"\n### {event.name}"]

    if event.type:
        lines.append(f"- Type: {sport_label(event)}")

    if event.duration_s:
        lines.append(f"- Duration: {fmt_time(event.duration_s)}")

    if event.distance_m:
        lines.append(f"- Distance: {event.distance_m/1000:.1f} km")

    description = event.description.strip("\n") if event.description else ""

    if description.strip():
        # Render the description as a fenced block so its structure stands
        # apart from the report's own Markdown. Keep it top-level (not
        # nested under a bullet): nested fences are not parsed by the HTML
        # conversion and show up as literal backticks.
        lines.append("")
        lines.extend(format_fenced_block(description))

    return lines


def _activity_lines(
    source,
    activities,
    prefix: str = "",
    resting_hr=None,
):
    lines = []

    for activity in sorted(activities, key=activity_sort_key):
        heading = f"{prefix}{sport_label(activity)} {activity.name}"
        lines.extend(
            format_activity(
                source,
                activity,
                heading,
                resting_hr=(
                    resting_hr(activity.date)
                    if callable(resting_hr)
                    else resting_hr
                ),
            )
        )

    return lines


def _plan_lines(events, heading: str, empty_message: str):
    lines = [f"\n## {heading}"]

    if not events:
        lines.append(empty_message)
        return lines

    for event in events:
        lines.extend(format_event(event))

    return lines


def daily(
    source: DataSource | None = None,
    *,
    include_review: bool = False,
    today: date | None = None,
):
    if source is None:
        with create_source() as source:
            return daily(
                source,
                include_review=include_review,
                today=today,
            )

    today = today or date.today()
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
        today - timedelta(days=RESTING_HR_WINDOW_DAYS),
        today
    )
    baseline = resting_hr_baselines(wellness)

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
        lines.extend(
            _activity_lines(source, activities, resting_hr=baseline)
        )
    else:
        lines.append("- No activity")

    lines.extend(format_nights(wellness))

    if activities_today:
        lines.extend(
            _activity_lines(
                source,
                activities_today,
                prefix="Today:  ",
                resting_hr=baseline,
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
