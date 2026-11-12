"""Backfill the race workout method onto existing planned events.

The Intervals importer maps ``RACE_A``/``RACE_B``/``RACE_C`` onto the canonical
``race`` method when it upserts an event, but only events inside a sync window
are rewritten. This applies the same mapping to every event linked to an
Intervals record, adding the method where the payload is a race and removing a
stale non-manual one where it is not.
"""

from __future__ import annotations

import json
import sqlite3

from hobbyjogging_import.intervals import event_methods

from ..context import TaskContext
from ..registry import task

SOURCE = "backfill"
_COUNT_ORDER = ("events", "added", "removed", "unchanged", "skipped")


@task(
    "event_race_method_v1",
    kind="backfill",
    description=(
        "Re-derive the race workout method for existing Intervals events."
    ),
)
def event_race_method(context: TaskContext) -> None:
    rows = _event_rows(context)
    if not rows:
        context.note("No events in scope.")
        return

    for row in rows:
        context.count("events")

        payload = _payload(row["payload_json"])
        if payload is None:
            context.count("skipped")
            continue

        wanted = bool(event_methods(payload))
        current = _current_methods(context.connection, row["id"])
        has_race = any(method == "race" for method, _, _ in current)

        if wanted == has_race:
            context.count("unchanged")
            continue

        if wanted:
            methods = sorted({method for method, _, _ in current} | {"race"})
            context.writer.replace_event_workout_methods(
                row["id"],
                methods,
                source=SOURCE,
                source_record_id=row["source_record_id"],
            )
            context.count("added")
            continue

        # Drop the stale race row from whichever source owns it, leaving
        # manual rows alone.
        owners = {
            source
            for method, source, manual in current
            if method == "race" and not manual
        }
        if not owners:
            # Only a manual race row remains: the human decision wins.
            context.count("unchanged")
            continue

        for owner in owners:
            remaining = sorted(
                method
                for method, source, _ in current
                if source == owner and method != "race"
            )
            context.writer.replace_event_workout_methods(
                row["id"],
                remaining,
                source=owner,
            )
        context.count("removed")

    context.order_counts(_COUNT_ORDER)

    if context.counts.get("skipped"):
        context.note(
            f"{context.counts['skipped']} events without a usable payload"
        )


def _event_rows(context: TaskContext) -> list[sqlite3.Row]:
    where = ["sr.source = 'intervals'", "sr.record_type = 'event'"]
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
        SELECT e.id, e.local_date, e.excluded_at,
               e.source_record_id, sr.payload_json
        FROM events e
        JOIN source_records sr ON sr.id = e.source_record_id
        WHERE {' AND '.join(where)}
        ORDER BY e.local_date, e.id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return [
        row
        for row in context.connection.execute(sql, params).fetchall()
        if not row["excluded_at"]
    ]


def _current_methods(
    connection: sqlite3.Connection,
    event_id: str,
) -> list[tuple[str, str, int]]:
    return [
        (row["method"], row["source"], row["is_manual"])
        for row in connection.execute(
            """
            SELECT method, source, is_manual FROM event_workout_methods
            WHERE event_id = ?
            ORDER BY method
            """,
            (event_id,),
        )
    ]


def _payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None
