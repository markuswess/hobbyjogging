"""Rewrite activity temperature as ambient air, not the device reading.

``activity_weather_v1`` used Intervals' ``average_temp``, which is the watch
temperature, so most rows carry a warmer device value. ``temp_c`` is ambient
air only: the sheet's ``Temperatur in °C`` wins where it exists, Intervals'
``average_weather_temp`` is the fallback when ``has_weather`` is true, and a
row with neither keeps no temperature. The raw payload keeps ``average_temp``
for diagnostics.
"""

from __future__ import annotations

import json
import sqlite3

from ..context import TaskContext
from ..registry import task

SOURCES = ("intervals", "sheet")

_COUNT_ORDER = (
    "activities",
    "from_sheet",
    "from_intervals",
    "cleared",
    "unchanged",
    "skipped",
)


@task(
    "weather_ambient_v1",
    kind="backfill",
    description=(
        "Rewrite activity_weather.temp_c from ambient sources and clear the "
        "device-only rows."
    ),
)
def weather_ambient(context: TaskContext) -> None:
    rows = _rows(context)
    if not rows:
        context.note("No weather rows or weather payloads in scope.")
        return

    groups = _groups(context, rows)

    for group in groups:
        if group["excluded"]:
            context.count("skipped")
            continue

        context.count("activities")
        sheet_temp = _sheet_temp(group["payloads"].get("sheet"))
        intervals_temp = _intervals_ambient(
            group["payloads"].get("intervals")
        )

        if sheet_temp is not None:
            temp_c, source = sheet_temp, "sheet"
        elif intervals_temp is not None:
            temp_c, source = intervals_temp, "intervals"
        elif group["current_source"] == "intervals":
            temp_c, source = None, ""
        else:
            # Another source may own an ambient value; leave it alone.
            context.count("unchanged")
            continue

        record = group["payloads"].get(source) if source else None
        changed = context.writer.set_activity_ambient_temperature(
            group["id"],
            temp_c=temp_c,
            source=source or "manual",
            source_record_id=record[0] if record else None,
        )

        if not changed:
            context.count("unchanged")
        elif temp_c is None:
            context.count("cleared")
        elif source == "sheet":
            context.count("from_sheet")
        else:
            context.count("from_intervals")

    context.order_counts(_COUNT_ORDER)


def _groups(
    context: TaskContext,
    rows: list[sqlite3.Row],
) -> list[dict]:
    groups: dict[str, dict] = {}
    ordered: list[dict] = []

    for row in rows:
        group = groups.get(row["id"])
        if group is None:
            if (
                context.scope.limit is not None
                and len(ordered) >= context.scope.limit
            ):
                break
            group = {
                "id": row["id"],
                "excluded": bool(row["excluded_at"]),
                "current_source": row["current_source"] or "",
                "payloads": {},
            }
            groups[row["id"]] = group
            ordered.append(group)

        if row["source"] in SOURCES and row["source"] not in group["payloads"]:
            group["payloads"][row["source"]] = (
                row["source_record_id"],
                row["payload_json"],
            )

    return ordered


def _rows(context: TaskContext) -> list[sqlite3.Row]:
    where = [
        """(
            EXISTS (
                SELECT 1 FROM activity_weather aw
                WHERE aw.activity_id = a.id
            )
            OR EXISTS (
                SELECT 1 FROM activity_sources als
                JOIN source_records sr2 ON sr2.id = als.source_record_id
                WHERE als.activity_id = a.id
                  AND sr2.source IN ('intervals', 'sheet')
            )
        )"""
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
        SELECT a.id, a.local_date, a.excluded_at,
               aw.source AS current_source,
               sr.id AS source_record_id, sr.source, sr.payload_json
        FROM activities a
        LEFT JOIN activity_weather aw ON aw.activity_id = a.id
        LEFT JOIN activity_sources als ON als.activity_id = a.id
        LEFT JOIN source_records sr ON sr.id = als.source_record_id
                                  AND sr.source IN ('intervals', 'sheet')
        WHERE {' AND '.join(where)}
        ORDER BY a.local_date, a.id, sr.source, sr.id
    """
    return context.connection.execute(sql, params).fetchall()


def _sheet_temp(record: tuple[int | None, str | None] | None) -> float | None:
    if record is None:
        return None
    payload = _payload(record[1])
    if payload is None:
        return None
    raw = payload.get("values") or {}
    return _number(raw.get("Temperatur in °C"))


def _intervals_ambient(
    record: tuple[int | None, str | None] | None,
) -> float | None:
    if record is None:
        return None
    payload = _payload(record[1])
    if payload is None or not payload.get("has_weather"):
        return None
    return _number(payload.get("average_weather_temp"))


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
