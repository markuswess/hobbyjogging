"""Backfill elevation and maximum heart rate from the stored payloads.

Schema v12 added ``activities.elevation_gain_m``, ``elevation_loss_m`` and
``max_hr``. The importers write them from now on; this fills the existing rows
from the payloads already in the database, in the order the sources were
imported (Intervals, FIT, sheet) so the first owner matches a fresh import.

The writes go through ``TrainingWriter.upsert_activity``, so ownership and the
field tolerances hold: a value is only filled when the field has no owner, and
a manual value is never touched. A disagreement between sources is counted, not
queued: the review queue is for imports, and a column backfill that opened
ninety items would be noise. The wide tolerance already means only a real
disagreement is counted.
"""

from __future__ import annotations

import json
import sqlite3

from ..context import TaskContext
from ..registry import task

SOURCES = ("intervals", "fit", "sheet")
ORDER = {source: index for index, source in enumerate(SOURCES)}

_COUNT_ORDER = ("activities", "written", "unchanged", "skipped", "conflicts")


@task(
    "activity_elevation_v1",
    kind="backfill",
    description="Fill elevation gain and loss from the stored payloads.",
)
def activity_elevation(context: TaskContext) -> None:
    _run(context, ("elevation_gain_m", "elevation_loss_m"))


@task(
    "activity_max_hr_v1",
    kind="backfill",
    description="Fill the maximum heart rate from the stored payloads.",
)
def activity_max_hr(context: TaskContext) -> None:
    _run(context, ("max_hr",))


def _run(context: TaskContext, fields: tuple[str, ...]) -> None:
    rows = _rows(context)
    if not rows:
        context.note("No source payloads in scope.")
        return

    seen: set[str] = set()

    for row in rows:
        activity_id = row["id"]

        if row["excluded_at"]:
            continue

        values = _extract(row["source"], row["payload_json"], fields)
        manual = _manual_fields(context.connection, activity_id, fields)
        values = {
            key: value
            for key, value in values.items()
            if key not in manual
        }
        if not values:
            continue

        if activity_id not in seen:
            seen.add(activity_id)
            context.count("activities")

        current = _current(context.connection, activity_id, fields)
        if all(current.get(key) == value for key, value in values.items()):
            context.count("unchanged")
            continue

        conflicts = context.writer.upsert_activity(
            activity_id,
            values,
            source=row["source"],
            source_record_id=row["source_record_id"],
        )
        context.count("written")
        context.count("conflicts", len(conflicts))

    context.order_counts(_COUNT_ORDER)


def _rows(context: TaskContext) -> list[sqlite3.Row]:
    where = ["sr.source IN ('intervals', 'fit', 'sheet')"]
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


def _extract(
    source: str,
    payload_json: str | None,
    fields: tuple[str, ...],
) -> dict[str, object]:
    payload = _payload(payload_json)
    if payload is None:
        return {}

    if source == "intervals":
        values = {
            "elevation_gain_m": _number(payload.get("total_elevation_gain")),
            "elevation_loss_m": _number(payload.get("total_elevation_loss")),
            "max_hr": _number(payload.get("max_heartrate")),
        }
    elif source == "sheet":
        raw = payload.get("values") or {}
        values = {
            "elevation_gain_m": _number(raw.get("m bergauf")),
            "elevation_loss_m": None,
            "max_hr": _number(raw.get("max. Hf")),
        }
    elif source == "fit":
        session = payload.get("session") or {}
        values = {
            "elevation_gain_m": _number(session.get("ascent_m")),
            "elevation_loss_m": _number(session.get("descent_m")),
            "max_hr": _number(session.get("max_hr")),
        }
    else:
        return {}

    return {
        field: values[field]
        for field in fields
        if values.get(field) is not None
    }


def _current(
    connection: sqlite3.Connection,
    activity_id: str,
    fields: tuple[str, ...],
) -> dict[str, object]:
    columns = ", ".join(fields)
    row = connection.execute(
        f"SELECT {columns} FROM activities WHERE id = ?",
        (activity_id,),
    ).fetchone()
    return {field: row[field] for field in fields} if row else {}


def _manual_fields(
    connection: sqlite3.Connection,
    activity_id: str,
    fields: tuple[str, ...],
) -> set[str]:
    rows = connection.execute(
        "SELECT field_name FROM activity_field_sources "
        "WHERE activity_id = ? AND is_manual = 1",
        (activity_id,),
    ).fetchall()
    return {
        row["field_name"]
        for row in rows
        if row["field_name"] in fields
    }


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
