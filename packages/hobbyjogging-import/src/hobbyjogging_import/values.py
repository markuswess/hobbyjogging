"""Parsers and formatters for manually entered activity values.

These accept the terse notation used by the review CLI and triage queue,
e.g. ``46:20`` for a duration or ``8.2km`` for a distance. ``format_field``
formats any activity field for review displays and conflict messages.
"""

from __future__ import annotations

from hobbyjogging_core.sports import canonical_sport


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


def parse_pace_mps(text: str) -> float:
    """Parse a threshold pace as speed in m/s.

    ``4:30`` or ``4:30/km`` is minutes per kilometre; ``3.70mps`` or
    ``3.70m/s`` is a speed. A bare decimal is m/s. The value must be positive.
    """
    raw = text.strip().lower()
    if not raw:
        raise ValueError("pace is empty")

    if raw.endswith("mps"):
        raw = raw[:-3].strip()
    elif raw.endswith("m/s"):
        raw = raw[:-3].strip()
    elif "/km" in raw:
        raw = raw.replace("/km", "").strip()
        seconds = parse_duration_s(raw)
        return 1000.0 / seconds

    if ":" in raw:
        seconds = parse_duration_s(raw)
        return 1000.0 / seconds

    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"invalid pace: {text!r}") from None

    if value <= 0:
        raise ValueError(f"pace must be positive: {text!r}")
    return value


def parse_sport(text: str) -> str:
    """Normalize a sport name like ``trail_running`` to ``trail_run``."""
    normalized = canonical_sport(text)
    if not normalized:
        raise ValueError("sport is empty")
    return normalized


def parse_text(text: str) -> str:
    """Parse a non-empty free-text value, trimmed but otherwise unchanged."""
    value = text.strip()
    if not value:
        raise ValueError("value is empty")
    return value


def parse_rpe(text: str) -> float:
    """Parse a rating of perceived exertion on the 1-10 scale."""
    try:
        value = float(text.strip())
    except ValueError:
        raise ValueError(f"invalid RPE: {text!r}") from None
    if not 1 <= value <= 10:
        raise ValueError("RPE must be between 1 and 10")
    return value


def parse_feel(text: str) -> int:
    """Parse a subjective feel rating on the schema's 1-5 scale."""
    try:
        value = int(text.strip())
    except ValueError:
        raise ValueError(f"invalid feel: {text!r}") from None
    if not 1 <= value <= 5:
        raise ValueError("feel must be between 1 and 5")
    return value


# One prompt/parser table for the review CLI, triage and the edit command.
# Fields without a terse notation are entered literally and use their parser
# directly.
VALUE_PROMPTS = {
    "duration_s": (
        "value (46:20, 1:02:03, or seconds): ",
        parse_duration_s,
    ),
    "distance_m": (
        "value (8.2km, 8200m, or plain km): ",
        parse_distance_m,
    ),
    "sport": (
        "value (e.g. trail_running or mtb_ride): ",
        parse_sport,
    ),
}


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


def format_pace(duration_s: float | None, distance_m: float | None) -> str:
    """Format pace as ``M:SS /km``."""
    if not duration_s or not distance_m:
        return "-"
    seconds_per_km = float(duration_s) / (float(distance_m) / 1000.0)
    minutes, seconds = divmod(int(round(seconds_per_km)), 60)
    return f"{minutes}:{seconds:02d} /km"


def format_speed(duration_s: float | None, distance_m: float | None) -> str:
    """Format average speed as ``KM/H``."""
    if not duration_s or not distance_m:
        return "-"
    speed_kmh = (float(distance_m) / 1000.0) / (float(duration_s) / 3600.0)
    return f"{speed_kmh:.1f} km/h"


def _format_hr(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):.0f} bpm"


def _format_rating(value) -> str:
    if value is None:
        return "-"
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


FORMATTERS = {
    "duration_s": format_duration_s,
    "elapsed_s": format_duration_s,
    "distance_m": format_distance_m,
    "sport": str,
    "avg_hr": _format_hr,
    "rpe": _format_rating,
    "feel": _format_rating,
}
