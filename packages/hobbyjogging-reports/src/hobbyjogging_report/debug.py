"""Raw stored payload dump for debugging.

Reads ``source_records.payload_json`` from the canonical database; no network
access.
"""

from __future__ import annotations

import json

from hobbyjogging_core import open_database

RESOURCES = {
    "activities": "activity",
    "wellness": "wellness",
    "events": "event",
}

USAGE = "usage: hobbyjogging_report debug [activities|wellness|events|intervals|all]"


def debug(resource: str = "all", *, database=None) -> None:
    connection = open_database(database)
    try:
        if resource == "intervals":
            print(_dump_intervals(connection))
            return

        if resource == "all":
            data = {
                name: _recent(connection, record_type)
                for name, record_type in RESOURCES.items()
            }
        elif resource in RESOURCES:
            data = _recent(connection, RESOURCES[resource])
        else:
            raise SystemExit(USAGE)
    finally:
        connection.close()

    print(json.dumps(data, indent=2, ensure_ascii=False))


def _recent(connection, record_type: str, limit: int = 2) -> list[dict]:
    """Return the most recent parsed payloads of one record type."""
    rows = connection.execute(
        """
        SELECT source, external_id, payload_json
        FROM source_records
        WHERE record_type = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (record_type, limit),
    ).fetchall()
    return [_payload(row) for row in rows]


def _payload(row) -> dict:
    try:
        value = json.loads(row["payload_json"] or "")
    except (TypeError, ValueError):
        value = None
    if isinstance(value, dict):
        return value
    return {"source": row["source"], "external_id": row["external_id"]}


def _dump_intervals(connection) -> str:
    """Return the intervals block of the newest activity payload that has one."""
    row = connection.execute(
        """
        SELECT payload_json
        FROM source_records
        WHERE record_type = 'activity'
          AND payload_json LIKE '%icu_intervals%'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return "No stored activity payload with intervals"

    payload = _payload(row)
    return json.dumps(
        payload.get("icu_intervals"),
        indent=2,
        ensure_ascii=False,
    )
