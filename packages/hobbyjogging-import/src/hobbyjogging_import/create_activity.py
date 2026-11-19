"""Create an activity from a source summary, on policy or after review."""

from __future__ import annotations

import uuid

from hobbyjogging_core import TrainingWriter

from .quality import CREATE_ACTIVITY, review_fingerprint


def create_activity(
    writer: TrainingWriter,
    *,
    source: str,
    values: dict,
    source_record_id: int,
) -> str:
    """Create one activity from a source summary and link its record."""
    activity_id = str(uuid.uuid4())
    writer.upsert_activity(
        activity_id,
        values,
        source=source,
        source_record_id=source_record_id,
    )
    writer.link_activity_source(
        activity_id,
        source_record_id,
        match_method="created",
    )
    return activity_id


def record_create_review(
    writer: TrainingWriter,
    *,
    source: str,
    source_record_id: int,
    values: dict,
    detail: str,
    import_run_id: int | None = None,
) -> int:
    """Queue a create decision for a row the policy did not auto-create."""
    _, created = writer.record_review_item(
        category=CREATE_ACTIVITY,
        detail=detail,
        context={
            "source": source,
            "source_record_id": source_record_id,
            "values": values,
        },
        severity="warn",
        fingerprint=review_fingerprint(
            [CREATE_ACTIVITY, source, source_record_id]
        ),
        source_record_id=source_record_id,
        import_run_id=import_run_id,
    )
    return int(created)
