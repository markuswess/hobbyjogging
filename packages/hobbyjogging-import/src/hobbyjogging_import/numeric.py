"""Small numeric coercions for raw source payloads."""

from __future__ import annotations


def number(value: object) -> float | None:
    """Return ``value`` as a float, or ``None`` when it is not numeric.

    Booleans are rejected even though they are integers in Python.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
