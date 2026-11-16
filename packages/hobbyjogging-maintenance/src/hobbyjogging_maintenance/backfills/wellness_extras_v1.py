"""Backfill the wellness extras from the stored payloads.

Schema v19 added weight, sleep score and quality, SpO2, steps, floors climbed
and Intervals' own CTL/ATL. The wellness payloads already carry them; this
fills the columns without touching the three values that were stored before.

The sheet's ``Gewicht nachher`` is a per-session weight, so it lands on that
day's wellness row when Intervals has no weight for it.
"""

from __future__ import annotations

import json

from ..context import TaskContext
from ..registry import task

INTERVALS = "intervals"
SHEET = "sheet"

FIELDS = (
    "weight_kg",
    "sleep_score",
    "sleep_quality",
    "spo2",
    "steps",
    "floors_climbed",
    "ctl",
    "atl",
)

_COUNT_ORDER = ("days", "written", "unchanged", "skipped")


@task(
    "wellness_extras_v1",
    kind="backfill",
    description="Fill the wellness extras from the stored payloads.",
)
def wellness_extras(context: TaskContext) -> None:
    written = 0
    unchanged = 0
    days: set[str] = set()

    for row in _wellness_rows(context):
        payload = _payload(row["payload_json"])
        if payload is None:
            context.count("skipped")
            continue

        values = {
            "weight_kg": _number(payload.get("weight")),
            "sleep_score": _number(payload.get("sleepScore")),
            "sleep_quality": _number(payload.get("sleepQuality")),
            "spo2": _number(payload.get("spO2")),
            "steps": _integer(payload.get("steps")),
            "floors_climbed": _integer(payload.get("floorsClimbed")),
            "ctl": _number(payload.get("ctl")),
            "atl": _number(payload.get("atl")),
        }
        values = {
            key: value for key, value in values.items() if value is not None
        }
        if not values:
            context.count("skipped")
            continue

        days.add(row["local_date"])
        current = _current(context, row["local_date"])
        if all(current.get(key) == value for key, value in values.items()):
            unchanged += 1
            continue

        context.writer.upsert_wellness(
            local_date=row["local_date"],
            source_record_id=row["source_record_id"],
            **values,
        )
        written += 1

    for row in _sheet_rows(context):
        payload = _payload(row["payload_json"])
        if payload is None:
            continue

        raw = payload.get("values") or {}
        weight = _number(raw.get("Gewicht nachher"))
        day = str(row["local_date"] or "")[:10]
        if weight is None or not day:
            continue

        current = _current(context, day)
        if current.get("weight_kg") is not None:
            continue

        days.add(day)
        context.writer.upsert_wellness(
            local_date=day,
            source_record_id=row["source_record_id"],
            weight_kg=weight,
        )
        written += 1

    context.count("days", len(days))
    context.count("written", written)
    context.count("unchanged", unchanged)
    context.order_counts(_COUNT_ORDER)


def _wellness_rows(context: TaskContext) -> list:
    return context.connection.execute(
        """
        SELECT sr.id AS source_record_id, sr.external_id AS local_date,
               sr.payload_json
        FROM source_records sr
        WHERE sr.source = 'intervals' AND sr.record_type = 'wellness'
        ORDER BY sr.external_id
        """
    ).fetchall()


def _sheet_rows(context: TaskContext) -> list:
    return context.connection.execute(
        """
        SELECT sr.id AS source_record_id, a.local_date, sr.payload_json
        FROM source_records sr
        JOIN activity_sources als ON als.source_record_id = sr.id
        JOIN activities a ON a.id = als.activity_id
        WHERE sr.source = 'sheet' AND sr.record_type = 'activity'
        ORDER BY a.local_date
        """
    ).fetchall()


def _current(context: TaskContext, local_date: str) -> dict:
    columns = ", ".join(FIELDS)
    row = context.connection.execute(
        f"SELECT {columns} FROM wellness_days WHERE local_date = ?",
        (local_date,),
    ).fetchone()
    return {key: row[key] for key in FIELDS} if row else {}


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


def _integer(value: object) -> int | None:
    number = _number(value)
    return None if number is None else int(round(number))
