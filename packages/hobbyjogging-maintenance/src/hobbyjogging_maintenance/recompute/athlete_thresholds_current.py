"""Derive the dated athlete-threshold series from the Intervals payloads.

Intervals stamps the athlete's settings on every activity, so the series is
the deduplicated sequence of those settings: a new snapshot starts when any
value changes. A missing value (an implausible or zero threshold pace) carries
the previous one forward rather than creating a snapshot with a gap.

Runalyze has no such history, so this recompute owns the series alone: there is
no second source to reconcile, and ``source`` is provenance.
"""

from __future__ import annotations

import json
import math

from ..context import TaskContext
from ..registry import task

SOURCE = "intervals"
PAUSE_MIN_MPS = 1.5

_COUNT_ORDER = ("payloads", "snapshots", "unchanged", "skipped")


@task(
    "athlete_thresholds_current",
    kind="recompute",
    description="Re-derive the dated threshold snapshots from the payloads.",
)
def athlete_thresholds_current(context: TaskContext) -> None:
    rows = _payload_rows(context)
    if not rows:
        context.note("No Intervals payloads in scope.")
        return

    # Thresholds are per sport: Intervals stamps the settings of the activity's
    # own sport, so the running series and the cycling one are separate. One
    # snapshot per sport and date: two activities on the same day can differ
    # (one carries a threshold pace, the other does not), and the later wins.
    by_sport: dict[str, dict[str, dict[str, object]]] = {}
    current: dict[str, dict[str, object]] = {}

    for row in rows:
        context.count("payloads")

        payload = _payload(row["payload_json"])
        if payload is None:
            context.count("skipped")
            continue

        sport = row["sport"] or ""
        values = _values(payload)
        merged = {**current.get(sport, {}), **values}

        if merged == current.get(sport, {}):
            continue

        current[sport] = merged
        by_sport.setdefault(sport, {})[row["local_date"]] = {
            "effective_from": row["local_date"],
            "sport": sport,
            "max_hr": merged.get("max_hr"),
            "lthr": merged.get("lthr"),
            "threshold_pace_mps": merged.get("threshold_pace_mps"),
            "source_record_id": row["source_record_id"],
        }

    snapshots = [
        by_sport[sport][day]
        for sport in sorted(by_sport)
        for day in sorted(by_sport[sport])
    ]
    existing = _existing(context)
    if existing == [
        (
            item["sport"],
            item["effective_from"],
            item["max_hr"],
            item["lthr"],
            item["threshold_pace_mps"],
        )
        for item in snapshots
    ]:
        context.count("unchanged", len(snapshots))
        return

    written = context.writer.replace_athlete_thresholds(
        snapshots,
        source=SOURCE,
    )
    context.count("snapshots", written)
    context.order_counts(_COUNT_ORDER)


def _payload_rows(context: TaskContext) -> list:
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
        SELECT a.local_date, a.sport, sr.id AS source_record_id,
               sr.payload_json
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        JOIN activities a ON a.id = als.activity_id
        WHERE {' AND '.join(where)}
          AND a.excluded_at IS NULL
        ORDER BY a.local_date, a.started_at_utc, a.id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return context.connection.execute(sql, params).fetchall()


def _existing(context: TaskContext) -> list[tuple]:
    return [
        (
            row["sport"],
            row["effective_from"],
            row["max_hr"],
            row["lthr"],
            row["threshold_pace_mps"],
        )
        for row in context.connection.execute(
            """
            SELECT sport, effective_from, max_hr, lthr, threshold_pace_mps
            FROM athlete_thresholds
            WHERE source = ?
            ORDER BY sport, effective_from, id
            """,
            (SOURCE,),
        )
    ]


def _values(payload: dict) -> dict[str, object]:
    values: dict[str, object] = {}

    max_hr = _number(payload.get("athlete_max_hr"))
    if max_hr is not None:
        values["max_hr"] = max_hr

    lthr = _number(payload.get("lthr"))
    if lthr is not None:
        values["lthr"] = lthr

    pace = _number(payload.get("threshold_pace"))
    if pace is not None and math.isfinite(pace) and pace >= PAUSE_MIN_MPS:
        values["threshold_pace_mps"] = pace

    return values


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
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
