"""Mapping from the historical training log spreadsheet to canonical values.

The spreadsheet stores German column names and ODS types: dates are ``date``
cells, clock times and durations are ``timedelta`` cells, and numbers are
``float`` cells. This module turns one row into canonical activity or
equipment values; the importer in :mod:`sheet_import` handles source records,
matching, and review items.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from hobbyjogging_core.sports import canonical_sport, normalize_token

SOURCE = "sheet"
DEFAULT_TIMEZONE = "Europe/Vienna"

ROHDATEN = "Rohdaten"
ALTERNATIVTRAINING = "Alternativtraining"
MATERIAL = "Material"
SUPPORTED_SHEETS = (ROHDATEN, ALTERNATIVTRAINING, MATERIAL)

MISSING_MARKERS = frozenset(
    {"/", "n/a", "#ref!", "#n/a", "-", "–", "—", "?"}
)

# Cross-training labels that name a canonical sport. Everything else in the
# sheet's "Was" column becomes the generic "other".
ALTERNATIVE_SPORT_TOKENS = frozenset(
    {
        "kicken",
        "badminton",
        "padel",
        "tischtennis",
        "radfahren",
        "lastenrad",
        "mountainbike",
        "schwimmen",
        "wandern",
        "laufband",
        "kraft",
        "sup",
    }
)


@dataclass(frozen=True)
class EquipmentRow:
    """Canonical equipment values parsed from one Material row."""

    equipment_id: str
    type: str
    name: str
    brand: str
    model: str
    acquired_on: date | None
    retired_on: date | None
    notes: str


def is_missing(value: object) -> bool:
    """True for empty cells and the sheet's textual placeholders."""
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip().lower()
        return not text or text in MISSING_MARKERS
    return False


def clean_text(value: object) -> str:
    """Return stripped text, or an empty string for missing markers."""
    if is_missing(value):
        return ""
    return str(value).strip()


def as_float(value: object) -> float | None:
    """Return a numeric cell as float, or None."""
    if is_missing(value):
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def as_seconds(value: object) -> float | None:
    """Return an ODS duration cell as seconds."""
    if is_missing(value):
        return None
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        hours, minutes, seconds = (float(part) for part in text.split(":"))
    except ValueError:
        return None
    return hours * 3600 + minutes * 60 + seconds


def as_date(value: object) -> date | None:
    """Return a date cell (or an ISO date string) as a date."""
    if is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def as_clock(value: object) -> time | None:
    """Return a clock cell as a time of day.

    ODS stores clock times as durations since midnight; hand-entered strings
    such as ``06:43`` or ``8;19`` are accepted too.
    """
    if is_missing(value):
        return None
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds()) % (24 * 3600)
        return time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)
    text = str(value).strip().replace(";", ":")
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return time(hour, minute)


def german_date(value: object) -> date | None:
    """Parse a ``D.M.YYYY`` cell from the equipment sheet."""
    text = clean_text(value)
    if not text:
        return None
    parts = text.split(".")
    if len(parts) != 3:
        return None
    try:
        day, month, year = (int(part) for part in parts)
    except ValueError:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def local_start(
    day: date,
    clock: time,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> tuple[str, int]:
    """Return UTC text and the local offset in minutes for a wall clock."""
    local = datetime.combine(day, clock, tzinfo=ZoneInfo(timezone_name))
    utc = local.astimezone(timezone.utc)
    offset = local.utcoffset() or timedelta(0)
    return (
        utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        int(offset.total_seconds() // 60),
    )


def row_record(
    headers: list[object],
    row: list[object],
    *,
    blank_names: dict[int, str] | None = None,
) -> dict[str, object]:
    """Key one row by its header, dropping empty headers and markers."""
    record: dict[str, object] = {}
    for index, header in enumerate(headers):
        if not isinstance(header, str) or not header.strip():
            header = (blank_names or {}).get(index)
            if not header:
                continue
        value = row[index] if index < len(row) else None
        if is_missing(value):
            continue
        record[header.strip()] = value
    return record


def rohdaten_values(
    record: dict[str, object],
    *,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> tuple[dict[str, object], list[str], object | None]:
    """Map a Rohdaten row to activity values, tags, and the shoe reference."""
    day = as_date(record.get("Datum"))
    if day is None:
        raise ValueError("Rohdaten row has no date")

    duration_s = as_seconds(record.get("Zeit")) or 0.0
    values: dict[str, object] = {
        "local_date": day.isoformat(),
        "sport": "run",
        "duration_s": duration_s,
        "elapsed_s": duration_s,
        "distance_m": as_float(record.get("Distanz in m")) or 0.0,
    }

    name = clean_text(record.get("Strecke"))
    if name:
        values["name"] = name
    description = clean_text(record.get("Beschreibung"))
    if description:
        values["description"] = description

    avg_hr = as_float(record.get("d. Hf"))
    if avg_hr is not None:
        values["avg_hr"] = avg_hr

    clock = as_clock(record.get("Startzeit"))
    if clock is not None:
        started_at, offset = local_start(day, clock, timezone_name)
        values["started_at_utc"] = started_at
        values["tz_offset_min"] = offset

    tags = [
        tag
        for tag in (
            clean_text(record.get("Trainigstyp")),
            clean_text(record.get("Trainingsgebiet")),
        )
        if tag
    ]
    shoe = record.get("Schuhe")
    return values, tags, None if is_missing(shoe) else shoe


def alternativtraining_values(
    record: dict[str, object],
    *,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> dict[str, object]:
    """Map an Alternativtraining row to canonical activity values."""
    day = as_date(record.get("Datum"))
    if day is None:
        raise ValueError("Alternativtraining row has no date")

    distance_km = as_float(record.get("Distanz"))
    duration_s = as_seconds(record.get("Zeit")) or 0.0
    values: dict[str, object] = {
        "local_date": day.isoformat(),
        "sport": _alternative_sport(record.get("Was")),
        "duration_s": duration_s,
        "elapsed_s": duration_s,
        "distance_m": (distance_km or 0.0) * 1000.0,
    }

    name = clean_text(record.get("Was"))
    if name:
        values["name"] = name
    description = clean_text(record.get("Beschreibung"))
    if description:
        values["description"] = description

    avg_hr = as_float(record.get("Puls Durchschnitt"))
    if avg_hr is not None:
        values["avg_hr"] = avg_hr

    clock = as_clock(record.get("Uhrzeit"))
    if clock is not None:
        started_at, offset = local_start(day, clock, timezone_name)
        values["started_at_utc"] = started_at
        values["tz_offset_min"] = offset

    return values


def equipment_id(value: object) -> str | None:
    """Return the stable equipment id for a Material id cell."""
    if is_missing(value):
        return None
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = clean_text(value)
    return f"sheet:equipment:{text}" if text else None


def equipment_values(record: dict[str, object]) -> EquipmentRow:
    """Map one Material row to canonical equipment values."""
    stable_id = equipment_id(record.get("Id"))
    if stable_id is None:
        raise ValueError("Material row has no id")

    brand = clean_text(record.get("Marke"))
    model = clean_text(record.get("Typ"))
    name = " ".join(part for part in (brand, model) if part) or stable_id
    colour = clean_text(record.get("Farbe"))

    notes = []
    size = clean_text(record.get("Größe"))
    if size:
        notes.append(f"Größe {size}")
    price = as_float(record.get("Kaufpreis"))
    if price is not None:
        notes.append(f"Preis {price:g}")
    mileage = as_float(record.get("gesamt km"))
    if mileage is not None:
        notes.append(f"gesamt {mileage:g} km")
    if colour:
        notes.append(f"Farbe {colour}")
    remarks = clean_text(record.get("Bemerkungen"))
    if remarks:
        notes.append(remarks)

    return EquipmentRow(
        equipment_id=stable_id,
        type="shoe",
        name=name,
        brand=brand,
        model=model,
        acquired_on=german_date(record.get("Kaufdatum")),
        retired_on=german_date(record.get("Entsorgungsdatum")),
        notes="; ".join(notes),
    )


def row_payload(
    sheet_name: str,
    row_number: int,
    record: dict[str, object],
) -> str:
    """Serialize a raw row for ``source_records.payload_json``."""
    return json.dumps(
        {
            "sheet": sheet_name,
            "row": row_number,
            "values": record,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _alternative_sport(value: object) -> str:
    token = normalize_token(value)
    if token in ALTERNATIVE_SPORT_TOKENS:
        return canonical_sport(value)
    return "other"
