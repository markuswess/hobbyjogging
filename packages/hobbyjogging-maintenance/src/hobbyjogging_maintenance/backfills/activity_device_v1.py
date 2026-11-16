"""Backfill the recording device on existing activities.

Schema v17 added ``devices`` and ``activities.device_id``. The FIT payloads
carry the recorder's manufacturer, product and serial in ``file``; Intervals
carries a ``device_name`` string. FIT wins through the field authority, and a
manual assignment is never touched.

Garmin Connect web uploads (``product='connect'``) are uploads, not devices.
"""

from __future__ import annotations

import json
import sqlite3

from ..context import TaskContext
from ..registry import task

FIT = "fit"
INTERVALS = "intervals"

_COUNT_ORDER = ("activities", "devices", "written", "unchanged", "skipped")


@task(
    "activity_device_v1",
    kind="backfill",
    description="Fill devices and the activity device from the payloads.",
)
def activity_device(context: TaskContext) -> None:
    rows = _rows(context)
    if not rows:
        context.note("No device payloads in scope.")
        return

    devices: set[str] = set()
    seen: set[str] = set()

    # FIT first: it carries the serial and wins through the field authority.
    # Intervals then only fills the activities FIT left without a device.
    for source in (FIT, INTERVALS):
        for row in rows:
            if row["source"] != source or row["excluded_at"]:
                continue

            current = _current(context.connection, row["id"])

            if source == INTERVALS and current is not None:
                context.count("unchanged")
                continue

            device_id, device = _device(source, row["payload_json"])
            if device_id is None:
                context.count("skipped")
                continue

            if row["id"] not in seen:
                seen.add(row["id"])
                context.count("activities")

            if current == device_id:
                context.count("unchanged")
                continue

            if device_id not in devices:
                devices.add(device_id)
                context.count("devices")
                context.writer.upsert_device(device_id, **device)

            context.writer.upsert_activity(
                row["id"],
                {"device_id": device_id},
                source=source,
                source_record_id=row["source_record_id"],
            )
            context.count("written")

    context.order_counts(_COUNT_ORDER)


def _rows(context: TaskContext) -> list[sqlite3.Row]:
    where = ["sr.source IN ('fit', 'intervals')"]
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
        SELECT a.id, a.local_date, a.excluded_at,
               sr.id AS source_record_id, sr.source, sr.payload_json
        FROM activities a
        JOIN activity_sources als ON als.activity_id = a.id
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE {' AND '.join(where)}
        ORDER BY a.local_date, a.id, sr.source
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()


def _device(
    source: str,
    payload_json: str | None,
) -> tuple[str | None, dict[str, str]]:
    payload = _payload(payload_json)
    if payload is None:
        return None, {}

    if source == FIT:
        file_id = payload.get("file") or {}
        manufacturer = str(file_id.get("manufacturer") or "").strip()
        product = str(file_id.get("product") or "").strip()

        if not manufacturer or not product or product == "connect":
            return None, {}

        serial = str(file_id.get("serial_number") or "").strip()
        return (
            f"fit:{manufacturer}:{product}:{serial}",
            {
                "manufacturer": manufacturer,
                "product": product,
                "serial_number": serial,
            },
        )

    name = str(payload.get("device_name") or "").strip()
    if not name:
        return None, {}

    slug = _slug(name)
    if not slug:
        return None, {}

    return f"intervals:{slug}", {"name": name}


def _slug(text: str) -> str:
    slug = "".join(
        character if character.isalnum() else "-"
        for character in text.lower()
    ).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


def _current(connection: sqlite3.Connection, activity_id: str) -> str | None:
    row = connection.execute(
        "SELECT device_id FROM activities WHERE id = ?",
        (activity_id,),
    ).fetchone()
    return None if row is None else row["device_id"]


def _payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None
