"""The manual overlay: export and re-apply the athlete's decisions.

The raw payloads and the SQLite file are already durable; this JSONL layer
protects the *meaning* those files cannot carry on their own — which values
were overridden, which sessions were excluded, which review items were
answered. It is not a database dump and it is not a backup.

One JSON object per line, sorted and diffable. The first line is a version
header. ``import_manual`` applies the file to a target that already has the
raw/structural layer (activities, source records, links, pointers, equipment).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, TextIO

from hobbyjogging_core import TrainingWriter

OVERLAY_VERSION = 1

KINDS = (
    "manual_field",
    "workout",
    "tags",
    "equipment",
    "exclusion",
    "review",
)

# Exclusions first, review answers last, so a hand-edited file is safe.
_APPLY_ORDER = {
    "manual_field": 0,
    "workout": 1,
    "tags": 2,
    "equipment": 3,
    "exclusion": 4,
    "review": 5,
}


@dataclass
class OverlayCounts:
    """What an export or import saw."""

    manual_fields: int = 0
    owner_patches: int = 0
    workout_sets: int = 0
    tag_sets: int = 0
    equipment_links: int = 0
    exclusions: int = 0
    review_answers: int = 0
    skipped_excluded: int = 0

    @property
    def records(self) -> int:
        return (
            self.manual_fields
            + self.owner_patches
            + self.workout_sets
            + self.tag_sets
            + self.equipment_links
            + self.exclusions
            + self.review_answers
        )


def overlay_header() -> dict:
    return {"kind": "overlay", "version": OVERLAY_VERSION}


def iter_overlay(connection: sqlite3.Connection) -> Iterator[dict]:
    """Yield the overlay records in a stable, human-readable order."""
    yield overlay_header()

    for row in connection.execute(
        """
        SELECT activity_id, field_name, value_json, owner_source, note
        FROM activity_manual_fields
        ORDER BY activity_id, field_name
        """
    ):
        record = {
            "kind": "manual_field",
            "activity": row["activity_id"],
            "field": row["field_name"],
        }
        if row["owner_source"] is not None:
            record["owner"] = row["owner_source"]
            record["value"] = None
        else:
            record["owner"] = None
            try:
                record["value"] = json.loads(row["value_json"])
            except (TypeError, ValueError):
                raise ValueError(
                    f"{row['activity_id']} {row['field_name']}: "
                    "invalid value_json"
                ) from None
        if row["note"]:
            record["note"] = row["note"]
        yield record

    methods: dict[str, list[str]] = {}
    for row in connection.execute(
        """
        SELECT activity_id, method FROM activity_workout_methods
        WHERE is_manual = 1
        ORDER BY activity_id, method
        """
    ):
        methods.setdefault(row["activity_id"], []).append(row["method"])

    targets: dict[str, list[str]] = {}
    for row in connection.execute(
        """
        SELECT activity_id, target FROM activity_workout_targets
        WHERE is_manual = 1
        ORDER BY activity_id, target
        """
    ):
        targets.setdefault(row["activity_id"], []).append(row["target"])

    for activity_id in sorted(methods):
        yield {
            "kind": "workout",
            "activity": activity_id,
            "methods": methods[activity_id],
        }
    for activity_id in sorted(targets):
        yield {
            "kind": "workout",
            "activity": activity_id,
            "targets": targets[activity_id],
        }

    tags: dict[str, list[str]] = {}
    for row in connection.execute(
        """
        SELECT activity_id, tag FROM activity_tags
        WHERE is_manual = 1
        ORDER BY activity_id, tag
        """
    ):
        tags.setdefault(row["activity_id"], []).append(row["tag"])
    for activity_id in sorted(tags):
        yield {
            "kind": "tags",
            "activity": activity_id,
            "tags": tags[activity_id],
        }

    for row in connection.execute(
        """
        SELECT activity_id, equipment_id, role FROM activity_equipment
        WHERE is_manual = 1
        ORDER BY activity_id, role, equipment_id
        """
    ):
        yield {
            "kind": "equipment",
            "activity": row["activity_id"],
            "equipment": row["equipment_id"],
            "role": row["role"],
        }

    for row in connection.execute(
        """
        SELECT id FROM activities
        WHERE excluded_at IS NOT NULL
        ORDER BY id
        """
    ):
        yield {"kind": "exclusion", "activity": row["id"]}

    for row in connection.execute(
        """
        SELECT category, activity_id, fingerprint, status, resolved_note,
               detail, severity
        FROM review_items
        WHERE status IN ('ignored', 'resolved')
        ORDER BY category, COALESCE(activity_id, ''), fingerprint
        """
    ):
        yield {
            "kind": "review",
            "category": row["category"],
            "activity": row["activity_id"],
            "fingerprint": row["fingerprint"],
            "status": row["status"],
            "note": row["resolved_note"] or "",
            "detail": row["detail"] or "",
            "severity": row["severity"] or "warn",
        }


def write_overlay(
    connection: sqlite3.Connection,
    stream: TextIO,
) -> OverlayCounts:
    """Write the JSONL overlay and return its record counts."""
    counts = OverlayCounts()
    for record in iter_overlay(connection):
        stream.write(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        )
        _count(counts, record)
    return counts


def read_overlay(path: str | Path) -> list[dict]:
    """Read and validate a JSONL overlay, keeping the first line as a header."""
    records: list[dict] = []
    with Path(path).expanduser().open("r", encoding="utf-8") as stream:
        for lineno, line in enumerate(stream, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"line {lineno}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"line {lineno}: expected a JSON object")
            _validate(record, lineno)
            records.append(record)
    if not records:
        raise ValueError("overlay is empty")
    if records[0].get("kind") != "overlay":
        raise ValueError("overlay must start with a version header")
    return records


def apply_overlay(
    connection: sqlite3.Connection,
    records: Iterable[dict],
) -> OverlayCounts:
    """Apply an overlay to a database that already has the raw layer."""
    writer = TrainingWriter(connection)
    counts = OverlayCounts()

    ordered = sorted(
        (
            record for record in records
            if record.get("kind") != "overlay"
        ),
        key=lambda record: _APPLY_ORDER[record["kind"]],
    )

    for record in ordered:
        kind = record["kind"]
        activity = record.get("activity")
        if kind != "review" and kind != "exclusion" and _excluded(
            connection,
            activity,
        ):
            counts.skipped_excluded += 1
            continue

        if kind == "manual_field":
            owner = record.get("owner")
            if owner:
                writer.set_manual_owner(activity, record["field"], owner)
                counts.owner_patches += 1
            else:
                writer.set_manual_field(
                    activity,
                    record["field"],
                    record.get("value"),
                )
                counts.manual_fields += 1
            if record.get("note"):
                connection.execute(
                    """
                    UPDATE activity_manual_fields SET note = ?
                    WHERE activity_id = ? AND field_name = ?
                    """,
                    (record["note"], activity, record["field"]),
                )
            continue

        if kind == "workout":
            if record.get("methods"):
                writer.set_manual_activity_workout_methods(
                    activity,
                    record["methods"],
                )
            if record.get("targets"):
                writer.set_manual_activity_workout_targets(
                    activity,
                    record["targets"],
                )
            counts.workout_sets += 1
            continue

        if kind == "tags":
            writer.replace_activity_tags(
                activity,
                record["tags"],
                source="manual",
                is_manual=True,
            )
            counts.tag_sets += 1
            continue

        if kind == "equipment":
            writer.link_activity_equipment(
                activity,
                record["equipment"],
                source="manual",
                role=record.get("role") or "primary",
                is_manual=True,
            )
            counts.equipment_links += 1
            continue

        if kind == "exclusion":
            writer.exclude_activity(activity)
            counts.exclusions += 1
            continue

        if kind == "review":
            item_id, _created = writer.record_review_item(
                category=record["category"],
                detail=record.get("detail") or "restored overlay decision",
                fingerprint=record["fingerprint"],
                activity_id=activity,
                severity=record.get("severity") or "warn",
            )
            writer.set_review_status(
                item_id,
                record["status"],
                note=record.get("note") or "",
            )
            counts.review_answers += 1
            continue

    return counts


def format_counts(counts: OverlayCounts, *, label: str = "overlay") -> str:
    parts = [
        f"{counts.manual_fields} manual fields",
        f"{counts.owner_patches} owner patches",
        f"{counts.workout_sets} workout sets",
        f"{counts.tag_sets} tag sets",
        f"{counts.equipment_links} equipment links",
        f"{counts.exclusions} exclusions",
        f"{counts.review_answers} review answers",
    ]
    if counts.skipped_excluded:
        parts.append(f"{counts.skipped_excluded} skipped (excluded)")
    return f"{label}: " + ", ".join(parts)


def _count(counts: OverlayCounts, record: dict) -> None:
    kind = record["kind"]
    if kind == "manual_field":
        if record.get("owner"):
            counts.owner_patches += 1
        else:
            counts.manual_fields += 1
    elif kind == "workout":
        counts.workout_sets += 1
    elif kind == "tags":
        counts.tag_sets += 1
    elif kind == "equipment":
        counts.equipment_links += 1
    elif kind == "exclusion":
        counts.exclusions += 1
    elif kind == "review":
        counts.review_answers += 1


def _excluded(connection: sqlite3.Connection, activity: str | None) -> bool:
    if not activity:
        return False
    row = connection.execute(
        "SELECT excluded_at FROM activities WHERE id = ?",
        (activity,),
    ).fetchone()
    return bool(row and row["excluded_at"])


def _validate(record: dict, lineno: int) -> None:
    kind = record.get("kind")
    if kind == "overlay":
        if record.get("version") != OVERLAY_VERSION:
            raise ValueError(
                f"line {lineno}: unsupported overlay version "
                f"{record.get('version')!r}"
            )
        return
    if kind not in KINDS:
        raise ValueError(f"line {lineno}: unknown kind {kind!r}")

    def require(*keys: str) -> None:
        missing = [key for key in keys if key not in record]
        if missing:
            raise ValueError(
                f"line {lineno}: {kind} is missing {', '.join(missing)}"
            )

    if kind == "manual_field":
        require("activity", "field")
        if not record.get("owner") and "value" not in record:
            raise ValueError(
                f"line {lineno}: manual_field needs owner or value"
            )
    elif kind == "workout":
        require("activity")
        if not record.get("methods") and not record.get("targets"):
            raise ValueError(
                f"line {lineno}: workout needs a non-empty methods or "
                "targets list"
            )
        for key in ("methods", "targets"):
            if key in record and not isinstance(record[key], list):
                raise ValueError(f"line {lineno}: {key} must be a list")
    elif kind == "tags":
        require("activity", "tags")
        if not isinstance(record["tags"], list) or not record["tags"]:
            raise ValueError(
                f"line {lineno}: tags must be a non-empty list"
            )
    elif kind == "equipment":
        require("activity", "equipment")
    elif kind == "exclusion":
        require("activity")
    elif kind == "review":
        require("category", "fingerprint", "status")
        if record["status"] not in ("ignored", "resolved"):
            raise ValueError(
                f"line {lineno}: review status must be ignored or resolved"
            )
