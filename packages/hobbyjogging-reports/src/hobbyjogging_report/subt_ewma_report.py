"""subT/LT1 EWMA report: smoothed work pace and heart rate per category."""

from __future__ import annotations

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    SUBT_CATEGORY_ORDER,
    average_warmup_days,
    subt_ewma,
)
from .command_support import subt_session_points
from .format import format_pace
from .model import AverageWindows
from .review import exclude_review

CATEGORY_LABELS = {
    "short": "Short",
    "medium": "Medium",
    "long": "Long",
    "lt1": "LT1",
}
WINDOW_LABELS = ((7, "7-day EWMA"), (42, "42-day EWMA"), (182, "182-day EWMA"))


def _pace_cell(value: float | None) -> str:
    return "-" if value is None else f"{format_pace(value)}/km"


def _hr_cell(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f} bpm"


def _efficiency_cell(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f} m/beat"


def subt_ewma_markdown(
    points,
    end: date,
    *,
    windows: AverageWindows | None = None,
) -> str:
    """Render the subT EWMA tables for points that include warm-up history."""
    windows = windows or AverageWindows()
    start = end - timedelta(days=average_warmup_days(windows))
    rows = subt_ewma(points, start, end, windows=windows)
    order = {name: index for index, name in enumerate(SUBT_CATEGORY_ORDER)}
    rows = sorted(rows, key=lambda row: order.get(row.category, 99))
    header = "| Category | " + " | ".join(
        label for _, label in WINDOW_LABELS
    ) + " |"
    divider = "|---|" + "---:|" * len(WINDOW_LABELS)

    lines = [
        "# subT EWMA Report",
        f"7/42/182-day EWMAs ending {end}",
        "",
        "## Pace",
        "",
        header,
        divider,
    ]

    for row in rows:
        cells = " | ".join(
            _pace_cell(row.pace[tau]) for tau, _ in WINDOW_LABELS
        )
        label = CATEGORY_LABELS.get(row.category, row.category.title())
        lines.append(f"| {label} | {cells} |")

    lines.extend([
        "",
        "## Heart rate",
        "",
        header,
        divider,
    ])

    for row in rows:
        cells = " | ".join(
            _hr_cell(row.hr[tau]) for tau, _ in WINDOW_LABELS
        )
        label = CATEGORY_LABELS.get(row.category, row.category.title())
        lines.append(f"| {label} | {cells} |")

    lines.extend([
        "",
        "## Efficiency",
        "",
        header,
        divider,
    ])

    for row in rows:
        cells = " | ".join(
            _efficiency_cell(row.efficiency[tau])
            for tau, _ in WINDOW_LABELS
        )
        label = CATEGORY_LABELS.get(row.category, row.category.title())
        lines.append(f"| {label} | {cells} |")

    lines.extend([
        "",
        "EWMAs of the work-interval pace, the session average heart rate, and "
        "efficiency (sum(distance) / sum(beats)) per category; days between "
        "sessions keep the last measured value.",
    ])

    return "\n".join(lines)


def subt_ewma_report(
    source: DataSource,
    *,
    today: date | None = None,
    include_review: bool = False,
) -> str:
    """Render the subT EWMA report for the canonical database."""
    today = today or date.today()
    windows = AverageWindows()
    start = today - timedelta(days=average_warmup_days(windows))
    activities, _ = exclude_review(
        source.activities(start, today),
        include_review=include_review,
    )

    return subt_ewma_markdown(
        subt_session_points(source, activities),
        today,
        windows=windows,
    )
