"""Backfill stored planned-event zone kinds/times from saved payloads.

The parsing itself lives in :mod:`hobbyjogging_import.event_zones` because the
Intervals sync uses it too; only the repair pass lives here.
"""

from __future__ import annotations

import json
import sqlite3

from hobbyjogging_import.event_zones import current_zone_times, event_zone_data

from ..context import TaskContext
from ..registry import task

_COUNT_ORDER = ("events", "updated", "cleared", "unchanged", "skipped")


@task(
    "event_zones_v1",
    kind="backfill",
    description=(
        "Rewrite stored event zone kinds/times from saved Intervals payloads."
    ),
)
def event_zones(context: TaskContext) -> None:
    """Re-derive event zones from the payloads already in the database.

    Only events linked to an Intervals event record are considered.
    Soft-excluded events and malformed payloads are skipped. Writes happen
    only when the stored kind or distribution differs, so repeated runs are
    idempotent and do not touch ``updated_at``.
    """
    rows = _event_rows(context)
    if not rows:
        context.note("No events in scope.")
        return

    current = current_zone_times(
        context.connection,
        [row["id"] for row in rows],
    )

    for row in rows:
        context.count("events")

        if row["excluded_at"]:
            context.count("skipped")
            continue

        payload = _payload(row["payload_json"])
        if payload is None:
            context.count("skipped")
            continue

        kind, zones = event_zone_data(payload, row["type"])
        desired = {zone.zone_label: float(zone.seconds) for zone in zones}
        existing = current.get(row["id"], {})

        if row["zone_kind"] == kind and existing == desired:
            context.count("unchanged")
            continue

        context.count("updated")
        if not kind and not zones and (row["zone_kind"] or existing):
            context.count("cleared")

        context.writer.set_event_zone_times(row["id"], kind, zones)

    if context.counts.get("skipped"):
        context.note(
            f"{context.counts['skipped']} events skipped "
            "(excluded or without a usable payload)"
        )

    context.order_counts(_COUNT_ORDER)


def _event_rows(context: TaskContext) -> list[sqlite3.Row]:
    where = [
        "sr.source = 'intervals'",
        "sr.record_type = 'event'",
    ]
    params: list[object] = []

    if context.scope.start is not None:
        where.append("e.local_date >= ?")
        params.append(context.scope.start.isoformat())
    if context.scope.end is not None:
        where.append("e.local_date <= ?")
        params.append(context.scope.end.isoformat())
    if context.scope.entity_id is not None:
        where.append("e.id = ?")
        params.append(context.scope.entity_id)

    sql = f"""
        SELECT e.id, e.name, e.type, e.local_date, e.zone_kind,
               e.excluded_at, sr.payload_json
        FROM events e
        JOIN source_records sr ON sr.id = e.source_record_id
        WHERE {' AND '.join(where)}
        ORDER BY e.local_date, e.name
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()


def _payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None
