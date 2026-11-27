"""Gear mileage and coverage report."""

from __future__ import annotations

from datetime import date

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    DEFAULT_SHOE_TARGET_M,
    RUN_TYPES,
    device_usage,
    equipment_coverage,
    equipment_detail,
    equipment_usage,
    group_equipment,
    retirement_candidates,
    select_equipment,
)
from .command_support import activity_start
from .format import (
    activity_display_name,
    pace,
    table_text,
)
from .review import exclude_review


def _km(value: float) -> str:
    return f"{value / 1000:,.0f}"


def _target(stat) -> str:
    if not stat.target_distance_m:
        return "-"

    value = f"{stat.target_distance_m / 1000:,.0f} km"
    return f"{value}*" if stat.target_is_default else value


def _wear(stat) -> str:
    if stat.wear is None:
        return "-"
    return f"{stat.wear * 100:.0f}%"


def _last_used(stat) -> str:
    return str(stat.last_used) if stat.last_used else "-"


def equipment_report(
    source: DataSource,
    *,
    today: date | None = None,
    include_review: bool = False,
    default_shoe_target_m: float = DEFAULT_SHOE_TARGET_M,
) -> str:
    """Render gear mileage, coverage, and retirement candidates."""
    today = today or date.today()
    equipment = source.equipment()
    activities, excluded = exclude_review(
        source.activities(activity_start(source, today), today),
        include_review=include_review,
    )
    stats = equipment_usage(
        equipment,
        activities,
        default_shoe_target_m=default_shoe_target_m,
    )
    coverage = equipment_coverage(activities)
    candidates = retirement_candidates(stats, today)

    lines = [
        "# Gear",
        f"Through {today}",
    ]

    if excluded:
        lines.append(
            f"\n> {excluded} activities excluded (import review)"
        )

    if not stats:
        lines.extend(["", "- No equipment records"])
        return "\n".join(lines)

    groups = group_equipment(stats)
    devices = device_usage(source.devices(), activities)
    active = sum(1 for stat in stats if not stat.retired)
    counts = ", ".join(
        f"{len(items)} "
        f"{key if len(items) == 1 else label.lower()}"
        for key, label, items in groups
    )
    lines.extend([
        "",
        (
            f"{len(stats)} item{'s' if len(stats) != 1 else ''}: "
            f"{active} active, {len(stats) - active} retired ({counts})."
        ),
    ])

    for _key, label, items in groups:
        lines.extend([
            "",
            f"## {label}",
            "",
            "| Gear | Sessions | km | km/month | Last used | "
            "Target | Wear | Status | Notes |",
            "|---|---:|---:|---:|---|---:|---:|---|---|",
        ])

        for stat in items:
            lines.append(
                f"| {table_text(stat.label)} | "
                f"{stat.sessions} | {_km(stat.distance_m)} | "
                f"{'-' if stat.km_per_month is None else f'{stat.km_per_month:.1f}'} | "
                f"{_last_used(stat)} | {_target(stat)} | {_wear(stat)} | "
                f"{'retired' if stat.retired else 'active'} | "
                f"{table_text(stat.equipment.notes) or '-'} |"
            )

    if devices:
        lines.extend([
            "",
            "## Devices",
            "",
            "| Device | Activities | First used | Last used | Status |",
            "|---|---:|---|---|---|",
        ])

        for stat in devices:
            lines.append(
                f"| {table_text(stat.label)} | "
                f"{stat.activities} | {stat.first_used or '-'} | "
                f"{stat.last_used or '-'} | "
                f"{'retired' if stat.retired else 'active'} |"
            )

    lines.extend([
        "",
        (
            f"`*` default shoe target ({default_shoe_target_m / 1000:.0f} km); "
            "set `target_distance_m` to override."
        ),
        "",
        "## Coverage",
        "",
        "| Year | With gear | Without gear |",
        "|---|---:|---:|",
    ])

    for year, (with_gear, without_gear) in coverage.items():
        lines.append(f"| {year} | {with_gear} | {without_gear} |")

    if candidates:
        lines.extend(["", "## Retirement candidates"])
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

            lines.extend(["", f"### {label}", ""])
            for stat, reason in found:
                lines.append(f"- {stat.label}: {reason}")

    return "\n".join(lines)


def _gear_meta(stat) -> str:
    """Brand/model and acquisition line for one item."""
    item = stat.equipment
    parts = [
        part
        for part in (item.brand, item.model)
        if part
    ]
    meta = " ".join(parts) or item.type.replace("_", " ").capitalize()

    if item.acquired_on:
        meta += f" · acquired {item.acquired_on}"

    if item.retired_on:
        meta += f" · retired {item.retired_on}"

    return meta


def gear_report(
    source: DataSource,
    selector: str,
    *,
    today: date | None = None,
    include_review: bool = False,
    default_shoe_target_m: float = DEFAULT_SHOE_TARGET_M,
) -> str:
    """Render one gear item's totals, mileage, sessions and co-used gear.

    This is the console form of the dashboard's ``gear/<item>.html`` page:
    both read :func:`equipment_detail`, so the numbers match.
    """
    today = today or date.today()
    equipment = source.equipment()
    item = select_equipment(equipment, selector)
    activities, excluded = exclude_review(
        source.activities(activity_start(source, today), today),
        include_review=include_review,
    )
    stats = equipment_usage(
        equipment,
        activities,
        default_shoe_target_m=default_shoe_target_m,
    )
    stat = next(
        stat for stat in stats if stat.equipment.id == item.id
    )
    detail = equipment_detail(stat, activities, equipment)
    km_per_month = (
        "-" if stat.km_per_month is None else f"{stat.km_per_month:.1f}"
    )

    lines = [
        f"# Gear — {stat.label}",
        f"Through {today}",
        "",
        _gear_meta(stat),
        "",
        "| Sessions | km | km/month | First used | Last used | "
        "Target | Wear | Status |",
        "|---:|---:|---:|---|---|---:|---:|---|",
        (
            f"| {stat.sessions} | {_km(stat.distance_m)} | "
            f"{km_per_month} | {stat.first_used or '-'} | "
            f"{_last_used(stat)} | {_target(stat)} | {_wear(stat)} | "
            f"{'retired' if stat.retired else 'active'} |"
        ),
    ]

    if excluded:
        lines.append(f"\n> {excluded} activities excluded (import review)")

    lines.extend(["", "## Monthly mileage"])

    if detail.monthly:
        lines.extend([
            "",
            "| Month | km | Cumulative km |",
            "|---|---:|---:|",
        ])
        total = 0.0

        for month, km in detail.monthly:
            total += km
            lines.append(f"| {month:%Y-%m} | {km:.1f} | {total:.1f} |")
    else:
        lines.append("\n- No sessions recorded.")

    lines.extend(["", "## Activities"])

    if detail.activities:
        lines.extend([
            "",
            "| Date | Activity | km | Pace | With |",
            "|---|---|---:|---|---|",
        ])

        for entry in detail.activities:
            activity = entry.activity
            others = ", ".join(item.name for item in entry.others) or "-"
            distance = (
                "-"
                if not activity.distance_m
                else f"{activity.distance_m / 1000:.1f}"
            )
            pace_cell = (
                pace(activity)
                if activity.type in RUN_TYPES
                else "-"
            )
            lines.append(
                f"| {activity.date} | "
                f"{table_text(activity_display_name(activity))} | "
                f"{distance} | {pace_cell} | {table_text(others)} |"
            )
    else:
        lines.append("\n- No sessions recorded.")

    lines.extend(["", "## Co-used gear"])

    if detail.co_used:
        lines.append("")
        for other, count in detail.co_used:
            lines.append(
                f"- {other.name}: {count} "
                f"session{'s' if count != 1 else ''}"
            )
    else:
        lines.append("\n- No co-used gear.")

    if stat.equipment.notes:
        lines.extend(["", "## Notes", "", table_text(stat.equipment.notes)])

    return "\n".join(lines)
