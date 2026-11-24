"""Derive canonical activity values from a source payload.

The maps are the declared part: canonical field -> payload key(s). The
transforms are the named exceptions (units, sport vocabulary, dates, the FIT
device id). ``verify_canonical`` and the future rebuild read this, and a
contract test asserts each map reproduces what its importer writes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from hobbyjogging_core.sports import canonical_sport

from .devices import provider_device_id
from .fit_import import device_id_from
from .intervals import (
    _fraction,
    _int,
    _tz_offset_min,
)
from .sheet import (
    DEFAULT_TIMEZONE,
    _alternative_sport,
    as_clock,
    as_date,
    as_float,
    as_seconds,
    clean_text,
    local_start,
)


class Unmapped(Exception):
    """The source has no declared mapping for this field."""


@dataclass(frozen=True)
class FieldSpec:
    """One canonical field's payload keys and transform."""

    keys: tuple[str, ...] = ()
    transform: Callable[[dict, object], object] | None = None
    default: object = None
    # Duration-like fields treat a zero as absent and try the next key.
    skip_falsy: bool = False


def _get(payload: dict, path: str) -> object:
    # A literal key wins, so sheet headers such as "d. Hf" stay intact.
    if path in payload:
        return payload[path]
    current: object = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _derive(spec: FieldSpec, payload: dict) -> object:
    if not spec.keys:
        return spec.transform(payload, None) if spec.transform else spec.default

    for key in spec.keys:
        value = _get(payload, key)
        if value is None or value == "":
            continue
        if spec.skip_falsy and value == 0:
            continue
        return spec.transform(payload, value) if spec.transform else value
    return spec.default


# -- named transforms ------------------------------------------------------


def _as_str(payload: dict, value: object) -> str:
    return str(value or "")


def _as_float(payload: dict, value: object) -> float:
    return float(value)


def _as_int(payload: dict, value: object) -> int:
    return int(float(value))


def _date_prefix(payload: dict, value: object) -> str | None:
    text = str(value or "")
    return text[:10] if len(text) >= 10 else None


def _sport(payload: dict, value: object) -> str:
    return canonical_sport(value)


def _fraction_of_100(payload: dict, value: object) -> float | None:
    return _fraction(value)


def _offset_minutes(payload: dict, value: object) -> int | None:
    return _tz_offset_min(payload)


def _intervals_device(payload: dict, value: object) -> str | None:
    return provider_device_id(value)


def _fit_sub_sport(payload: dict, value: object) -> str | None:
    text = str(value or "")
    return text if text and text != "generic" else None


def _fit_device_id(payload: dict, value: object) -> str | None:
    file = payload.get("file") or {}
    return device_id_from(
        file.get("manufacturer"),
        file.get("product"),
        file.get("serial_number"),
    )


def _sheet_date(payload: dict, value: object) -> str | None:
    day = as_date(value)
    return day.isoformat() if day is not None else None


def _sheet_seconds(payload: dict, value: object) -> float:
    return as_seconds(value) or 0.0


def _sheet_clean(payload: dict, value: object) -> str:
    return clean_text(value)


def _sheet_start(payload: dict, value: object) -> str | None:
    day = as_date(payload.get("Datum"))
    clock = as_clock(value)
    if day is None or clock is None:
        return None
    return local_start(day, clock, DEFAULT_TIMEZONE)[0]


def _sheet_offset(payload: dict, value: object) -> int | None:
    day = as_date(payload.get("Datum"))
    clock = as_clock(value)
    if day is None or clock is None:
        return None
    return local_start(day, clock, DEFAULT_TIMEZONE)[1]


def _sheet_km_to_m(payload: dict, value: object) -> float:
    return (as_float(value) or 0.0) * 1000.0


def _sheet_run(payload: dict, value: object) -> str:
    return "run"


def _sheet_alternative_sport(payload: dict, value: object) -> str:
    return _alternative_sport(value)


def _runalyze_start(payload: dict, value: object) -> str | None:
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _runalyze_sport(payload: dict, value: object) -> str:
    name = value.get("name") if isinstance(value, dict) else value
    return canonical_sport(name)


def _km_to_m(payload: dict, value: object) -> float:
    return float(value) * 1000.0


# -- the declared maps -----------------------------------------------------


FIELD_MAPS: dict[str, dict[str, FieldSpec]] = {
    "intervals": {
        "local_date": FieldSpec(
            ("start_date_local", "start_date"), _date_prefix
        ),
        "started_at_utc": FieldSpec(("start_date",), _as_str),
        "tz_offset_min": FieldSpec((), _offset_minutes),
        "sport": FieldSpec(("type",), _sport),
        "name": FieldSpec(("name",), _as_str, ""),
        "description": FieldSpec(("description",), _as_str, ""),
        "duration_s": FieldSpec(
            ("icu_recording_time", "moving_time"),
            _as_float,
            0.0,
            skip_falsy=True,
        ),
        "elapsed_s": FieldSpec(("elapsed_time",), _as_float, 0.0),
        "moving_s": FieldSpec(("moving_time",), _as_float),
        "distance_m": FieldSpec(("distance",), _as_float, 0.0),
        "avg_hr": FieldSpec(("average_heartrate",), _as_float),
        "max_hr": FieldSpec(("max_heartrate",), _as_float),
        "elevation_gain_m": FieldSpec(("total_elevation_gain",), _as_float),
        "elevation_loss_m": FieldSpec(("total_elevation_loss",), _as_float),
        "training_load": FieldSpec(("icu_training_load",), _as_float),
        "rpe": FieldSpec(("icu_rpe",), _as_float),
        "feel": FieldSpec(("feel",), _as_int),
        "intensity": FieldSpec(("icu_intensity",), _fraction_of_100),
        "sub_sport": FieldSpec(("sub_type",), _as_str),
        "device_id": FieldSpec(("device_name",), _intervals_device),
    },
    "fit": {
        "local_date": FieldSpec(("session.local_start",), _date_prefix),
        "started_at_utc": FieldSpec(("session.start_time_utc",), _as_str),
        "tz_offset_min": FieldSpec(("session.tz_offset_min",), _as_int),
        "sport": FieldSpec(("session.canonical_sport",), _as_str),
        "name": FieldSpec(("session.name",), _as_str, ""),
        "duration_s": FieldSpec(("session.duration_s",), _as_float),
        "elapsed_s": FieldSpec(("session.elapsed_s",), _as_float),
        "moving_s": FieldSpec(("session.moving_s",), _as_float),
        "distance_m": FieldSpec(("session.distance_m",), _as_float),
        "avg_hr": FieldSpec(("session.avg_hr",), _as_float),
        "max_hr": FieldSpec(("session.max_hr",), _as_float),
        "elevation_gain_m": FieldSpec(("session.ascent_m",), _as_float),
        "elevation_loss_m": FieldSpec(("session.descent_m",), _as_float),
        "vo2max_garmin": FieldSpec(("session.vo2max_garmin",), _as_float),
        "sub_sport": FieldSpec(("session.sub_sport",), _fit_sub_sport),
        "device_id": FieldSpec((), _fit_device_id),
    },
    "runalyze": {
        "local_date": FieldSpec(("date_time",), _date_prefix),
        "started_at_utc": FieldSpec(("date_time",), _runalyze_start),
        "tz_offset_min": FieldSpec(("timezone_offset",), _as_int),
        "sport": FieldSpec(("sport",), _runalyze_sport),
        "duration_s": FieldSpec(("duration",), _as_float),
        "elapsed_s": FieldSpec(("elapsed_time",), _as_float),
        "distance_m": FieldSpec(("distance",), _km_to_m, 0.0),
        "avg_hr": FieldSpec(("hr_avg",), _as_float),
        "max_hr": FieldSpec(("hr_max",), _as_float),
        "description": FieldSpec(("note",), _as_str, ""),
        "training_load": FieldSpec(
            ("fit_trimp", "trimp"),
            _as_float,
            skip_falsy=True,
        ),
        "vo2max_runalyze": FieldSpec(("vo2max",), _as_float),
    },
    # Strava writes social text and gear; a create uses the manifest fields.
    "strava": {
        "local_date": FieldSpec(("date",), _date_prefix),
        "started_at_utc": FieldSpec(("started_at_utc",), _as_str),
        "tz_offset_min": FieldSpec(("tz_offset_min",), _as_int),
        "sport": FieldSpec(("sport",), _sport),
        "name": FieldSpec(("name",), _as_str, ""),
        "description": FieldSpec(("description",), _as_str, ""),
        "duration_s": FieldSpec(
            ("moving_s", "elapsed_s"),
            _as_float,
            0.0,
            skip_falsy=True,
        ),
        "elapsed_s": FieldSpec(("elapsed_s",), _as_float, 0.0),
        "moving_s": FieldSpec(("moving_s",), _as_float),
        "distance_m": FieldSpec(("distance_m",), _as_float, 0.0),
        "avg_hr": FieldSpec(("avg_hr",), _as_float),
        "max_hr": FieldSpec(("max_hr",), _as_float),
        "elevation_gain_m": FieldSpec(("elevation_gain_m",), _as_float),
    },
}


SHEET_MAPS: dict[str, dict[str, FieldSpec]] = {
    "Rohdaten": {
        "local_date": FieldSpec(("Datum",), _sheet_date),
        "started_at_utc": FieldSpec(("Startzeit",), _sheet_start),
        "tz_offset_min": FieldSpec(("Startzeit",), _sheet_offset),
        "sport": FieldSpec((), _sheet_run),
        "name": FieldSpec(("Strecke",), _sheet_clean, ""),
        "description": FieldSpec(("Beschreibung",), _sheet_clean, ""),
        "duration_s": FieldSpec(("Zeit",), _sheet_seconds, 0.0),
        "elapsed_s": FieldSpec(("Zeit",), _sheet_seconds, 0.0),
        "distance_m": FieldSpec(("Distanz in m",), _as_float, 0.0),
        "avg_hr": FieldSpec(("d. Hf",), _as_float),
        "max_hr": FieldSpec(("max. Hf",), _as_float),
        "elevation_gain_m": FieldSpec(("m bergauf",), _as_float),
    },
    "Alternativtraining": {
        "local_date": FieldSpec(("Datum",), _sheet_date),
        "started_at_utc": FieldSpec(("Uhrzeit",), _sheet_start),
        "tz_offset_min": FieldSpec(("Uhrzeit",), _sheet_offset),
        "sport": FieldSpec(("Was",), _sheet_alternative_sport),
        "name": FieldSpec(("Was",), _sheet_clean, ""),
        "description": FieldSpec(("Beschreibung",), _sheet_clean, ""),
        "duration_s": FieldSpec(("Zeit",), _sheet_seconds, 0.0),
        "elapsed_s": FieldSpec(("Zeit",), _sheet_seconds, 0.0),
        "distance_m": FieldSpec(("Distanz",), _sheet_km_to_m, 0.0),
        "avg_hr": FieldSpec(("Puls Durchschnitt",), _as_float),
    },
}


def _specs(source: str, payload: dict) -> tuple[dict[str, FieldSpec], dict]:
    if source == "sheet":
        sheet = str(payload.get("sheet") or "")
        record = payload.get("values") or {}
        return SHEET_MAPS.get(sheet, {}), record
    return FIELD_MAPS.get(source, {}), payload


def derive_values(source: str, payload: dict) -> dict[str, object]:
    """Every mapped field's value from one payload."""
    specs, record = _specs(source, payload)
    return {field: _derive(spec, record) for field, spec in specs.items()}


def derive_value(source: str, field: str, payload: dict) -> object:
    """One mapped field's value, or Unmapped for a source without a spec."""
    specs, record = _specs(source, payload)
    spec = specs.get(field)
    if spec is None:
        raise Unmapped(f"{source} has no mapping for {field}")
    return _derive(spec, record)
