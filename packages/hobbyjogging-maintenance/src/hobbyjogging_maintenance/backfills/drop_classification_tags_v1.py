"""Drop the sheet's ``Trainigstyp`` codes from ``activity_tags``.

The type code duplicates the method/target sets, which carry the same
information with a canonical vocabulary. The training *area*
(``Trainingsgebiet``) is orthogonal and stays a tag; manual tags are never
touched.

The code set comes from ``SHEET_TYPE_CODES`` so it cannot drift from the
importer's mapping.
"""

from __future__ import annotations

import sqlite3

from hobbyjogging_core.workouts import SHEET_TYPE_CODES

from ..context import TaskContext
from ..registry import task

SOURCE = "sheet"
CODE_TAGS = frozenset(SHEET_TYPE_CODES)

_COUNT_ORDER = ("activities", "tags_removed", "unchanged", "skipped")


@task(
    "drop_classification_tags_v1",
    kind="backfill",
    description="Remove the sheet's Trainigstyp codes from activity tags.",
)
def drop_classification_tags(context: TaskContext) -> None:
    rows = _activities_with_codes(context)
    if not rows:
        context.note("No classification tags in scope.")
        return

    for row in rows:
        context.count("activities")

        if row["excluded_at"]:
            context.count("skipped")
            continue

        tags = _sheet_tags(context.connection, row["id"])
        remaining = [tag for tag in tags if tag not in CODE_TAGS]

        if len(remaining) == len(tags):
            context.count("unchanged")
            continue

        context.writer.replace_activity_tags(
            row["id"],
            remaining,
            source=SOURCE,
        )
        context.count("tags_removed", len(tags) - len(remaining))

    context.order_counts(_COUNT_ORDER)


def _activities_with_codes(context: TaskContext) -> list[sqlite3.Row]:
    placeholders = ", ".join("?" for _ in CODE_TAGS)
    where = [
        "t.source = ?",
        "t.is_manual = 0",
        f"t.tag IN ({placeholders})",
    ]
    params: list[object] = [SOURCE, *sorted(CODE_TAGS)]

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
        SELECT a.id, a.local_date, a.excluded_at
        FROM activities a
        JOIN activity_tags t ON t.activity_id = a.id
        WHERE {' AND '.join(where)}
        GROUP BY a.id
        ORDER BY a.local_date, a.id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()


def _sheet_tags(connection: sqlite3.Connection, activity_id: str) -> list[str]:
    return [
        row["tag"]
        for row in connection.execute(
            """
            SELECT tag FROM activity_tags
            WHERE activity_id = ? AND source = ? AND is_manual = 0
            ORDER BY tag
            """,
            (activity_id, SOURCE),
        )
    ]
