"""Compare canonical activity fields with their source payloads.

Read-only: each owned field is derived from its input (a manual value, an
owner patch or the source pointer) and compared with the stored value. It
reports drift, a dangling pointer, an unmapped source/field or a payload that
cannot be read. It never writes, so it is the gate before trusting a rebuild.
"""

from __future__ import annotations

from hobbyjogging_core.db.writer import ACTIVITY_COLUMNS

from ..canonical import activities, expected, manual_inputs, owner, pointers, same
from ..context import TaskContext
from ..registry import task

_COUNT_ORDER = (
    "activities",
    "fields",
    "ok",
    "drift",
    "dangling",
    "unmapped",
    "error",
)

MAX_NOTES = 20


@task(
    "verify_canonical",
    kind="recompute",
    description="Compare canonical activity fields with their source payloads.",
)
def verify_canonical(context: TaskContext) -> None:
    rows = activities(context.connection, context.scope)
    if not rows:
        context.note("No activities in scope.")
        return

    per_field: dict[str, dict[str, int]] = {}
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
            counts = per_field.setdefault(field, {})
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
                counts[status] = counts.get(status, 0) + 1
                detail = (
                    f"{activity['id']} {field}: {status} "
                    f"(source {source})"
                )
                context.output_lines.append(detail)
                if reported < MAX_NOTES:
                    context.note(detail)
                    reported += 1
                continue

            if same(activity[field], value):
                context.count("ok")
                counts["ok"] = counts.get("ok", 0) + 1
                continue

            context.count("drift")
            counts["drift"] = counts.get("drift", 0) + 1
            detail = (
                f"{activity['id']} {field}: stored={activity[field]!r} "
                f"derived={value!r} (source {source})"
            )
            context.output_lines.append(detail)
            if reported < MAX_NOTES:
                context.note(detail)
                reported += 1

    for field, counts in sorted(per_field.items()):
        if any(
            counts.get(key, 0)
            for key in ("drift", "dangling", "unmapped", "error")
        ):
            context.note(
                f"{field}: {counts.get('ok', 0)} ok, "
                f"{counts.get('drift', 0)} drift, "
                f"{counts.get('dangling', 0)} dangling, "
                f"{counts.get('unmapped', 0)} unmapped, "
                f"{counts.get('error', 0)} error"
            )

    context.order_counts(_COUNT_ORDER)
