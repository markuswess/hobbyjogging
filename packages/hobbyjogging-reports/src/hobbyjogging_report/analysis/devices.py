"""Recording-device usage and timeline data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.model import Activity, Device

from .common import RUN_TYPES

# FIT stores the product as a short code (``fr645``, ``edge_540``) and leaves
# the name empty, while a provider fallback stores the marketing name only.
# The map turns the codes this athlete's recorders use into the names the
# providers print, so one watch reads the same way whichever source found it.
DEVICE_PRODUCT_LABELS = {
    "fr645": "Forerunner 645",
    "fr945": "Forerunner 945",
    "fr955": "Forerunner 955",
    "fr265": "Forerunner 265",
    "fr965": "Forerunner 965",
    "edge_530": "Edge 530",
    "edge_540": "Edge 540",
    "edge_830": "Edge 830",
    "edge_1030": "Edge 1030",
    "enduro": "Enduro",
    "fenix7": "Fenix 7",
}


def _clean(value: str | None) -> str:
    """Collapse the stray whitespace some provider names carry."""
    return " ".join((value or "").split())


def device_label(device: Device) -> str:
    """A readable device name from either writer's shape.

    FIT writes ``manufacturer``/``product`` (``garmin``/``enduro``) and no
    name; the Intervals/Runalyze fallback writes ``name`` only
    ("Garmin Enduro"). A stored name wins as the provider's own label, and a
    product-only device gets the manufacturer and the product's marketing
    name, so ``garmin``/``enduro`` and ``Garmin Enduro`` read the same.
    """
    name = _clean(device.name)
    if name:
        return name

    product = _clean(device.product)
    if not product:
        return device.id

    text = DEVICE_PRODUCT_LABELS.get(
        product.lower(),
        product.replace("_", " ").title(),
    )
    manufacturer = _clean(device.manufacturer)

    if manufacturer and manufacturer.lower() not in text.lower():
        return f"{manufacturer.title()} {text}"

    return text


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
        return device_label(self.device)

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
