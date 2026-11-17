"""Derive the training periods from the Intervals event notes.

Intervals stores the season starts as ``SEASON_START`` events ("VCM 23/24/25")
and the sickness and travel notes as ``SICK`` / ``NOTE``. This turns them into
dated periods:

- a season runs from its start to the day before the next one, and the latest
  stays open;
- a sickness or note keeps the source's inclusive range: ``end_date_local``
  when present, otherwise the start day. The source says how long it lasted,
  so the range is stored; the recompute never invents an end.

Manual rows are never removed: the recompute replaces only its own source.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from ..context import TaskContext
from ..registry import task

SOURCE = "intervals"
SEASON = "SEASON_START"
SICK = "SICK"
NOTE = "NOTE"

_COUNT_ORDER = ("events", "periods", "unchanged", "skipped")


@task(
    "training_periods_current",
    kind="recompute",
    description="Derive seasons and illness ranges from the event notes.",
)
def training_periods_current(context: TaskContext) -> None:
    rows = _payload_rows(context)
    if not rows:
        context.note("No event payloads in scope.")
        return

    seasons: list[dict[str, object]] = []
    ranges: list[dict[str, object]] = []

    for row in rows:
        payload = _payload(row["payload_json"])
        if payload is None:
            context.count("skipped")
            continue

        category = payload.get("category")
        day = _date(payload.get("start_date_local") or payload.get("date"))
        if day is None or category not in (SEASON, SICK, NOTE):
            context.count("skipped")
            continue

        context.count("events")
        event_id = str(payload.get("id") or "")
        name = str(payload.get("name") or "").strip()

        if category == SEASON:
            seasons.append({
                "id": f"{SOURCE}:season:{event_id}",
                "kind": "season",
                "label": name,
                "start": day,
                "end": None,
                "source_record_id": row["source_record_id"],
            })
            continue

        end = _date(payload.get("end_date_local")) or day
        if end < day:
            end = day

        ranges.append({
            "id": f"{SOURCE}:{category.lower()}:{event_id}",
            "kind": "illness" if category == SICK else "other",
            "label": name,
            "start": day,
            "end": end,
            "source_record_id": row["source_record_id"],
        })

    periods = _close_seasons(seasons) + ranges
    periods.sort(key=lambda item: (item["start"], item["id"]))

    existing = _existing(context)
    if existing == [
        (
            item["id"],
            item["kind"],
            item["label"],
            item["start"].isoformat(),
            item["end"].isoformat() if item["end"] else None,
        )
        for item in periods
    ]:
        context.count("unchanged", len(periods))
        return

    written = context.writer.replace_training_periods(
        [
            {
                "id": item["id"],
                "kind": item["kind"],
                "label": item["label"],
                "start_date": item["start"].isoformat(),
                "end_date": item["end"].isoformat() if item["end"] else None,
                "source_record_id": item["source_record_id"],
            }
            for item in periods
        ],
        source=SOURCE,
    )
    context.count("periods", written)
    context.order_counts(_COUNT_ORDER)


def _close_seasons(seasons: list[dict[str, object]]) -> list[dict[str, object]]:
    """End each season the day before the next one; the latest stays open."""
    ordered = sorted(seasons, key=lambda item: item["start"])

    for index, season in enumerate(ordered):
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        season["end"] = (
            following["start"] - timedelta(days=1) if following else None
        )

    return ordered


def _payload_rows(context: TaskContext) -> list:
    sql = """
        SELECT sr.id AS source_record_id, sr.payload_json
        FROM source_records sr
        WHERE sr.source = 'intervals' AND sr.record_type = 'event'
        ORDER BY sr.id
    """
    return context.connection.execute(sql).fetchall()


def _existing(context: TaskContext) -> list[tuple]:
    return [
        (
            row["id"],
            row["kind"],
            row["label"],
            row["start_date"],
            row["end_date"],
        )
        for row in context.connection.execute(
            """
            SELECT id, kind, label, start_date, end_date
            FROM training_periods
            WHERE source = ?
            ORDER BY start_date, id
            """,
            (SOURCE,),
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


def _date(value: object) -> date | None:
    text = str(value or "")[:10]
    if len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
