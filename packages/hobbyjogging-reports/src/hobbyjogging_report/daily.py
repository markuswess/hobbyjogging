"""Daily training report."""

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .analysis import activity_sort_key
from .format import (
    fmt_time,
    format_activity,
    format_fenced_block,
    last_four_nights,
    sport_label,
)
from .review import exclude_review, review_note
from .sources import create_source


def format_event(event) -> list[str]:
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
