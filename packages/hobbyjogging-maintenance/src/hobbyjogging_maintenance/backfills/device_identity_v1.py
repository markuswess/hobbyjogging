"""Re-point provider-fallback devices at the FIT device they claim.

Intervals may report the watch model instead of the app that uploaded the
activity. The importer now resolves that name against the devices table: a
unique FIT device of the same model claims the activity, an app name is never
a device, and two devices of the same model stay ambiguous. This repairs the
activities stored before that rule existed, through the same resolver and the
normal writer path.

Device rows are inputs in their own right. Provider rows that no activity
points at after this task are left in place; excluding them needs a device
exclusion column, which is core/schema work, not a hard delete here.
"""

from __future__ import annotations

import json
import sqlite3

from hobbyjogging_import.devices import resolve_provider_device

from ..context import TaskContext
from ..registry import task

SOURCE = "intervals"

_COUNT_ORDER = (
    "activities",
    "reassigned",
    "cleared",
    "unchanged",
    "manual",
    "skipped",
)


@task(
    "device_identity_v1",
    kind="backfill",
    description=(
        "Re-point activities on a provider fallback device at the FIT device "
        "they claim."
    ),
)
def device_identity(context: TaskContext) -> None:
    """Resolve every stored provider fallback through the import rule."""
    rows = _rows(context)
    if not rows:
        _require_known_entity(context)
        context.note("No activities on a provider fallback device in scope.")
        return

    for row in rows:
        context.count("activities")

        if row["excluded_at"]:
            context.count("skipped")
            continue

        if _is_manual(context.connection, row["id"]):
            context.count("manual")
            continue

        name = _device_name(row["payload_json"])
        if not name:
            context.count("skipped")
            continue

        resolved = resolve_provider_device(
            context.connection,
            context.writer,
            name,
        )
        if resolved == row["device_id"]:
            context.count("unchanged")
            continue

        context.writer.upsert_activity(
            row["id"],
            {"device_id": resolved},
            source=SOURCE,
            source_record_id=row["source_record_id"],
        )

        stored = _stored_device(context.connection, row["id"])
        if stored == row["device_id"]:
            # The writer kept the stored value (for example an owner patch).
            context.count("skipped")
            continue

        if stored is None:
            context.count("cleared")
        else:
            context.count("reassigned")
        context.note(
            f"{row['local_date']} {row['name'] or '-'} [{row['id']}]: "
            f"{row['device_id']} -> {stored or 'none'}"
        )
        context.details.setdefault("changes", []).append(
            {
                "activity_id": row["id"],
                "local_date": row["local_date"],
                "from": row["device_id"],
                "to": stored,
            }
        )

    context.order_counts(_COUNT_ORDER)


def _rows(context: TaskContext) -> list[sqlite3.Row]:
    where = [
        "a.device_id LIKE 'intervals:%'",
        """
        NOT EXISTS (
            SELECT 1
            FROM activity_sources fit_link
            JOIN source_records fit_record
              ON fit_record.id = fit_link.source_record_id
            WHERE fit_link.activity_id = a.id
              AND fit_record.source = 'fit'
        )
        """,
    ]
    params: list[object] = []

    if context.scope.start is not None:
        where.append("a.local_date >= ?")
        params.append(context.scope.start.isoformat())
    if context.scope.end is not None:
        where.append("a.local_date <= ?")
        params.append(context.scope.end.isoformat())
    if context.scope.entity_id is not None:
        where.append("a.id = ?")
        params.append(context.scope.entity_id)

    sql = f"""
        SELECT a.id, a.local_date, a.name, a.excluded_at, a.device_id,
               sr.id AS source_record_id, sr.payload_json
        FROM activities a
        JOIN activity_sources als ON als.id = (
            SELECT als2.id
            FROM activity_sources als2
            JOIN source_records sr2 ON sr2.id = als2.source_record_id
            WHERE als2.activity_id = a.id
              AND sr2.source = 'intervals'
              AND sr2.record_type = 'activity'
            ORDER BY als2.is_primary DESC, als2.id
            LIMIT 1
        )
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE {' AND '.join(where)}
        ORDER BY a.local_date, a.id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()


def _device_name(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("device_name") or "").strip()


def _is_manual(connection: sqlite3.Connection, activity_id: str) -> bool:
    row = connection.execute(
        """
        SELECT is_manual FROM activity_field_sources
        WHERE activity_id = ? AND field_name = 'device_id'
        """,
        (activity_id,),
    ).fetchone()
    return bool(row is not None and row["is_manual"])


def _stored_device(
    connection: sqlite3.Connection,
    activity_id: str,
) -> str | None:
    row = connection.execute(
        "SELECT device_id FROM activities WHERE id = ?",
        (activity_id,),
    ).fetchone()
    return None if row is None else row["device_id"]


def _require_known_entity(context: TaskContext) -> None:
    """Fail loudly when ``--entity`` names an unknown or excluded activity."""
    if context.scope.entity_id is None:
        return

    row = context.connection.execute(
        """
        SELECT 1 FROM activities
        WHERE id = ? AND excluded_at IS NULL
        """,
        (context.scope.entity_id,),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"unknown or excluded activity: {context.scope.entity_id}"
        )
