"""Resolve the sheet's ``Strecke`` / ``Streckennummer`` into a route identity.

``Streckennummer`` is the stable key, so a numbered row is identified by its
number. A name-only row is resolved through the numbers seen for the same name
elsewhere in the sheet (``Kaserne`` is number 6 for most rows); when the name
has no single number, or several, the name itself is the key. A name that is a
Gmap URL is not a route.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .sheet import SOURCE, as_float, clean_text

URL_PREFIXES = ("http://", "https://")


@dataclass(frozen=True)
class RouteIdentity:
    """One canonical route resolved from a sheet row."""

    id: str
    external_ref: str
    name: str


def route_number(value: object) -> str | None:
    """Return a stable text form of a ``Streckennummer`` cell."""
    number = as_float(value)
    if number is None:
        return None
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:g}"


def numbers_by_name(
    rows: Iterable[tuple[object, object]],
) -> dict[str, set[str]]:
    """Map each case-folded route name to the numbers seen with it."""
    result: dict[str, set[str]] = {}
    for name, number in rows:
        text = clean_text(name)
        ref = route_number(number)
        if not text or ref is None or _is_url(text):
            continue
        result.setdefault(text.casefold(), set()).add(ref)
    return result


def route_identity(
    name: object,
    number: object,
    known: dict[str, set[str]] | None = None,
) -> RouteIdentity | None:
    """Resolve one row's route, or ``None`` when it names no usable route."""
    text = clean_text(name)
    if not text or _is_url(text):
        return None

    ref = route_number(number)
    if ref is None:
        candidates = (known or {}).get(text.casefold(), set())
        if len(candidates) == 1:
            ref = next(iter(candidates))
        else:
            ref = f"name:{_name_key(text)}"

    return RouteIdentity(
        id=f"{SOURCE}:route:{ref}",
        external_ref=ref,
        name=text,
    )


def _is_url(text: str) -> bool:
    return text.lower().startswith(URL_PREFIXES)


def _name_key(text: str) -> str:
    return "-".join(text.casefold().split())
