"""Rebuild canonical activity fields from their inputs.

The ownership pointer is not re-decided: each field is projected from the
manual value, the owner patch or the stored pointer. Fields without a readable
input are left untouched and reported. Links, exclusions, review answers, child
tables and entity rows are never touched.
"""

from __future__ import annotations

from hobbyjogging_core.db.writer import ACTIVITY_COLUMNS

from ..canonical import activities, expected, manual_inputs, owner, pointers, same
from ..context import TaskContext
from ..registry import task

_COUNT_ORDER = (
    "activities",
    "fields",
    "written",
    "unchanged",
    "dangling",
    "unmapped",
    "error",
)

MAX_NOTES = 20


@task(
    "recompute_canonical",
    kind="recompute",
    description="Rebuild canonical activity fields from their inputs.",
)
def recompute_canonical(context: TaskContext) -> None:
    rows = activities(context.connection, context.scope)
    if not rows:
        context.note("No activities in scope.")
        return

    reported = 0

    for activity in rows:
        context.count("activities")
        manual = manual_inputs(context.connection, activity["id"])
        fields = pointers(context.connection, activity["id"])

        for field in sorted(ACTIVITY_COLUMNS):
            source, record_id = owner(manual, fields, field)
            if source is None:
                continue

            context.count("fields")
            value, status = expected(
                context.connection,
                activity,
                field,
                source,
                record_id,
                manual,
            )

            if status != "ok":
                context.count(status)
                if reported < MAX_NOTES:
                    context.note(
                        f"{activity['id']} {field}: {status} "
                        f"(source {source})"
                    )
                    reported += 1
                continue

            if same(activity[field], value):
                context.count("unchanged")
                continue

            context.writer.project_activity_field(
                activity["id"],
                field,
                value,
                update_snapshot=source != "manual",
            )
            context.count("written")
            if reported < MAX_NOTES:
                context.note(
                    f"{activity['id']} {field}: "
                    f"{activity[field]!r} -> {value!r} (source {source})"
                )
                reported += 1

    context.order_counts(_COUNT_ORDER)
