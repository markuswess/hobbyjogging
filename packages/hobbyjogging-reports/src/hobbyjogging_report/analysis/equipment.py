"""Gear mileage, wear, and coverage from canonical equipment links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core.model import Activity, Equipment

DEFAULT_SHOE_TARGET_M = 800_000.0
MONTH_DAYS = 30.4375
UNUSED_DAYS = 365


@dataclass(frozen=True)
class EquipmentStat:
    """Mileage and use summary for one piece of gear."""

    equipment: Equipment
    sessions: int = 0
    distance_m: float = 0
    first_used: date | None = None
    last_used: date | None = None
    target_distance_m: float | None = None
    target_is_default: bool = False

    @property
    def label(self) -> str:
        if self.equipment.acquired_on is None:
            return self.equipment.name
        return (
            f"{self.equipment.name} "
            f"({self.equipment.acquired_on.year})"
        )

    @property
    def retired(self) -> bool:
        return self.equipment.retired_on is not None

    @property
    def months_used(self) -> float | None:
        if self.first_used is None or self.last_used is None:
            return None
        days = (self.last_used - self.first_used).days + 1
        return max(days, 1) / MONTH_DAYS

    @property
    def km_per_month(self) -> float | None:
        months = self.months_used
        if not months:
            return None
        return self.distance_m / 1000 / months

    @property
    def wear(self) -> float | None:
        if not self.target_distance_m:
            return None
        return self.distance_m / self.target_distance_m

    @property
    def beyond_target(self) -> bool:
        return self.wear is not None and self.wear >= 1


def equipment_usage(
    equipment: list[Equipment],
    activities: list[Activity],
    *,
    default_shoe_target_m: float = DEFAULT_SHOE_TARGET_M,
) -> list[EquipmentStat]:
    """Aggregate sessions and distance per equipment item."""
    by_id: dict[str, dict] = {}

    for activity in activities:
        seen = set()

        for item in activity.equipment:
            if item.id in seen:
                continue
            seen.add(item.id)

            usage = by_id.setdefault(
                item.id,
                {
                    "sessions": 0,
                    "distance_m": 0.0,
                    "first": None,
                    "last": None,
                },
            )
            usage["sessions"] += 1
            usage["distance_m"] += activity.distance_m or 0
            usage["first"] = (
                activity.date
                if usage["first"] is None
                else min(usage["first"], activity.date)
            )
            usage["last"] = (
                activity.date
                if usage["last"] is None
                else max(usage["last"], activity.date)
            )

    stats = []

    for item in equipment:
        usage = by_id.get(item.id, {})
        target = item.target_distance_m

        if target is None and item.type == "shoe":
            target = default_shoe_target_m

        stats.append(
            EquipmentStat(
                equipment=item,
                sessions=usage.get("sessions", 0),
                distance_m=usage.get("distance_m", 0.0),
                first_used=usage.get("first"),
                last_used=usage.get("last"),
                target_distance_m=target,
                target_is_default=(
                    item.target_distance_m is None
                    and item.type == "shoe"
                    and target is not None
                ),
            )
        )

    return sorted(
        stats,
        key=lambda stat: (
            stat.retired,
            -stat.distance_m,
            stat.equipment.name,
        ),
    )


def equipment_coverage(
    activities: list[Activity],
) -> dict[int, tuple[int, int]]:
    """Per year: activities with gear, activities without gear."""
    coverage: dict[int, list[int]] = {}

    for activity in activities:
        counts = coverage.setdefault(activity.date.year, [0, 0])
        counts[0 if activity.equipment else 1] += 1

    return {year: (counts[0], counts[1]) for year, counts in sorted(coverage.items())}


def retirement_candidates(
    stats: list[EquipmentStat],
    today: date,
    *,
    unused_days: int = UNUSED_DAYS,
) -> list[tuple[EquipmentStat, str]]:
    """Active gear beyond target or not used for a year, with the reason."""
    candidates = []
    cutoff = today - timedelta(days=unused_days)

    for stat in stats:
        if stat.retired:
            continue

        reasons = []

        if stat.beyond_target:
            reasons.append(
                f"over target ({stat.distance_m / 1000:.0f} km)"
            )
        if stat.last_used is None:
            reasons.append("never used")
        elif stat.last_used < cutoff:
            reasons.append(f"unused since {stat.last_used}")

        if reasons:
            candidates.append((stat, "; ".join(reasons)))

    return candidates
