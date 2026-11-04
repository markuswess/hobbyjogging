"""Parsers and formatters for manually entered activity values.

These accept the terse notation used by the review CLI and triage queue,
e.g. ``46:20`` for a duration or ``8.2km`` for a distance. ``format_field``
formats any activity field for review displays and conflict messages.
"""

from __future__ import annotations

from .fit import canonical_sport


def format_field(field_name: str, value: object) -> str:
    """Render one activity field's value for a human-readable line."""
    formatter = FORMATTERS.get(field_name)
    if formatter is not None:
        return formatter(value)
    if value is None:
        return "-"
    return str(value)


def parse_duration_s(text: str) -> float:
    """Parse a duration in seconds from ``46:20``, ``1:02:03``, or ``2780``.

    Plain numbers are seconds; colon-separated values are h:mm:ss or mm:ss.
    The value must be positive.
    """
    raw = text.strip()
    if not raw:
        raise ValueError("duration is empty")

    parts = raw.split(":")
    if len(parts) > 3:
        raise ValueError(f"invalid duration: {text!r}")

    seconds = 0.0
    for part in parts:
        try:
            value = float(part)
        except ValueError:
            raise ValueError(
                f"invalid duration component {part!r} in {text!r}"
            ) from None
        seconds = seconds * 60 + value

    if seconds <= 0:
        raise ValueError(f"duration must be positive: {text!r}")

    return seconds


def parse_distance_m(text: str) -> float:
    """Parse a distance in meters from ``8.2km``, ``8200m``, or ``8.2``.

    A plain number is kilometers. The value must be positive.
    """
    raw = text.strip().lower()
    if not raw:
        raise ValueError("distance is empty")

    try:
        if raw.endswith("km"):
            value = float(raw[:-2]) * 1000.0
        elif raw.endswith("m"):
            value = float(raw[:-1])
        else:
            value = float(raw) * 1000.0
    except ValueError:
        raise ValueError(f"invalid distance: {text!r}") from None

    if value <= 0:
        raise ValueError(f"distance must be positive: {text!r}")

    return value


def parse_sport(text: str) -> str:
    """Normalize a sport name like ``trail_running`` to ``trail_run``."""
    normalized = canonical_sport(text)
    if not normalized:
        raise ValueError("sport is empty")
    return normalized


def format_duration_s(seconds: float | None) -> str:
    """Format seconds as ``46:20`` or, past one hour, ``1:02:03``."""
    if seconds is None:
        return "-"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_distance_m(meters: float | None) -> str:
    """Format meters as kilometers with two decimals."""
    if meters is None:
        return "-"
    return f"{meters / 1000:.2f} km"


def _format_hr(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):.0f} bpm"


FORMATTERS = {
    "duration_s": format_duration_s,
    "elapsed_s": format_duration_s,
    "distance_m": format_distance_m,
    "sport": str,
    "avg_hr": _format_hr,
}
