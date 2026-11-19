"""Provider device names: what is a recorder, how it reads, what it claims.

A provider reports a ``device_name`` that may be the watch model or the app
that uploaded the activity. An app is never a recorder, so it writes no device
row and no ``device_id``. A real name fills the field only when the activity
has no FIT source, and a name that resolves onto exactly one FIT device of its
model claims that device instead of creating a duplicate provider row: the
serial is the identity.
"""

from __future__ import annotations

import sqlite3

from hobbyjogging_core import TrainingWriter

# Names a provider reports for the app, not for a recorder. Evidence-based:
# a name joins this list when a stored payload shows the app writing it.
APP_DEVICE_NAMES = frozenset(
    {
        "runalyze",
        "garminconnect",
        "strava",
        "intervals.icu",
    }
)

DEVICE_PREFIX = "intervals"


def _collapsed(value: object) -> str:
    """Whitespace collapsed; payloads carry leading and trailing spaces."""
    return " ".join(str(value or "").split())


def _alphanumeric(value: object) -> str:
    """Case and separators dropped, so two spellings of one model compare."""
    return "".join(
        character
        for character in _collapsed(value).lower()
        if character.isalnum()
    )


def is_app_device_name(value: object) -> bool:
    """True when the provider name is an app, never a recorder."""
    squashed = _collapsed(value).lower().replace(" ", "")
    return squashed in APP_DEVICE_NAMES


def display_device_name(value: object) -> str:
    """The stored label: whitespace collapsed and title-cased."""
    return " ".join(
        word[:1].upper() + word[1:].lower()
        for word in _collapsed(value).split()
    )


def provider_device_id(value: object) -> str | None:
    """The stable id for a provider-only device, or None for an app."""
    if is_app_device_name(value):
        return None

    text = _collapsed(value).lower()
    if not text:
        return None

    slug = "".join(
        character if character.isalnum() else "-" for character in text
    ).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")

    return f"{DEVICE_PREFIX}:{slug}" if slug else None


def claimed_fit_device(
    connection: sqlite3.Connection,
    value: object,
) -> str | None:
    """The one FIT device of this model, when the name identifies it.

    The comparison ignores case and separators, so ``GARMIN EDGE_540`` and
    ``Garmin Edge 540`` both match the ``garmin``/``edge_540`` row; it does not
    expand abbreviations, so a name and a product that differ in more than
    punctuation stay separate. Two devices of the same model stay ambiguous:
    the provider id is kept and nothing is guessed. A serial-less FIT upload is
    not a device, so it cannot be claimed.
    """
    tokens = _alphanumeric(value)
    if not tokens:
        return None

    rows = connection.execute(
        """
        SELECT id, manufacturer, product
        FROM devices
        WHERE id LIKE 'fit:%' AND serial_number <> ''
        """
    ).fetchall()

    matched = [
        row["id"]
        for row in rows
        if _alphanumeric(f"{row['manufacturer']}{row['product']}") == tokens
    ]
    return matched[0] if len(matched) == 1 else None


def resolve_provider_device(
    connection: sqlite3.Connection,
    writer: TrainingWriter,
    value: object,
) -> str | None:
    """The device id an activity should carry, or None for an app or blank.

    The FIT claim wins over a provider row, so the activity points at the real
    device. Otherwise the provider row is created on first sight and keeps the
    name it was given: a re-import never rewrites ``devices.name``.
    """
    if is_app_device_name(value):
        return None

    claimed = claimed_fit_device(connection, value)
    if claimed is not None:
        return claimed

    device_id = provider_device_id(value)
    if device_id is None:
        return None

    existing = connection.execute(
        "SELECT name FROM devices WHERE id = ?",
        (device_id,),
    ).fetchone()
    if existing is None or not str(existing["name"] or "").strip():
        writer.upsert_device(
            device_id,
            name=display_device_name(value),
        )
    return device_id
