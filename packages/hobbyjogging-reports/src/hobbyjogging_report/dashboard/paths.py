"""Relative paths shared by the dashboard's page builders."""

from __future__ import annotations

import re

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _filename(value: str) -> str:
    # Source-scoped ids carry colons (``sheet:equipment:1``); a colon or a
    # percent escape in a file name would not survive a browser's URL
    # decoding, so the name is sanitised rather than percent-quoted.
    return f"{_UNSAFE.sub('-', str(value))}.html"


def activity_filename(activity_id: str) -> str:
    return _filename(activity_id)


def activity_href(activity_id: str) -> str:
    return f"activity/{activity_filename(activity_id)}"


def event_filename(event_id: str) -> str:
    return _filename(event_id)


def event_href(event_id: str) -> str:
    return f"event/{event_filename(event_id)}"


def gear_filename(item_id: str) -> str:
    return _filename(item_id)


def gear_href(item_id: str) -> str:
    return f"gear/{gear_filename(item_id)}"
