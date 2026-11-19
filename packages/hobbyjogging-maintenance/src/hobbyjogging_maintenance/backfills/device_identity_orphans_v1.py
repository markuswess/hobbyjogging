"""Soft-exclude the provider device rows no activity uses.

``device_identity_v1`` moved the last activities off the provider fallback rows
and cleared the app-name one. The rows stay for audit; this task hides them
once nothing points at them, so the device report does not list a 0-activity
watch.
"""

from __future__ import annotations

from ..context import TaskContext
from ..registry import task

PROVIDER_ROWS = (
    "intervals:garmin-enduro",
    "intervals:runalyze",
)

_COUNT_ORDER = ("devices", "excluded", "unchanged", "kept", "missing")


@task(
    "device_identity_orphans_v1",
    kind="backfill",
    description="Soft-exclude provider device rows that no activity uses.",
)
def device_identity_orphans(context: TaskContext) -> None:
    for device_id in PROVIDER_ROWS:
        context.count("devices")
        row = context.connection.execute(
            """
            SELECT d.excluded_at,
                   (SELECT COUNT(*) FROM activities a
                     WHERE a.device_id = d.id) AS activities
            FROM devices d
            WHERE d.id = ?
            """,
            (device_id,),
        ).fetchone()

        if row is None:
            context.count("missing")
            continue
        if row["excluded_at"]:
            context.count("unchanged")
            continue
        if row["activities"] > 0:
            context.count("kept")
            continue

        context.writer.exclude_device(device_id)
        context.count("excluded")

    context.order_counts(_COUNT_ORDER)
