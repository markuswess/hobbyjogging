"""Dashboard Gear tab: mileage, wear, coverage, and retirement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.datasource import DataSource

from ..analysis import (
    DEFAULT_SHOE_TARGET_M,
    RUN_TYPES,
    device_usage,
    equipment_coverage,
    equipment_detail,
    equipment_usage,
    group_equipment,
    retirement_candidates,
)
from ..charts import plot_devices, plot_equipment, plot_gear_mileage
from ..command_support import activity_start
from ..format import activity_display_name, pace
from ..html import card, esc, link, stat_grid, table
from ..review import exclude_review
from .paths import activity_href, gear_filename

NO_GEAR = '<p class="muted">No equipment records.</p>'
NO_CHART = '<p class="muted">No gear mileage to plot.</p>'


@dataclass(frozen=True)
class GearItemPage:
    """One gear item's own page, built beside the Gear tab."""

    filename: str
    label: str
    body_html: str


@dataclass(frozen=True)
class GearSection:
    """Rendered gear cards for the dashboard."""

    summary_html: str
    chart_html: str
    table_html: str
    coverage_html: str
    devices_html: str
    candidates_html: str
    items: list[GearItemPage]


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
            "Device", "Activities", "First used", "Last used", "Status",
        ],
        rows,
        numeric=(1,),
    )


def _gear_item_page(stat, detail, linked_ids) -> GearItemPage:
    """One item's totals, mileage chart, sessions and co-used gear."""
    item = stat.equipment
    meta = (
        " ".join(part for part in (item.brand, item.model) if part)
        or item.type
    )

    if item.acquired_on:
        meta += f" · acquired {item.acquired_on}"

    if item.retired_on:
        meta += f" · retired {item.retired_on}"

    summary_html = f'<p class="muted">{esc(meta)}</p>' + stat_grid([
        ("Sessions", esc(str(stat.sessions)), ""),
        ("Distance", esc(f"{stat.distance_m / 1000:,.1f} km"), ""),
        (
            "km/month",
            esc(
                "-"
                if stat.km_per_month is None
                else f"{stat.km_per_month:.1f}"
            ),
            "",
        ),
        ("First used", esc(stat.first_used or "-"), ""),
        ("Last used", esc(stat.last_used or "-"), ""),
        ("Target", esc(_target_cell(stat)), ""),
        ("Wear", esc("-" if stat.wear is None else f"{stat.wear:.0%}"), ""),
        ("Status", esc("retired" if stat.retired else "active"), ""),
    ])

    chart_html = (
        plot_gear_mileage(detail, "", as_html=True)
        if detail.monthly
        else NO_CHART
    )
    activities_html = table(
        ["Date", "Activity", "km", "Pace", "With"],
        [
            [
                esc(str(entry.activity.date)),
                (
                    link(
                        f"../{activity_href(entry.activity.id)}",
                        activity_display_name(entry.activity),
                    )
                    if entry.activity.id in linked_ids
                    else esc(activity_display_name(entry.activity))
                ),
                esc(
                    "-"
                    if not entry.activity.distance_m
                    else f"{entry.activity.distance_m / 1000:.1f}"
                ),
                esc(
                    pace(entry.activity)
                    if entry.activity.type in RUN_TYPES
                    else "-"
                ),
                (
                    ", ".join(
                        link(
                            f"../gear/{gear_filename(other.id)}",
                            other.name,
                        )
                        for other in entry.others
                    )
                    or "-"
                ),
            ]
            for entry in detail.activities
        ],
        numeric=(2,),
        empty="No sessions recorded.",
        collapse=f"gear-item-{item.id}",
    )
    co_used_html = table(
        ["Gear", "Sessions"],
        [
            [
                link(f"../gear/{gear_filename(other.id)}", other.name),
                str(count),
            ]
            for other, count in detail.co_used
        ],
        numeric=(1,),
        empty="No co-used gear.",
    )

    body = (
        card(None, summary_html)
        + card("Mileage", chart_html)
        + card("Activities", activities_html)
        + card("Co-used gear", co_used_html)
    )

    if item.notes:
        body += card("Notes", f"<p>{esc(item.notes)}</p>")

    return GearItemPage(
        filename=gear_filename(item.id),
        label=stat.label,
        body_html=body,
    )


def build_gear_section(
    source: DataSource,
    *,
    today: date,
    include_review: bool = False,
    linked_ids: set[str] | None = None,
) -> GearSection:
    """Build the gear cards and one page per item.

    ``linked_ids`` are the activity ids that also get a detail page; only
    those become links, so a gear page cannot point at a page the dashboard
    did not render.
    """
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
            items=[],
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
                link(f"gear/{gear_filename(stat.equipment.id)}", stat.label),
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

    linked_ids = linked_ids or set()
    item_pages = [
        _gear_item_page(
            stat,
            equipment_detail(stat, activities, equipment),
            linked_ids,
        )
        for stat in stats
    ]

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
        items=item_pages,
    )
