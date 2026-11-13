"""Gear mileage and coverage report."""

from __future__ import annotations

from datetime import date

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    DEFAULT_SHOE_TARGET_M,
    equipment_coverage,
    equipment_usage,
    retirement_candidates,
)
from .command_support import activity_start
from .format import table_text
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

    active = sum(1 for stat in stats if not stat.retired)
    lines.extend([
        "",
        (
            f"{len(stats)} items: {active} active, "
            f"{len(stats) - active} retired."
        ),
        "",
        "| Gear | Type | Sessions | km | km/month | Last used | "
        "Target | Wear | Status | Notes |",
        "|---|---|---:|---:|---:|---|---:|---:|---|---|",
    ])

    for stat in stats:
        lines.append(
            f"| {table_text(stat.label)} | {stat.equipment.type} | "
            f"{stat.sessions} | {_km(stat.distance_m)} | "
            f"{'-' if stat.km_per_month is None else f'{stat.km_per_month:.1f}'} | "
            f"{_last_used(stat)} | {_target(stat)} | {_wear(stat)} | "
            f"{'retired' if stat.retired else 'active'} | "
            f"{table_text(stat.equipment.notes) or '-'} |"
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
        lines.extend(["", "## Retirement candidates", ""])
        for stat, reason in candidates:
            lines.append(f"- {stat.label}: {reason}")

    return "\n".join(lines)
