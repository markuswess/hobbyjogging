"""Backfill per-activity weather from the stored payloads.

Schema v13 added ``activity_weather``. Intervals carries ``average_temp`` and
the sheet ``Temperatur in °C``; both are degrees Celsius, which is the stored
unit. Runalyze fills the remaining fields (humidity, wind, pressure, …) when
its import lands, and only into the gaps this backfill leaves.
"""

from __future__ import annotations

import json
import sqlite3

from ..context import TaskContext
from ..registry import task

SOURCES = ("intervals", "sheet")
ORDER = {source: index for index, source in enumerate(SOURCES)}

_COUNT_ORDER = ("activities", "written", "unchanged", "skipped")


@task(
    "activity_weather_v1",
    kind="backfill",
    description="Fill activity_weather from the stored payloads.",
)
def activity_weather(context: TaskContext) -> None:
    rows = _rows(context)
    if not rows:
        context.note("No weather payloads in scope.")
        return

    seen: set[str] = set()

    for row in rows:
        if row["excluded_at"]:
            continue

        temp_c = _temperature(row["source"], row["payload_json"])
        if temp_c is None:
            continue

        if row["id"] not in seen:
            seen.add(row["id"])
            context.count("activities")

        current = _current_temp(context.connection, row["id"])
        if current == temp_c:
            context.count("unchanged")
            continue

        written = context.writer.upsert_activity_weather(
            row["id"],
            source=row["source"],
            source_record_id=row["source_record_id"],
            temp_c=temp_c,
        )
        context.count("written" if written else "unchanged")

    context.order_counts(_COUNT_ORDER)


def _rows(context: TaskContext) -> list[sqlite3.Row]:
    where = ["sr.source IN ('intervals', 'sheet')"]
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

    rows = context.connection.execute(sql, params).fetchall()
    return sorted(
        rows,
        key=lambda row: (row["local_date"], row["id"], ORDER[row["source"]]),
    )


def _temperature(source: str, payload_json: str | None) -> float | None:
    payload = _payload(payload_json)
    if payload is None:
        return None

    if source == "intervals":
        return _number(payload.get("average_temp"))

    if source == "sheet":
        raw = payload.get("values") or {}
        return _number(raw.get("Temperatur in °C"))

    return None


def _current_temp(
    connection: sqlite3.Connection,
    activity_id: str,
) -> float | None:
    row = connection.execute(
        "SELECT temp_c FROM activity_weather WHERE activity_id = ?",
        (activity_id,),
    ).fetchone()
    return None if row is None else row["temp_c"]


def _payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
