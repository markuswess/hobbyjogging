"""Backfill route identity and links from the stored sheet payloads.

The sheet's ``Strecke`` / ``Streckennummer`` is the only route source before
2022. This reads the stored payloads (not the workbook), resolves each row to
a route and links the matched activity. A numbered row is keyed by its number;
a name-only row reuses the number seen for the same name elsewhere in the
sheet. Re-running it is a no-op.
"""

from __future__ import annotations

import json
import sqlite3

from hobbyjogging_import.routes import numbers_by_name, route_identity

from ..context import TaskContext
from ..registry import task

SOURCE = "sheet"
_COUNT_ORDER = ("records", "routes", "linked", "unchanged", "skipped")


@task(
    "activity_routes_v1",
    kind="backfill",
    description="Link sheet activities to their routes (Strecke/Streckennummer).",
)
def activity_routes(context: TaskContext) -> None:
    rows = _sheet_rows(context)
    if not rows:
        context.note("No sheet activity payloads in scope.")
        return

    known = numbers_by_name(
        (values.get("Strecke"), values.get("Streckennummer"))
        for values in (_values(row["payload_json"]) for row in rows)
    )

    routes: set[str] = set()
    for row in rows:
        context.count("records")

        values = _values(row["payload_json"])
        route = route_identity(
            values.get("Strecke"),
            values.get("Streckennummer"),
            known,
        )
        if route is None:
            context.count("skipped")
            continue

        activity_id = row["activity_id"]
        current = _current(context.connection, activity_id)
        if current == [route.id]:
            context.count("unchanged")
            continue

        context.writer.upsert_route(
            route.id,
            name=route.name,
            external_ref=route.external_ref,
            source=SOURCE,
        )
        routes.add(route.id)
        context.writer.replace_activity_routes(
            activity_id,
            [route.id],
            source=SOURCE,
            source_record_id=row["source_record_id"],
        )
        context.count("linked")

    context.count("routes", len(routes))
    context.order_counts(_COUNT_ORDER)


def _sheet_rows(context: TaskContext) -> list[sqlite3.Row]:
    where = ["sr.source = 'sheet'", "sr.record_type = 'activity'"]
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
        SELECT
            sr.id AS source_record_id,
            sr.payload_json,
            als.activity_id
        FROM source_records sr
        JOIN activity_sources als ON als.source_record_id = sr.id
        JOIN activities a ON a.id = als.activity_id
        WHERE {' AND '.join(where)}
          AND a.excluded_at IS NULL
        ORDER BY a.local_date, a.id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()


def _current(connection: sqlite3.Connection, activity_id: str) -> list[str]:
    return [
        row["route_id"]
        for row in connection.execute(
            """
            SELECT route_id FROM activity_routes
            WHERE activity_id = ? AND source = ?
            ORDER BY route_id
            """,
            (activity_id, SOURCE),
        )
    ]


def _values(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    values = payload.get("values")
    return values if isinstance(values, dict) else {}
