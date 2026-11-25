"""Backfill session-average metrics from the stored payloads and FIT archive.

Schema v27 added ``activity_metrics``. New imports write it directly; this
fills the existing rows. Intervals, Runalyze and the sheet payloads already
carry the averages. The stored FIT payloads predate the new fields, so a FIT
row is re-read from ``source_records.raw_path`` and the matching session is
selected by the external-id suffix. A file is parsed once per run.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from hobbyjogging_core.import_rules import METRIC_FIELDS
from hobbyjogging_import.fit import FitFileSummary, parse_fit_file
from hobbyjogging_import.metrics import derive_metrics

from ..context import TaskContext
from ..registry import task

SOURCES = ("fit", "intervals", "runalyze", "sheet")
ORDER = {source: index for index, source in enumerate(SOURCES)}

_COUNT_ORDER = ("activities", "written", "unchanged", "skipped")


@task(
    "activity_metrics_v1",
    kind="backfill",
    description="Fill activity_metrics from the stored payloads and FIT archive.",
)
def activity_metrics(context: TaskContext) -> None:
    rows = _rows(context)
    if not rows:
        context.note("No metric payloads in scope.")
        return

    seen: set[str] = set()
    cache: dict[str, FitFileSummary | None] = {}

    for row in rows:
        if row["excluded_at"]:
            continue

        values = _extract(row, context, cache)
        if not values:
            context.count("skipped")
            continue

        activity_id = row["id"]
        if activity_id not in seen:
            seen.add(activity_id)
            context.count("activities")

        current = _current(context.connection, activity_id)
        if current is not None and all(
            current.get(field) == value for field, value in values.items()
        ):
            context.count("unchanged")
            continue

        written = context.writer.upsert_activity_metrics(
            activity_id,
            source=row["source"],
            source_record_id=row["source_record_id"],
            **values,
        )
        context.count("written" if written else "unchanged")

    context.order_counts(_COUNT_ORDER)


def _rows(context: TaskContext) -> list[sqlite3.Row]:
    where = [
        "sr.source IN ('fit', 'intervals', 'runalyze', 'sheet')",
        "sr.record_type = 'activity'",
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
        SELECT a.id, a.local_date, a.excluded_at, a.sport,
               sr.id AS source_record_id, sr.source, sr.payload_json,
               sr.raw_path, sr.external_id
        FROM activities a
        JOIN activity_sources als ON als.activity_id = a.id
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE {' AND '.join(where)}
        ORDER BY a.local_date, a.id, sr.source
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    rows = context.connection.execute(sql, params).fetchall()
    return sorted(
        rows,
        key=lambda row: (
            row["local_date"],
            row["id"],
            ORDER[row["source"]],
        ),
    )


def _extract(
    row: sqlite3.Row,
    context: TaskContext,
    cache: dict[str, FitFileSummary | None],
) -> dict[str, float]:
    payload = _payload(row["payload_json"])
    if payload is None:
        payload = {}

    if row["source"] != "fit":
        return derive_metrics(row["source"], payload, row["sport"] or "")

    session = payload.get("session")
    if isinstance(session, dict) and any(
        session.get(field) is not None for field in _FIT_KEYS
    ):
        return derive_metrics("fit", payload, row["sport"] or "")

    raw_path = row["raw_path"]
    if not raw_path:
        return {}

    summary = cache.get(raw_path)
    if raw_path not in cache:
        path = Path(raw_path).expanduser()
        if path.is_file():
            try:
                summary = parse_fit_file(path)
            except Exception:
                summary = None
        else:
            summary = None
        cache[raw_path] = summary

    if summary is None or not summary.sessions:
        return {}

    index = _session_index(row["external_id"])
    if index is None or not 1 <= index <= len(summary.sessions):
        return {}

    fit_session = summary.sessions[index - 1]
    return derive_metrics(
        "fit",
        {"session": asdict(fit_session)},
        row["sport"] or "",
    )


def _session_index(external_id: str | None) -> int | None:
    if not external_id:
        return None
    suffix = str(external_id).rsplit(":", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return None


def _current(
    connection: sqlite3.Connection,
    activity_id: str,
) -> dict[str, object] | None:
    columns = ", ".join(METRIC_FIELDS)
    row = connection.execute(
        f"SELECT {columns} FROM activity_metrics WHERE activity_id = ?",
        (activity_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _payload(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


# The stored FIT payload carries these keys after item 38; an older payload
# has none of them and is re-read from the archive.
_FIT_KEYS = (
    "cadence",
    "stride_m",
    "vertical_oscillation_mm",
    "stance_time_ms",
    "stance_time_pct",
    "stance_balance_pct",
    "vertical_ratio_pct",
    "respiration_bpm",
    "power_w",
    "training_effect",
)
