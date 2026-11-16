"""Point every activity at the zone configs of its era.

Intervals stamps the zone boundaries on each activity, so the boundaries are
shared by the activities of a period rather than duplicated per row. This
recompute creates one ``zone_configs`` row per distinct boundary set and sets
the activity's ``hr_zone_config_id`` / ``pace_zone_config_id``, which makes
"Z3" mean the same thing across eras.

Only Intervals supplies boundaries; Runalyze's zone distributions are
percentages computed from its own settings and are not a config.
"""

from __future__ import annotations

import json

from ..context import TaskContext
from ..registry import task

SOURCE = "intervals"

_COUNT_ORDER = ("activities", "configs_used", "updated", "unchanged", "skipped")


@task(
    "activity_zone_configs_current",
    kind="recompute",
    description="Link activities to the zone configs of their era.",
)
def activity_zone_configs_current(context: TaskContext) -> None:
    rows = _rows(context)
    if not rows:
        context.note("No Intervals payloads in scope.")
        return

    configs: set[str] = set()

    for row in rows:
        context.count("activities")

        payload = _payload(row["payload_json"])
        if payload is None:
            context.count("skipped")
            continue

        hr = _boundaries(payload.get("icu_hr_zones"))
        pace = _boundaries(payload.get("pace_zones"))

        if not hr and not pace:
            context.count("skipped")
            continue

        hr_id = (
            context.writer.upsert_zone_config(
                kind="hr", boundaries=hr, source=SOURCE
            )
            if hr
            else None
        )
        pace_id = (
            context.writer.upsert_zone_config(
                kind="pace", boundaries=pace, source=SOURCE
            )
            if pace
            else None
        )

        for config_id in (hr_id, pace_id):
            if config_id is not None and config_id not in configs:
                configs.add(config_id)
                context.count("configs_used")

        current = _current(context, row["id"])
        if current == (hr_id, pace_id):
            context.count("unchanged")
            continue

        context.writer.set_activity_zone_configs(
            row["id"],
            hr_zone_config_id=hr_id,
            pace_zone_config_id=pace_id,
        )
        context.count("updated")

    context.order_counts(_COUNT_ORDER)


def _rows(context: TaskContext) -> list:
    where = ["sr.source = 'intervals'", "sr.record_type = 'activity'"]
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
        SELECT a.id, a.local_date, sr.payload_json
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        JOIN activities a ON a.id = als.activity_id
        WHERE {' AND '.join(where)}
          AND a.excluded_at IS NULL
        ORDER BY a.local_date, a.id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()


def _current(context: TaskContext, activity_id: str) -> tuple:
    row = context.connection.execute(
        """
        SELECT hr_zone_config_id, pace_zone_config_id
        FROM activities WHERE id = ?
        """,
        (activity_id,),
    ).fetchone()
    return (row["hr_zone_config_id"], row["pace_zone_config_id"])


def _boundaries(value: object) -> list[float]:
    if not isinstance(value, list):
        return []

    boundaries = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return []
        boundaries.append(float(item))

    return boundaries


def _payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None
