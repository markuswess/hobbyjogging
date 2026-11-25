"""Shared formatting for the historical audit."""

from __future__ import annotations


def cell(value: object) -> str:
    return str(value).replace("|", "/").replace("\n", " ").strip()


def shorten(text: str, limit: int = 80) -> str:
    value = " ".join(str(text).split())
    return value if len(value) <= limit else value[: limit - 1] + "…"
