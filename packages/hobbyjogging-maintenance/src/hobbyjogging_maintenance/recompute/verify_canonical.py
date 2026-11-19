"""Compare canonical activity fields with their source payloads.

Read-only: each owned field is derived from its input (a manual value, an
owner patch or the source pointer) and compared with the stored value. It
reports drift, a dangling pointer, an unmapped source/field or a payload that
cannot be read. It never writes, so it is the gate before trusting a rebuild.
"""

from __future__ import annotations

import json
import sqlite3

from hobbyjogging_core.db.writer import ACTIVITY_COLUMNS
from hobbyjogging_core.sports import NO_DISTANCE_SPORTS
from hobbyjogging_import.derive import Unmapped, derive_value

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
    activities = _activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    per_field: dict[str, dict[str, int]] = {}
    reported = 0

    for activity in activities:
        context.count("activities")
        manual = _manual_inputs(context.connection, activity["id"])
        pointers = _pointers(context.connection, activity["id"])

        for field in sorted(ACTIVITY_COLUMNS):
            source, record_id = _owner(manual, pointers, field)
            if source is None:
                continue

            context.count("fields")
            counts = per_field.setdefault(field, {})
            expected, status = _expected(
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

            if _same(activity[field], expected, field):
                context.count("ok")
                counts["ok"] = counts.get("ok", 0) + 1
                continue

            context.count("drift")
            counts["drift"] = counts.get("drift", 0) + 1
            detail = (
                f"{activity['id']} {field}: stored={activity[field]!r} "
                f"derived={expected!r} (source {source})"
            )
            context.output_lines.append(detail)
            if reported < MAX_NOTES:
                context.note(detail)
                reported += 1

    for field, counts in sorted(per_field.items()):
        if any(counts.get(key, 0) for key in ("drift", "dangling", "unmapped", "error")):
            context.note(
                f"{field}: {counts.get('ok', 0)} ok, "
                f"{counts.get('drift', 0)} drift, "
                f"{counts.get('dangling', 0)} dangling, "
                f"{counts.get('unmapped', 0)} unmapped, "
                f"{counts.get('error', 0)} error"
            )

    context.order_counts(_COUNT_ORDER)


def _activities(context: TaskContext) -> list[sqlite3.Row]:
    where = ["excluded_at IS NULL"]
    params: list[object] = []

    if context.scope.start is not None:
        where.append("local_date >= ?")
        params.append(context.scope.start.isoformat())
    if context.scope.end is not None:
        where.append("local_date <= ?")
        params.append(context.scope.end.isoformat())
    if context.scope.entity_id is not None:
        where.append("id = ?")
        params.append(context.scope.entity_id)

    sql = (
        "SELECT * FROM activities "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY local_date, id"
    )
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()


def _manual_inputs(
    connection: sqlite3.Connection,
    activity_id: str,
) -> dict[str, sqlite3.Row]:
    return {
        row["field_name"]: row
        for row in connection.execute(
            """
            SELECT field_name, value_json, owner_source
            FROM activity_manual_fields
            WHERE activity_id = ?
            """,
            (activity_id,),
        )
    }


def _pointers(
    connection: sqlite3.Connection,
    activity_id: str,
) -> dict[str, sqlite3.Row]:
    return {
        row["field_name"]: row
        for row in connection.execute(
            """
            SELECT field_name, source, source_record_id
            FROM activity_field_sources
            WHERE activity_id = ?
            """,
            (activity_id,),
        )
    }


def _owner(
    manual: dict[str, sqlite3.Row],
    pointers: dict[str, sqlite3.Row],
    field: str,
) -> tuple[str | None, int | None]:
    entry = manual.get(field)
    if entry is not None:
        if entry["value_json"] is not None:
            return "manual", None
        if entry["owner_source"] is not None:
            return entry["owner_source"], None

    pointer = pointers.get(field)
    if pointer is not None:
        return pointer["source"], pointer["source_record_id"]
    return None, None


def _expected(
    connection: sqlite3.Connection,
    activity: sqlite3.Row,
    field: str,
    source: str,
    record_id: int | None,
    manual: dict[str, sqlite3.Row],
) -> tuple[object, str]:
    entry = manual.get(field)
    if entry is not None and entry["value_json"] is not None:
        try:
            return json.loads(entry["value_json"]), "ok"
        except (TypeError, ValueError):
            return None, "error"

    if source == "manual":
        return None, "dangling"

    record_id = record_id or _linked_record(
        connection,
        activity["id"],
        source,
    )
    if record_id is None:
        return None, "dangling"

    row = connection.execute(
        "SELECT payload_json FROM source_records WHERE id = ?",
        (record_id,),
    ).fetchone()
    if row is None:
        return None, "dangling"

    try:
        payload = json.loads(row["payload_json"] or "{}")
    except ValueError:
        return None, "error"
    if not isinstance(payload, dict):
        return None, "error"

    try:
        value = derive_value(source, field, payload)
    except Unmapped:
        return None, "unmapped"
    except Exception:
        return None, "error"

    # The writer zeroes distance for sports where it is not meaningful.
    if field == "distance_m" and activity["sport"] in NO_DISTANCE_SPORTS:
        value = 0.0
    return value, "ok"


def _linked_record(
    connection: sqlite3.Connection,
    activity_id: str,
    source: str,
) -> int | None:
    row = connection.execute(
        """
        SELECT als.source_record_id
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE als.activity_id = ? AND sr.source = ?
        ORDER BY als.is_primary DESC, als.id
        LIMIT 1
        """,
        (activity_id, source),
    ).fetchone()
    return row["source_record_id"] if row is not None else None


def _same(stored: object, expected: object, field: str) -> bool:
    if stored is None or expected is None:
        return stored is None and expected is None
    if isinstance(stored, (int, float)) and isinstance(expected, (int, float)):
        scale = max(1.0, abs(float(expected)))
        return abs(float(stored) - float(expected)) <= 1e-6 * scale
    return stored == expected
