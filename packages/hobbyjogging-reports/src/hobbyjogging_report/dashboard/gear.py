"""Dashboard Gear tab: mileage, wear, coverage, and retirement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.datasource import DataSource

from ..analysis import (
    DEFAULT_SHOE_TARGET_M,
    equipment_coverage,
    equipment_usage,
    retirement_candidates,
)
from ..charts import plot_equipment
from ..command_support import activity_start
from ..html import esc, table
from ..review import exclude_review

NO_GEAR = '<p class="muted">No equipment records.</p>'
NO_CHART = '<p class="muted">No gear mileage to plot.</p>'


@dataclass(frozen=True)
class GearSection:
    """Rendered gear cards for the dashboard."""

    summary_html: str
    chart_html: str
    table_html: str
    coverage_html: str
    candidates_html: str


def _km(value: float) -> str:
    return f"{value / 1000:,.0f}"


def _target_cell(stat) -> str:
    if not stat.target_distance_m:
        return "-"
    value = f"{stat.target_distance_m / 1000:,.0f} km"
    return f"{value}*" if stat.target_is_default else value


def build_gear_section(
    source: DataSource,
    *,
    today: date,
    include_review: bool = False,
) -> GearSection:
    """Build the mileage chart, table, coverage, and candidates."""
    equipment = source.equipment()
    activities, excluded = exclude_review(
        source.activities(activity_start(source, today), today),
        include_review=include_review,
    )
    stats = equipment_usage(equipment, activities)
    coverage = equipment_coverage(activities)
    candidates = retirement_candidates(stats, today)

    if not stats:
        return GearSection(
            summary_html="",
            chart_html=NO_CHART,
            table_html=NO_GEAR,
            coverage_html="",
            candidates_html="",
        )

    active = sum(1 for stat in stats if not stat.retired)
    summary = (
        f"<p>{len(stats)} items: {active} active, "
        f"{len(stats) - active} retired.</p>"
    )

    if excluded:
        summary += (
            f'<p class="muted">{excluded} activities are hidden by import '
            "review.</p>"
        )

    rows = [
        [
            esc(stat.label),
            esc(stat.equipment.type),
            str(stat.sessions),
            _km(stat.distance_m),
            (
                "-"
                if stat.km_per_month is None
                else f"{stat.km_per_month:.1f}"
            ),
            esc(stat.last_used or "-"),
            _target_cell(stat),
            "-" if stat.wear is None else f"{stat.wear * 100:.0f}%",
            "retired" if stat.retired else "active",
        ]
        for stat in stats
    ]
    table_html = table(
        [
            "Gear", "Type", "Sessions", "km", "km/month", "Last used",
            "Target", "Wear", "Status",
        ],
        rows,
        numeric=(2, 3, 4, 7),
    )
    table_html += (
        '<p class="muted">`*` default shoe target '
        f"({DEFAULT_SHOE_TARGET_M / 1000:.0f} km); set "
        "`target_distance_m` to override.</p>"
    )

    coverage_html = table(
        ["Year", "With gear", "Without gear"],
        [
            [str(year), str(with_gear), str(without_gear)]
            for year, (with_gear, without_gear) in coverage.items()
        ],
        numeric=(1, 2),
    )

    candidates_html = (
        "<ul>"
        + "".join(
            f"<li>{esc(stat.label)}: {esc(reason)}</li>"
            for stat, reason in candidates
        )
        + "</ul>"
        if candidates
        else '<p class="muted">No retirement candidates.</p>'
    )

    return GearSection(
        summary_html=summary,
        chart_html=(
            plot_equipment(stats, "", as_html=True)
            if any(stat.sessions for stat in stats)
            else NO_CHART
        ),
        table_html=table_html,
        coverage_html=coverage_html,
        candidates_html=candidates_html,
    )
