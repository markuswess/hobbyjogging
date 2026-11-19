"""Resolve canonical activity fields from their inputs.

One resolver for the read-only check and the rebuild: a manual value wins, then
an owner patch, then the stored pointer. The value is derived from the source
payload through :mod:`hobbyjogging_import.derive`; the ownership itself is
never re-decided here.
"""

from __future__ import annotations

import json
import sqlite3

from hobbyjogging_core.sports import NO_DISTANCE_SPORTS
from hobbyjogging_import.derive import Unmapped, derive_value

from .context import Scope


def activities(
    connection: sqlite3.Connection,
    scope: Scope,
) -> list[sqlite3.Row]:
    where = ["excluded_at IS NULL"]
    params: list[object] = []

    if scope.start is not None:
        where.append("local_date >= ?")
        params.append(scope.start.isoformat())
    if scope.end is not None:
        where.append("local_date <= ?")
        params.append(scope.end.isoformat())
    if scope.entity_id is not None:
        where.append("id = ?")
        params.append(scope.entity_id)

    sql = (
        "SELECT * FROM activities "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY local_date, id"
    )
    if scope.limit is not None:
        sql += " LIMIT ?"
        params.append(scope.limit)

    return connection.execute(sql, params).fetchall()


def manual_inputs(
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


def pointers(
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


def owner(
    manual: dict[str, sqlite3.Row],
    pointers: dict[str, sqlite3.Row],
    field: str,
) -> tuple[str | None, int | None]:
    entry = manual.get(field)
    if entry is not None:
        if entry["value_json"] is not None:
            return "manual", None
        if entry["owner_source"] is not None:
            pointer = pointers.get(field)
            record_id = None
            if (
                pointer is not None
                and pointer["source"] == entry["owner_source"]
            ):
                record_id = pointer["source_record_id"]
            return entry["owner_source"], record_id

    pointer = pointers.get(field)
    if pointer is not None:
        return pointer["source"], pointer["source_record_id"]
    return None, None


def expected(
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


def same(stored: object, expected: object) -> bool:
    if stored is None or expected is None:
        return stored is None and expected is None
    if isinstance(stored, (int, float)) and isinstance(expected, (int, float)):
        scale = max(1.0, abs(float(expected)))
        return abs(float(stored) - float(expected)) <= 1e-6 * scale
    return stored == expected


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
