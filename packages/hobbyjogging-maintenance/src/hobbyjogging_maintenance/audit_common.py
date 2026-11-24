"""Shared formatting for the historical audit."""

from __future__ import annotations

INJURY_WORDS = frozenset(
    {
        "krank",
        "verkühlt",
        "infekt",
        "magen-darm",
        "fieber",
        "grippe",
        "erkältet",
    }
)
RECOVERED_WORDS = frozenset({"wieder gesund"})
IGNORED_WORDS = frozenset({"schlapp"})
SHEET_AREA_TAGS = frozenset({"w", "m", "wb", "a", "t", "i"})

def cell(value: object) -> str:
    return str(value).replace("|", "/").replace("\n", " ").strip()


def shorten(text: str, limit: int = 80) -> str:
    value = " ".join(str(text).split())
    return value if len(value) <= limit else value[: limit - 1] + "…"
