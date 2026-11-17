"""Dashboard Gear tab: mileage, wear, coverage, and retirement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.datasource import DataSource

from ..analysis import (
    DEFAULT_SHOE_TARGET_M,
    device_usage,
    equipment_coverage,
    equipment_usage,
    group_equipment,
    retirement_candidates,
)
from ..charts import plot_devices, plot_equipment
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
    devices_html: str
    candidates_html: str


def _km(value: float) -> str:
    return f"{value / 1000:,.0f}"


def _target_cell(stat) -> str:
    if not stat.target_distance_m:
        return "-"
    value = f"{stat.target_distance_m / 1000:,.0f} km"
    return f"{value}*" if stat.target_is_default else value


def _devices_html(device_stats) -> str:
    if not device_stats:
        return '<p class="muted">No recording devices.</p>'

    rows = [
        [
            esc(stat.label),
            esc(stat.product),
            str(stat.activities),
            esc(str(stat.first_used or "-")),
            esc(str(stat.last_used or "-")),
            "retired" if stat.retired else "active",
        ]
        for stat in device_stats
    ]

    return plot_devices(
        device_stats,
        "",
        as_html=True,
    ) + table(
        [
            "Device", "Product", "Activities", "First used",
            "Last used", "Status",
        ],
        rows,
        numeric=(2,),
    )


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
    devices = source.devices()
    device_stats = device_usage(devices, activities)

    if not stats:
        return GearSection(
            summary_html="",
            chart_html=NO_CHART,
            table_html=NO_GEAR,
            coverage_html="",
            devices_html=_devices_html(device_stats),
            candidates_html="",
        )

    groups = group_equipment(stats)
    active = sum(1 for stat in stats if not stat.retired)
    counts = ", ".join(
        f"{len(items)} "
        f"{key if len(items) == 1 else label.lower()}"
        for key, label, items in groups
    )
    summary = (
        f"<p>{len(stats)} item{'s' if len(stats) != 1 else ''}: "
        f"{active} active, {len(stats) - active} retired ({counts}).</p>"
    )

    if excluded:
        summary += (
            f'<p class="muted">{excluded} activities are hidden by import '
            "review.</p>"
        )

    table_html = ""

    for key, label, items in groups:
        rows = [
            [
                esc(stat.label),
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
            for stat in items
        ]
        table_html += f"<h3>{esc(label)}</h3>"
        table_html += table(
            [
                "Gear", "Sessions", "km", "km/month", "Last used",
                "Target", "Wear", "Status",
            ],
            rows,
            numeric=(1, 2, 3, 6),
            collapse=f"gear-{key}",
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

    devices_html = _devices_html(device_stats)

    candidates_html = ""

    if candidates:
        reasons = {
            stat.equipment.id: reason for stat, reason in candidates
        }

        for _key, label, items in groups:
            found = [
                (stat, reasons[stat.equipment.id])
                for stat in items
                if stat.equipment.id in reasons
            ]

            if not found:
                continue

            candidates_html += f"<h3>{esc(label)}</h3><ul>"
            candidates_html += "".join(
                f"<li>{esc(stat.label)}: {esc(reason)}</li>"
                for stat, reason in found
            )
            candidates_html += "</ul>"
    else:
        candidates_html = (
            '<p class="muted">No retirement candidates.</p>'
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
        devices_html=devices_html,
        candidates_html=candidates_html,
    )
