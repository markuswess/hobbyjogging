"""Upcoming planned workouts report."""

from datetime import date

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
    include_review: bool = False,
) -> str:
    """Render a compact table of planned sessions in a forward range.

    Events without a sport type (illness or travel notes) are skipped.
    """
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

    return "\n".join(lines)
