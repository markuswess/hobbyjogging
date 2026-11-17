"""Recording-device usage and timeline data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.model import Activity, Device

from .common import RUN_TYPES


@dataclass(frozen=True)
class DeviceStat:
    """Activity usage for one recording device."""

    device: Device
    activities: int = 0
    runs: int = 0
    first_used: date | None = None
    last_used: date | None = None

    @property
    def label(self) -> str:
        return self.device.name or self.device.product or self.device.id

    @property
    def product(self) -> str:
        return self.device.product or self.device.name or self.device.id

    @property
    def start(self) -> date | None:
        return self.device.acquired_on or self.first_used

    @property
    def end(self) -> date | None:
        return self.device.retired_on or self.last_used

    @property
    def retired(self) -> bool:
        return self.device.retired_on is not None


def device_usage(
    devices: list[Device],
    activities: list[Activity],
) -> list[DeviceStat]:
    """Aggregate activity counts and date ranges per recording device."""
    by_id: dict[str, dict] = {}

    for activity in activities:
        if not activity.device_id:
            continue

        usage = by_id.setdefault(
            activity.device_id,
            {"activities": 0, "runs": 0, "first": None, "last": None},
        )
        usage["activities"] += 1
        usage["runs"] += 1 if activity.type in RUN_TYPES else 0
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

    stats = [
        DeviceStat(
            device=device,
            activities=by_id.get(device.id, {}).get("activities", 0),
            runs=by_id.get(device.id, {}).get("runs", 0),
            first_used=by_id.get(device.id, {}).get("first"),
            last_used=by_id.get(device.id, {}).get("last"),
        )
        for device in devices
    ]

    return sorted(
        stats,
        key=lambda stat: (
            stat.start or date.min,
            stat.label,
        ),
    )


def device_changes(
    stats: list[DeviceStat],
) -> list[tuple[date, str]]:
    """Dates where a device started recording, oldest first."""
    return sorted(
        (
            (stat.first_used or stat.device.acquired_on, stat.label)
            for stat in stats
            if stat.first_used is not None or stat.device.acquired_on
        ),
        key=lambda change: change[0],
    )
