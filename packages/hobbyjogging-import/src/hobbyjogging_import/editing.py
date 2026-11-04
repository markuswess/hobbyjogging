"""Manual edit application shared by the review CLI and the triage queue."""

from __future__ import annotations

from dataclasses import dataclass

from hobbyjogging_core import TrainingWriter

from .values import format_field


@dataclass
class EditApplication:
    """Result of one manual field edit plus its quality re-check."""

    activity_id: str
    field: str
    old: object
    new: object
    findings: list

    @property
    def okay(self) -> bool:
        return not self.findings

    def note(self) -> str:
        return (
            f"manual edit: {self.field} "
            f"{format_field(self.field, self.old)} → "
            f"{format_field(self.field, self.new)}"
        )

    def describe(self) -> str:
        return (
            f"set {self.field}: {format_field(self.field, self.old)} → "
            f"{format_field(self.field, self.new)} (manual)"
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
) -> EditApplication:
    """Write a manual value, close stale review items, re-run quality rules.

    Returns the application result (old value plus the findings that still
    stand after the edit).
    """
    from .quality import refresh_activity_quality

    row = writer.connection.execute(
        f"SELECT {field} FROM activities WHERE id = ?",
        (activity_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown activity: {activity_id}")

    old = row[field]
    writer.set_manual_field(activity_id, field, value)

    application = EditApplication(
        activity_id=activity_id,
        field=field,
        old=old,
        new=value,
        findings=[],
    )
    application.findings = refresh_activity_quality(
        writer,
        activity_id=activity_id,
        resolve_item_id=resolve_item_id,
        resolve_note=note or application.note(),
    )
    return application
