"""Backfill the ``fartlek`` method for the sheet's ``fs`` rows.

The sheet's ``fs`` code (Fahrtspiel) used to map to ``intervals`` with no
target, which is how the historical fartleks ended up in the intervals bucket.
``SHEET_TYPE_CODES`` now yields ``fartlek`` + ``vo2max``; this applies the same
mapping to the activities that were imported before the change.

Manual method rows win: a session triaged by hand is skipped entirely, targets
included, so a human decision is never rewritten. An activity whose only target
is the ``other`` placeholder is left alone — the item asks for filling a
*missing* target, not for replacing a value someone chose.
"""

from __future__ import annotations

import sqlite3

from ..context import TaskContext
from ..registry import task

SOURCE = "backfill"
SHEET_CODE = "fs"
METHOD = "fartlek"
TARGET = "vo2max"

_COUNT_ORDER = (
    "activities",
    "converted",
    "unchanged",
    "skipped_manual",
    "skipped_excluded",
    "targets_filled",
)


@task(
    "fartlek_from_fs_v1",
    kind="backfill",
    description="Convert the sheet's fs (Fahrtspiel) activities to fartlek.",
)
def fartlek_from_fs(context: TaskContext) -> None:
    rows = _sheet_rows(context)
    if not rows:
        context.note("No sheet fs activities in scope.")
        return

    for row in rows:
        context.count("activities")

        if row["excluded_at"]:
            context.count("skipped_excluded")
            continue

        methods = _current(context.connection, "activity_workout_methods",
                           "method", row["id"])
        if any(manual for _, _, manual in methods):
            context.count("skipped_manual")
            continue

        current = {method for method, _, _ in methods}
        if current == {METHOD}:
            context.count("unchanged")
            continue

        context.writer.replace_activity_workout_methods(
            row["id"],
            [METHOD],
            source=SOURCE,
            source_record_id=row["source_record_id"],
        )
        context.count("converted")

        targets = _current(context.connection, "activity_workout_targets",
                           "target", row["id"])
        if not targets:
            context.writer.replace_activity_workout_targets(
                row["id"],
                [TARGET],
                source=SOURCE,
                source_record_id=row["source_record_id"],
            )
            context.count("targets_filled")

    context.order_counts(_COUNT_ORDER)

    if context.counts.get("skipped_manual"):
        context.note(
            f"{context.counts['skipped_manual']} activities kept their manual "
            "method rows"
        )


def _sheet_rows(context: TaskContext) -> list[sqlite3.Row]:
    where = [
        "sr.source = 'sheet'",
        "sr.record_type = 'activity'",
        "json_extract(sr.payload_json, '$.values.Trainigstyp') = ?",
    ]
    params: list[object] = [SHEET_CODE]

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
        SELECT a.id, a.local_date, a.excluded_at, sr.id AS source_record_id
        FROM activities a
        JOIN activity_sources als ON als.activity_id = a.id
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE {' AND '.join(where)}
        GROUP BY a.id
        ORDER BY a.local_date, a.id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()


def _current(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    activity_id: str,
) -> list[tuple[str, str, int]]:
    return [
        (row[column], row["source"], row["is_manual"])
        for row in connection.execute(
            f"""
            SELECT {column}, source, is_manual FROM {table}
            WHERE activity_id = ?
            ORDER BY {column}
            """,
            (activity_id,),
        )
    ]
