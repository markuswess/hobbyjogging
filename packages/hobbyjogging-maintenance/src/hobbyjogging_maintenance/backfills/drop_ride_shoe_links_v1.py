"""Remove historical sheet shoe links from rides.

The sheet's ``Schuhe`` column was linked regardless of sport, so a shoe can be
the primary equipment on a ride. A shoe is a walking/running item; remove only
the source links on ride sports, never a manual link, and leave every other
sport (including hiking) alone.
"""

from __future__ import annotations

from hobbyjogging_core.sports import RIDE_SPORTS

from ..context import TaskContext
from ..registry import task

SOURCE = "sheet"
_COUNT_ORDER = ("rides", "removed", "kept")


@task(
    "drop_ride_shoe_links_v1",
    kind="backfill",
    description=(
        "Remove the sheet's source shoe links from rides; keep manual links "
        "and every other sport."
    ),
)
def drop_ride_shoe_links(context: TaskContext) -> None:
    rows = _rows(context)
    if not rows:
        context.note("No ride shoe links in scope.")
        return

    seen: set[str] = set()

    for row in rows:
        activity_id = row["activity_id"]
        if activity_id not in seen:
            seen.add(activity_id)
            context.count("rides")

        removed = context.writer.unlink_activity_equipment(
            activity_id,
            source=SOURCE,
            equipment_type="shoe",
        )
        if removed:
            context.count("removed")
            context.output_lines.append(
                f"{row['local_date']} {activity_id}: "
                f"removed {removed} sheet shoe link(s)"
            )
        else:
            context.count("kept")

    context.order_counts(_COUNT_ORDER)
    context.write_output()


def _rows(context: TaskContext):
    placeholders = ", ".join("?" for _ in RIDE_SPORTS)
    where = [
        "ae.source = ?",
        "ae.is_manual = 0",
        "e.type = 'shoe'",
        f"a.sport IN ({placeholders})",
    ]
    params: list[object] = [SOURCE, *sorted(RIDE_SPORTS)]

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
        SELECT ae.activity_id, a.local_date
        FROM activity_equipment ae
        JOIN activities a ON a.id = ae.activity_id
        JOIN equipment e ON e.id = ae.equipment_id
        WHERE {' AND '.join(where)}
        ORDER BY a.local_date, ae.activity_id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()
