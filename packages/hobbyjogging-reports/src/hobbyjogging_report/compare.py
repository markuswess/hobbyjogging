"""Yearly and monthly comparison report."""

from datetime import date

from hobbyjogging_core.datasource import DataSource

from .analysis import COMPARE_MODES, compare_periods
from .format import fmt_time, format_pace
from .review import exclude_review, review_note


def _time_cell(seconds: float) -> str:
    return fmt_time(seconds)


def _km_cell(distance_m: float) -> str:
    if not distance_m:
        return "-"
    return f"{distance_m / 1000:,.1f}"


def _pace_cell(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return f"{format_pace(seconds)}/km"


def _hr_cell(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def _all_years_start(source: DataSource, end: date) -> date:
    """First Jan 1 covered by the source, falling back to 2000."""
    getter = getattr(source, "earliest_activity_date", None)
    first = getter() if callable(getter) else None

    if first is None:
        first = date(2000, 1, 1)

    return min(date(first.year, 1, 1), end)


def compare_report(
    mode: str,
    start: date | None,
    end: date,
    source: DataSource,
    *,
    include_review: bool = False,
) -> str:
    """Render a compact year/month comparison table.

    ``start`` may be ``None`` for the default ``years`` view, which starts at
    the first year present in the source.
    """
    if mode not in COMPARE_MODES:
        raise ValueError(f"unknown compare mode: {mode}")

    if start is None:
        start = _all_years_start(source, end)

    if start > end:
        raise ValueError("start must not be after end")

    activities, excluded = exclude_review(
        source.activities(start, end),
        include_review=include_review,
    )
    periods = compare_periods(activities, mode, start, end)
    title = "Training Comparison by Year" if mode == "years" else (
        "Training Comparison by Month"
    )

    lines = [
        f"# {title}",
        f"{start} → {end}",
    ]

    note = review_note(excluded)
    if note:
        lines.append(f"\n> {note}")

    if not activities:
        lines.append("\n- No activities in this range")
        return "\n".join(lines)

    lines.extend([
        "",
        "| Period | Runs | Cross | Run time | Cross time | Run km | "
        "Avg pace | Avg HR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])

    for period in periods:
        lines.append(
            f"| {period.label} | {period.runs} | {period.cross_sessions} | "
            f"{_time_cell(period.run_time_s)} | "
            f"{_time_cell(period.cross_time_s)} | "
            f"{_km_cell(period.run_distance_m)} | "
            f"{_pace_cell(period.pace_s_per_km)} | "
            f"{_hr_cell(period.avg_hr)} |"
        )

    return "\n".join(lines)
