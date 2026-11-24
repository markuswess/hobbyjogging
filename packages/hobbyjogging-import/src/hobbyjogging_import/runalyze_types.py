"""Runalyze's own workout type as a canonical classification signal.

Runalyze stores a per-activity ``type`` object (``name``, ``abbreviation``,
``quality_session``). For an athlete without Intervals, names or RPE, it is
the one reliable signal that a session was structured, long or easy. The
mapping is deliberately small and evidence-based: an unknown type is listed
by the audit, never guessed.

``quality_session`` is a cross-check, not an override: quality is derived
from the canonical sets.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

SOURCE = "runalyze"

# Normalized name/abbreviation -> (methods, targets).
RUNALYZE_TYPE_CLASSES: dict[str, tuple[set[str], set[str]]] = {
    "jogging": ({"continuous"}, {"base"}),
    "jog": ({"continuous"}, {"base"}),
    "subthreshold": ({"intervals"}, {"subthreshold"}),
    "sub_threshold": ({"intervals"}, {"subthreshold"}),
    "sub threshold": ({"intervals"}, {"subthreshold"}),
    "st": ({"intervals"}, {"subthreshold"}),
    "long slow distance": ({"long_run"}, {"base"}),
    "long_slow_distance": ({"long_run"}, {"base"}),
    "lsd": ({"long_run"}, {"base"}),
}


def _normalize(value: object) -> str:
    """Case and separator insensitive, so "Sub-Threshold" matches."""
    text = " ".join(str(value or "").split()).lower()
    return text.replace("-", "_")


def type_tokens(payload: object) -> tuple[str, str]:
    """Return the normalized ``(name, abbreviation)`` of a payload's type."""
    activity_type = payload.get("type") if isinstance(payload, dict) else None
    if not isinstance(activity_type, dict):
        return "", ""
    return (
        _normalize(activity_type.get("name")),
        _normalize(activity_type.get("abbreviation")),
    )


def classification_for_runalyze_type(
    name: object,
    abbreviation: object = "",
) -> tuple[set[str], set[str]]:
    """Map a Runalyze type to method/target sets; unknown is empty."""
    for token in (_normalize(name), _normalize(abbreviation)):
        if token and token in RUNALYZE_TYPE_CLASSES:
            methods, targets = RUNALYZE_TYPE_CLASSES[token]
            return set(methods), set(targets)
    return set(), set()


def classification_for_payload(
    payload: object,
) -> tuple[set[str], set[str]]:
    """Map a stored Runalyze payload's type to method/target sets."""
    name, abbreviation = type_tokens(payload)
    return classification_for_runalyze_type(name, abbreviation)


@dataclass(frozen=True)
class TypeCount:
    """One distinct stored type and what it maps to."""

    name: str
    abbreviation: str
    count: int
    methods: frozenset[str]
    targets: frozenset[str]

    @property
    def mapped(self) -> bool:
        return bool(self.methods or self.targets)

    def proposal(self) -> str:
        if not self.mapped:
            return "unmapped"
        parts = []
        if self.methods:
            parts.append("+".join(sorted(self.methods)))
        if self.targets:
            parts.append("+".join(sorted(self.targets)))
        return " / ".join(parts)


def audit_types(connection: sqlite3.Connection) -> list[TypeCount]:
    """Count the distinct Runalyze types in the stored payloads."""
    counts: dict[tuple[str, str], list[object]] = {}

    for (payload_json,) in connection.execute(
        """
        SELECT payload_json FROM source_records
        WHERE source = ? AND record_type = 'activity'
          AND payload_json IS NOT NULL
        """,
        (SOURCE,),
    ):
        try:
            payload = json.loads(payload_json)
        except (TypeError, ValueError):
            continue
        name, abbreviation = type_tokens(payload)
        if not name and not abbreviation:
            continue
        key = (name, abbreviation)
        entry = counts.get(key)
        if entry is None:
            activity_type = payload.get("type") or {}
            counts[key] = [
                1,
                str(activity_type.get("name") or ""),
                str(activity_type.get("abbreviation") or ""),
            ]
        else:
            entry[0] = int(entry[0]) + 1

    rows = []
    for (name, abbreviation), (count, display_name, display_abbr) in sorted(
        counts.items(),
        key=lambda item: (-int(item[1][0]), item[1][1].lower()),
    ):
        methods, targets = classification_for_runalyze_type(
            name,
            abbreviation,
        )
        rows.append(
            TypeCount(
                name=str(display_name),
                abbreviation=str(display_abbr),
                count=int(count),
                methods=frozenset(methods),
                targets=frozenset(targets),
            )
        )
    return rows


def format_type_audit(rows: list[TypeCount]) -> str:
    if not rows:
        return "Runalyze types: no stored activity payloads carry a type."

    width = max(len(row.name) for row in rows)
    lines = ["Runalyze types (stored payloads):"]
    lines.append(
        f"  {'name':<{width}}  {'abbr':<6}  {'count':>5}  proposal"
    )
    for row in rows:
        lines.append(
            f"  {row.name or '-':<{width}}  "
            f"{row.abbreviation or '-':<6}  "
            f"{row.count:>5}  {row.proposal()}"
        )

    unmapped = [row for row in rows if not row.mapped]
    if unmapped:
        lines.append("")
        lines.append(
            f"Unmapped: {len(unmapped)} type(s). Add a mapping only when "
            "the meaning is known."
        )
    return "\n".join(lines)
