"""Upcoming planned workouts report."""

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .analysis import event_zone_time
from .format import fmt_time, sport_label, table_text


def _distance_cell(distance_m: float | None) -> str:
    if not distance_m:
        return "-"
    return f"{distance_m / 1000:.1f} km"


def _load_cell(load: float | None) -> str:
    return "-" if load is None else f"{load:.0f}"


def _zone_cell(event) -> str:
    """Planned time in zones 3 and 4 for the event's own zone kind."""
    seconds = event_zone_time(event, (3, 4))

    if seconds is None:
        return "-"

    return fmt_time(seconds) if seconds else "0min"


def planned_report(
    start: date,
    end: date,
    source: DataSource,
    *,
    today: date | None = None,
) -> str:
    """Render a compact table of planned sessions in a forward range.

    The report always starts tomorrow, even when ``start`` is today or in the
    past. Events without a sport type (illness or travel notes) are skipped.
    """
    today = today or date.today()
    start = max(start, today + timedelta(days=1))

    events = sorted(
        (
            event
            for event in source.events(start, end)
            if event.type
        ),
        key=lambda event: (event.date, event.name),
    )

    lines = [
        "# Planned Workouts",
        f"{start} to {end}",
    ]

    if not events:
        lines.append("\n- No planned sessions")
        return "\n".join(lines)

    lines.extend([
        "",
        "| Date | Day | Workout | Sport | Distance | Time | Z3+4 | Load |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ])

    for event in events:
        lines.append(
            f"| {event.date} | {event.date:%a} | "
            f"{table_text(event.name) or '-'} | {sport_label(event)} | "
            f"{_distance_cell(event.distance_m)} | "
            f"{fmt_time(event.duration_s)} | "
            f"{_zone_cell(event)} | "
            f"{_load_cell(event.training_load)} |"
        )

    if any(event.zone_times for event in events):
        lines.extend([
            "",
            "Z3+4 uses each event's planned zone kind "
            "(pace, HR, or power).",
        ])

    lines.extend(_summary_lines(events, start, end))

    return "\n".join(lines)


def _summary_lines(events, start: date, end: date) -> list[str]:
    """Weekly-average planned totals for the report range."""
    range_days = max((end - start).days + 1, 1)
    weekly_factor = 7 / range_days

    total_s = sum(event.duration_s or 0 for event in events)
    zone_values = [event_zone_time(event, (3, 4)) for event in events]
    has_zone_data = any(value is not None for value in zone_values)
    zone_s = sum(value or 0 for value in zone_values)

    lines = [
        "",
        "## Summary",
        f"- Total time: {fmt_time(total_s * weekly_factor)} / 7 days",
        "- Z3+4 time: "
        + (
            f"{fmt_time(zone_s * weekly_factor)} / 7 days"
            if has_zone_data
            else "- / 7 days"
        ),
    ]

    if range_days != 7:
        unit = "day" if range_days == 1 else "days"
        lines.append(f"\nAveraged over {range_days} {unit}.")

    return lines
