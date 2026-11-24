"""Marathon build comparison: the table shared by the report and the tab."""

from __future__ import annotations

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    MARATHON_WEEKS,
    MarathonBuild,
    official_by_activity,
    marathon_builds,
    race_results,
)
from .command_support import activity_start
from .format import fmt_clock, fmt_time, table_text
from .review import exclude_review, review_note

CELL_NOTE = (
    "Each cell: volume (km) · time · fast (Z3+Z4) · quality sessions; "
    "* marks planned values from the event calendar."
)
NO_BUILDS = "No marathon results or upcoming marathon."


def _header(build: MarathonBuild) -> str:
    outcome = (
        "planned"
        if build.planned
        else fmt_clock(build.result_s)
    )

    return f"{table_text(build.name)} {build.date} ({outcome})"


def _display_values(week):
    """The four numbers to show for one week, or ``None`` when empty."""
    if week.planned:
        return (
            week.planned_distance_km,
            week.planned_time_s,
            week.planned_fast_s,
            week.planned_quality,
        )

    if not week.has_data:
        return None

    return (
        week.distance_km,
        week.time_s,
        week.fast_s,
        week.quality,
    )


def _cell(values, *, planned: bool) -> str:
    if values is None:
        return "-"

    distance, time_s, fast_s, quality = values
    parts = [
        "-" if distance is None else f"{distance:.0f}",
        "-" if time_s is None else fmt_time(time_s),
        "-" if fast_s is None else fmt_time(fast_s),
        "-" if quality is None else str(quality),
    ]

    return " · ".join(parts) + (" *" if planned else "")


def _week_cell(week) -> str:
    return _cell(_display_values(week), planned=week.planned)


def _total_cell(build: MarathonBuild) -> str:
    weeks = [
        (week, values)
        for week in build.weeks
        if (values := _display_values(week)) is not None
    ]

    if not weeks:
        return "-"

    total = [
        sum(values[index] for _, values in weeks if values[index] is not None)
        if any(values[index] is not None for _, values in weeks)
        else None
        for index in range(4)
    ]
    planned = any(week.planned for week, _ in weeks)

    return _cell(tuple(total), planned=planned)


def marathon_builds_table(
    builds: list[MarathonBuild],
) -> tuple[list[str], list[list[str]]]:
    """Headers and rows for the build matrix, weeks newest last."""
    headers = ["Week", *(_header(build) for build in builds)]

    if not builds:
        return headers, []

    rows = []

    for index, week in enumerate(builds[0].weeks):
        rows.append(
            [week.label]
            + [_week_cell(build.weeks[index]) for build in builds]
        )

    rows.append(["Total"] + [_total_cell(build) for build in builds])

    return headers, rows


def marathon_builds_report(
    source: DataSource,
    *,
    today: date | None = None,
    weeks: int = MARATHON_WEEKS,
    include_review: bool = False,
) -> str:
    """Render the marathon build comparison as Markdown."""
    if weeks <= 0:
        raise ValueError("--weeks must be positive")

    today = today or date.today()
    activities, excluded = exclude_review(
        source.activities(activity_start(source, today), today),
        include_review=include_review,
    )
    results = race_results(
        activities,
        official_by_activity(source.race_results()),
    )
    events = source.events(
        today - timedelta(days=7 * weeks),
        today + timedelta(days=366),
    )
    builds = marathon_builds(activities, results, events, today, weeks=weeks)
    headers, rows = marathon_builds_table(builds)

    lines = [
        "# Marathon builds",
        f"{weeks}-week blocks ending on each marathon",
    ]

    note = review_note(excluded)
    if note:
        lines.append(f"\n> {note}")

    if not rows:
        lines.extend(["", f"- {NO_BUILDS}"])
        return "\n".join(lines)

    lines.extend(["", CELL_NOTE, ""])
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|---|" + "|".join("---:" for _ in headers[1:]) + "|")
    lines.extend(
        "| " + " | ".join(row) + " |"
        for row in rows
    )

    return "\n".join(lines)
