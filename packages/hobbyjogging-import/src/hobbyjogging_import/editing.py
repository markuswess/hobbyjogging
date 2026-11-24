"""Manual edit application shared by the review CLI, triage and `activity edit`.

One write path keeps provenance, the review-item lifecycle and the quality
re-check in step: every scalar field goes through ``set_manual_field``, every
set through the matching whole-set writer, and every change appends an
``edit_log`` row. ``activity_field_sources`` is only a snapshot; the log is
the history ``--history`` reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from hobbyjogging_core import TrainingWriter
from hobbyjogging_core.import_rules import MANUAL_FIELDS

from .quality import CONFLICT, WORKOUT_CLASSIFICATION
from .values import format_field

SET_FIELDS = ("tags", "methods", "targets", "equipment")


@dataclass
class EditApplication:
    """Result of one manual change plus the review items it closed."""

    activity_id: str
    field: str
    old: object
    new: object
    findings: list = field(default_factory=list)
    resolved_items: list[int] = field(default_factory=list)

    @property
    def okay(self) -> bool:
        return not self.findings

    def note(self) -> str:
        return (
            f"manual edit: {self.field} "
            f"{_format_change(self.field, self.old)} → "
            f"{_format_change(self.field, self.new)}"
        )

    def describe(self) -> str:
        return (
            f"set {self.field}: {_format_change(self.field, self.old)} → "
            f"{_format_change(self.field, self.new)} (manual)"
        )

    def describe_findings(self) -> str:
        return "; ".join(
            f"{finding.rule}: {finding.detail}" for finding in self.findings
        )


def apply_manual_edit(
    writer: TrainingWriter,
    *,
    activity_id: str,
    field: str,
    value: object,
    resolve_item_id: int | None = None,
    note: str | None = None,
    source: str = "manual",
) -> EditApplication:
    """Write a manual value, close stale review items, re-run quality rules.

    Resolves the explicit item (if any) and every open ``field_conflict`` for
    the touched field, so an item-less edit cannot leave a stale conflict
    behind. Returns the application result (old value plus the findings that
    still stand after the edit).
    """
    from .quality import refresh_activity_quality

    if field not in MANUAL_FIELDS:
        raise ValueError(f"field cannot be edited: {field}")

    row = _require_activity(writer, activity_id)
    old = row[field]

    writer.set_manual_field(activity_id, field, value)

    application = EditApplication(
        activity_id=activity_id,
        field=field,
        old=old,
        new=value,
    )
    resolve_note = note or application.note()
    application.resolved_items = _open_explicit(writer, resolve_item_id)
    application.resolved_items += _resolve_conflicts(
        writer, activity_id, field, resolve_note
    )
    application.resolved_items = _unique(application.resolved_items)

    _log(writer, application, source=source, note=resolve_note)
    application.findings = refresh_activity_quality(
        writer,
        activity_id=activity_id,
        resolve_item_id=resolve_item_id,
        resolve_note=resolve_note,
    )
    return application


def apply_manual_clear(
    writer: TrainingWriter,
    *,
    activity_id: str,
    field: str,
    resolve_item_id: int | None = None,
    note: str | None = None,
    source: str = "manual",
) -> EditApplication | None:
    """Remove a manual value and its ownership, logging the change.

    Returns ``None`` when the field has no manual override to remove.
    """
    from .quality import refresh_activity_quality

    if field in SET_FIELDS:
        return apply_manual_set_edit(
            writer,
            activity_id=activity_id,
            field=field,
            values=[],
            resolve_item_id=resolve_item_id,
            note=note,
            source=source,
        )
    if field not in MANUAL_FIELDS:
        raise ValueError(f"field cannot be edited: {field}")

    row = _require_activity(writer, activity_id)
    old = row[field]
    if not writer.clear_manual_field(activity_id, field):
        return None

    new = _field_value(writer, activity_id, field)
    application = EditApplication(
        activity_id=activity_id,
        field=field,
        old=old,
        new=new,
    )
    resolve_note = note or f"cleared manual {field}"
    application.resolved_items = _open_explicit(writer, resolve_item_id)
    application.resolved_items += _resolve_conflicts(
        writer, activity_id, field, resolve_note
    )
    application.resolved_items = _unique(application.resolved_items)

    _log(writer, application, source=source, note=resolve_note)
    application.findings = refresh_activity_quality(
        writer,
        activity_id=activity_id,
        resolve_item_id=resolve_item_id,
        resolve_note=resolve_note,
    )
    return application


def apply_manual_set_edit(
    writer: TrainingWriter,
    *,
    activity_id: str,
    field: str,
    values: list[str],
    resolve_item_id: int | None = None,
    note: str | None = None,
    source: str = "manual",
) -> EditApplication:
    """Replace one whole manual set (tags, methods, targets or equipment)."""
    if field not in SET_FIELDS:
        raise ValueError(f"not a set field: {field}")

    _require_activity(writer, activity_id)
    old = _field_value(writer, activity_id, field)

    if field == "tags":
        writer.replace_activity_tags(
            activity_id,
            values,
            source="manual",
            is_manual=True,
        )
    elif field == "methods":
        writer.set_manual_activity_workout_methods(activity_id, values)
    elif field == "targets":
        writer.set_manual_activity_workout_targets(activity_id, values)
    else:
        writer.set_manual_activity_equipment(activity_id, values)

    new = _field_value(writer, activity_id, field)
    resolved = _resolve_explicit(writer, resolve_item_id, note)
    if field in ("methods", "targets"):
        resolved += _resolve_classification(writer, activity_id, note)
    resolved = _unique(resolved)

    application = EditApplication(
        activity_id=activity_id,
        field=field,
        old=old,
        new=new,
        resolved_items=resolved,
    )
    _log(
        writer,
        application,
        source=source,
        note=note or f"manual {field} set",
    )
    return application


# -- reading values ------------------------------------------------------


def _require_activity(writer: TrainingWriter, activity_id: str):
    row = writer.connection.execute(
        "SELECT * FROM activities WHERE id = ?",
        (activity_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown activity: {activity_id}")
    if row["excluded_at"]:
        raise ValueError(f"activity {activity_id} is excluded")
    return row


def _field_value(
    writer: TrainingWriter,
    activity_id: str,
    field: str,
) -> object:
    queries = {
        "tags": (
            "SELECT tag AS value FROM activity_tags "
            "WHERE activity_id = ? ORDER BY tag"
        ),
        "methods": (
            "SELECT method AS value FROM activity_workout_methods "
            "WHERE activity_id = ? ORDER BY method"
        ),
        "targets": (
            "SELECT target AS value FROM activity_workout_targets "
            "WHERE activity_id = ? ORDER BY target"
        ),
        "equipment": (
            "SELECT equipment_id AS value FROM activity_equipment "
            "WHERE activity_id = ? ORDER BY role, equipment_id"
        ),
    }
    query = queries.get(field)
    if query is None:
        row = writer.connection.execute(
            f"SELECT {field} FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        return row[field]
    return [
        row["value"]
        for row in writer.connection.execute(query, (activity_id,))
    ]


# -- review-item lifecycle ------------------------------------------------


def _open_explicit(
    writer: TrainingWriter,
    item_id: int | None,
) -> list[int]:
    if item_id is None:
        return []
    item = writer.review_item(item_id)
    if item is None or item["status"] != "open":
        return []
    return [item_id]


def _resolve_explicit(
    writer: TrainingWriter,
    item_id: int | None,
    note: str | None,
) -> list[int]:
    if item_id is None:
        return []
    item = writer.review_item(item_id)
    if item is None or item["status"] != "open":
        return []
    writer.set_review_status(
        item_id,
        "resolved",
        note=note or "manual edit",
    )
    return [item_id]


def _resolve_conflicts(
    writer: TrainingWriter,
    activity_id: str,
    field: str,
    note: str | None,
) -> list[int]:
    resolved = []
    for item in writer.review_items(category=CONFLICT, status="open"):
        if item["activity_id"] != activity_id:
            continue
        try:
            context = json.loads(item["context_json"] or "{}")
        except ValueError:
            continue
        if context.get("field") != field:
            continue
        writer.set_review_status(
            item["id"],
            "resolved",
            note=note or f"manual edit: {field}",
        )
        resolved.append(item["id"])
    return resolved


def _resolve_classification(
    writer: TrainingWriter,
    activity_id: str,
    note: str | None,
) -> list[int]:
    resolved = []
    for item in writer.review_items(
        category=WORKOUT_CLASSIFICATION,
        status="open",
    ):
        if item["activity_id"] != activity_id:
            continue
        writer.set_review_status(
            item["id"],
            "resolved",
            note=note or "manual classification",
        )
        resolved.append(item["id"])
    return resolved


# -- logging -------------------------------------------------------------


def _unique(ids: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _log(
    writer: TrainingWriter,
    application: EditApplication,
    *,
    source: str,
    note: str,
) -> None:
    if application.resolved_items:
        ids = ", #".join(str(item) for item in application.resolved_items)
        suffix = f"resolved review item(s) #{ids}"
        note = f"{note}; {suffix}" if note else suffix
    writer.record_edit_log(
        entity_kind="activity",
        entity_id=application.activity_id,
        field=application.field,
        old=application.old,
        new=application.new,
        source=source,
        note=note,
    )


def format_change(field: str, value: object) -> str:
    """Render one value for a set or scalar change line."""
    return _format_change(field, value)


def _format_change(field: str, value: object) -> str:
    if field in SET_FIELDS:
        if value is None:
            return "-"
        items = list(value)
        return ", ".join(str(item) for item in items) if items else "(none)"
    return format_field(field, value)
