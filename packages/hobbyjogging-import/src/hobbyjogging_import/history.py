"""Shared edit-log writing and rendering for the manual commands."""

from __future__ import annotations

import json

from hobbyjogging_core import TrainingWriter


def record_changes(
    writer: TrainingWriter,
    *,
    entity_kind: str,
    entity_id: str,
    old: dict[str, object],
    new: dict[str, object],
    source: str = "manual",
    note: str = "",
) -> int:
    """Append one edit_log row per changed field; returns the row count."""
    count = 0
    for field in sorted(new):
        before = old.get(field)
        after = new[field]
        if before == after:
            continue
        writer.record_edit_log(
            entity_kind=entity_kind,
            entity_id=entity_id,
            field=field,
            old=before,
            new=after,
            source=source,
            note=note,
        )
        count += 1
    return count


def history_lines(entries, *, field_formatter=None) -> list[str]:
    """Render edit-log entries, oldest first."""
    if not entries:
        return ["No edits recorded."]
    format_value = field_formatter or _plain
    lines = []
    for entry in entries:
        lines.append(
            f"#{entry.id} {entry.created_at} [{entry.source}] "
            f"{entry.field}: {format_value(entry.field, entry.old)} → "
            f"{format_value(entry.field, entry.new)}"
        )
        if entry.note:
            lines.append(f"    {entry.note}")
    return lines


def _plain(_field: str, value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "(none)"
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)
