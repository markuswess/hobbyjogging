"""Extract canonical session-average metrics from source payloads.

The stored row is source-independent and in canonical units. FIT payloads are
already normalized by :mod:`hobbyjogging_import.fit`; the other sources are
mapped here so the importers and the backfill share one table of units.

Run cadence is reported one-leg (rpm) by FIT, Intervals and Runalyze, while
the sheet writes steps/min. A run value at or below 120 is therefore treated
as one-leg and doubled; rides keep their rpm unchanged.
"""

from __future__ import annotations

from hobbyjogging_core.import_rules import METRIC_FIELDS
from hobbyjogging_core.sports import RIDE_SPORTS, RUN_SPORTS


def derive_metrics(
    source: str,
    payload: dict,
    sport: str,
) -> dict[str, float]:
    """Return the non-null canonical metrics for one source payload."""
    if source == "fit":
        values = _fit(payload)
    elif source == "intervals":
        values = _intervals(payload, sport)
    elif source == "runalyze":
        values = _runalyze(payload, sport)
    elif source == "sheet":
        values = _sheet(payload, sport)
    else:
        return {}

    return {
        field: values[field]
        for field in METRIC_FIELDS
        if values.get(field) is not None
    }


# -- per source ----------------------------------------------------------


def _fit(payload: dict) -> dict[str, float | None]:
    session = payload.get("session") or {}
    if not isinstance(session, dict):
        return {}
    return {
        "cadence": _positive(session.get("cadence")),
        "stride_m": _positive(session.get("stride_m")),
        "vertical_oscillation_mm": _positive(
            session.get("vertical_oscillation_mm")
        ),
        "stance_time_ms": _positive(session.get("stance_time_ms")),
        "stance_time_pct": _positive(session.get("stance_time_pct")),
        "stance_balance_pct": _positive(session.get("stance_balance_pct")),
        "vertical_ratio_pct": _positive(
            session.get("vertical_ratio_pct")
        ),
        "respiration_bpm": _positive(session.get("respiration_bpm")),
        "power_w": _positive(session.get("power_w")),
        "calories_kcal": _positive(session.get("calories")),
        "training_effect": _positive(session.get("training_effect")),
    }


def _intervals(payload: dict, sport: str) -> dict[str, float | None]:
    stride = _first(
        _positive(payload.get("average_stride")),
        _mm_to_m(payload.get("average_step_length")),
    )
    return {
        "cadence": _cadence(sport, payload.get("average_cadence")),
        "stride_m": stride,
        "vertical_oscillation_mm": _positive(
            payload.get("average_vertical_oscillation")
        ),
        "stance_time_ms": _positive(payload.get("average_stance_time")),
        "stance_time_pct": _positive(
            payload.get("average_stance_time_percent")
        ),
        "stance_balance_pct": _positive(
            payload.get("average_stance_time_balance")
        ),
        "vertical_ratio_pct": _positive(
            payload.get("average_vertical_ratio")
        ),
        "calories_kcal": _positive(payload.get("calories")),
        "training_effect": _positive(payload.get("AerobicEffect")),
        "gap_mps": _positive(payload.get("gap")),
        "altitude_avg_m": _number(payload.get("average_altitude")),
        "altitude_min_m": _number(payload.get("min_altitude")),
        "altitude_max_m": _number(payload.get("max_altitude")),
    }


def _runalyze(payload: dict, sport: str) -> dict[str, float | None]:
    gap_kmh = _first(payload.get("gap"), payload.get("x_gap"))
    return {
        "cadence": _cadence(sport, payload.get("cadence")),
        "stride_m": _cm_to_m(payload.get("stride_length")),
        "vertical_oscillation_mm": _positive(
            payload.get("vertical_oscillation")
        ),
        "stance_time_ms": _positive(payload.get("groundcontact")),
        "stance_balance_pct": _hundredths(
            payload.get("groundcontact_balance")
        ),
        "vertical_ratio_pct": _tenths(payload.get("vertical_ratio")),
        "respiration_bpm": _positive(payload.get("avg_respiratory_rate")),
        "power_w": _positive(payload.get("power")),
        "calories_kcal": _positive(payload.get("kcal")),
        "training_effect": _positive(payload.get("fit_training_effect")),
        "gap_mps": _kmh_to_mps(gap_kmh),
    }


def _sheet(payload: dict, sport: str) -> dict[str, float | None]:
    values = payload.get("values") or {}
    if not isinstance(values, dict):
        return {}
    return {
        "cadence": _cadence(sport, values.get("Schrittfrequenz")),
        "vertical_oscillation_mm": _cm_to_mm(
            values.get("Vertikale Oszillation")
        ),
        "stance_time_ms": _positive(values.get("Bodenkontaktzeit")),
        "vertical_ratio_pct": _positive(
            values.get("Horizontal/Vertikal")
        ),
    }


# -- units ---------------------------------------------------------------


def _cadence(sport: str, value: object) -> float | None:
    number = _positive(value)
    if number is None:
        return None
    if sport not in RUN_SPORTS and sport not in RIDE_SPORTS:
        return None
    if sport in RUN_SPORTS and number <= 120:
        return number * 2
    return number


def _mm_to_m(value: object) -> float | None:
    number = _positive(value)
    return number / 1000.0 if number is not None else None


def _cm_to_m(value: object) -> float | None:
    number = _positive(value)
    return number / 100.0 if number is not None else None


def _cm_to_mm(value: object) -> float | None:
    number = _positive(value)
    return number * 10.0 if number is not None else None


def _tenths(value: object) -> float | None:
    number = _positive(value)
    return number / 10.0 if number is not None else None


def _hundredths(value: object) -> float | None:
    number = _positive(value)
    return number / 100.0 if number is not None else None


def _kmh_to_mps(value: object) -> float | None:
    number = _positive(value)
    return number / 3.6 if number is not None else None


def _first(*values: object) -> object:
    for value in values:
        if value is not None:
            return value
    return None


def _positive(value: object) -> float | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return number


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
