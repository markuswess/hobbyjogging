"""Drop the empty interval artifact Intervals appends to an activity.

Intervals adds a trailing 1 s / 0 m ``RECOVERY`` interval (occasionally a
``WORK`` one) to the interval list. The importer now filters it while building
the list; this backfill repairs activities imported before that filter
existed. The predicate stays in :mod:`hobbyjogging_import.intervals` so the
live import path and this repair cannot drift. Raw payloads keep the original
rows as provenance.
"""

from __future__ import annotations

import sqlite3

from hobbyjogging_core.model import Interval
from hobbyjogging_import.intervals import is_empty_interval

from ..context import TaskContext
from ..registry import task

_COUNT_ORDER = ("activities", "dropped", "kept", "cleared", "unchanged")


@task(
    "drop_empty_intervals_v1",
    kind="backfill",
    description=(
        "Drop the empty 1 s / 0 m Intervals artifact from stored interval "
        "sets."
    ),
)
def drop_empty_intervals(context: TaskContext) -> None:
    """Rewrite every interval set that still contains the empty artifact.

    Only activities with stored intervals are considered, so an activity that
    never had any is not reported. Sets without an empty row are left
    untouched, which makes a forced rerun a no-op; the raw Intervals payloads
    keep the dropped rows.
    """
    activity_ids = _activity_ids(context)
    if not activity_ids:
        _require_known_entity(context)
        context.note("No activities with intervals in scope.")
        return

    for activity_id in activity_ids:
        context.count("activities")
        rows = _interval_rows(context.connection, activity_id)
        intervals = [_interval(row) for row in rows]
        kept = [
            interval
            for interval in intervals
            if not is_empty_interval(interval)
        ]
        dropped = len(intervals) - len(kept)

        if not dropped:
            context.count("unchanged")
            continue

        context.writer.replace_activity_intervals(
            activity_id,
            kept,
            source_record_id=_source_record_id(rows),
        )
        context.count("dropped", dropped)
        context.count("kept", len(kept))
        if not kept:
            context.count("cleared")

    context.order_counts(_COUNT_ORDER)

    if context.counts.get("cleared"):
        context.note(
            f"{context.counts['cleared']} activities now have no intervals"
        )


def _activity_ids(context: TaskContext) -> list[str]:
    """In-scope, non-excluded activities that have stored intervals."""
    where = [
        "a.excluded_at IS NULL",
        """
        EXISTS (
            SELECT 1 FROM activity_intervals i
            WHERE i.activity_id = a.id
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
        SELECT a.id
        FROM activities a
        WHERE {' AND '.join(where)}
        ORDER BY a.local_date, a.id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return [
        row["id"]
        for row in context.connection.execute(sql, params).fetchall()
    ]


def _interval_rows(
    connection: sqlite3.Connection,
    activity_id: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT interval_index, group_id, type, start_time,
               duration_s, distance_m, avg_hr, max_hr, source_record_id
        FROM activity_intervals
        WHERE activity_id = ?
        ORDER BY interval_index
        """,
        (activity_id,),
    ).fetchall()


def _interval(row: sqlite3.Row) -> Interval:
    return Interval(
        group_id=row["group_id"],
        type=row["type"],
        start_time=row["start_time"],
        duration_s=row["duration_s"],
        distance_m=row["distance_m"],
        avg_hr=row["avg_hr"],
        max_hr=row["max_hr"],
    )


def _source_record_id(rows: list[sqlite3.Row]) -> int | None:
    """The interval set's source record; the writer keeps one per activity."""
    for row in rows:
        if row["source_record_id"] is not None:
            return row["source_record_id"]
    return None


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
