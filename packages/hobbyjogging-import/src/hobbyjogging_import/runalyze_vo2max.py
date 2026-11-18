"""Fill ``vo2max_runalyze`` from stored Runalyze activity payloads.

Phase 5 is offline: the detail payloads already sit in ``source_records``, so
no request is needed. Runalyze's ``vo2max`` is its *effective* estimate and
sits beside ``vo2max_by_time`` and ``vo2max_with_elevation``; only the
effective value is stored, under the second VO2max owner. ``vo2max_garmin`` is
never touched and an activity without a Runalyze link is never guessed.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from hobbyjogging_core import TrainingWriter

SOURCE = "runalyze"


@dataclass
class RunalyzeVo2maxSummary:
    run_id: int | None = None
    dry_run: bool = False
    payloads: int = 0
    with_value: int = 0
    written: int = 0
    unchanged: int = 0
    skipped_excluded: int = 0
    errors: list[str] = field(default_factory=list)


class RunalyzeVo2maxImporter:
    """Write Runalyze's effective VO2max into the canonical activity row."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.writer = TrainingWriter(connection)

    def import_vo2max(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> RunalyzeVo2maxSummary:
        summary = RunalyzeVo2maxSummary(dry_run=dry_run)

        if not dry_run:
            summary.run_id = self.writer.start_import_run(
                SOURCE,
                {
                    "vo2max": True,
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                    "limit": limit,
                },
            )

        try:
            rows = self._rows(start, end, limit)
            for row in rows:
                summary.payloads += 1
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except ValueError:
                    summary.errors.append(
                        f"source record {row['source_record_id']}: "
                        "invalid JSON"
                    )
                    continue
                if not isinstance(payload, dict):
                    continue

                value = _float(payload.get("vo2max"))
                if value is None:
                    continue
                summary.with_value += 1

                if row["excluded_at"]:
                    summary.skipped_excluded += 1
                    continue
                if _same(row["vo2max_runalyze"], value):
                    summary.unchanged += 1
                    continue

                summary.written += 1
                if dry_run:
                    continue

                self.writer.upsert_activity(
                    row["activity_id"],
                    {"vo2max_runalyze": value},
                    source=SOURCE,
                    source_record_id=row["source_record_id"],
                )

            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "success",
                    records_seen=summary.payloads,
                    records_imported=summary.written,
                    records_skipped=summary.unchanged
                    + summary.skipped_excluded,
                )
            return summary

        except Exception as exc:
            self.connection.rollback()
            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "failed",
                    records_seen=summary.payloads,
                    records_imported=summary.written,
                    records_skipped=summary.unchanged,
                    error=str(exc),
                )
            raise

    def _rows(
        self,
        start: date | None,
        end: date | None,
        limit: int | None,
    ) -> list[sqlite3.Row]:
        sql = """
            SELECT sr.id AS source_record_id, sr.payload_json,
                   als.activity_id, a.excluded_at, a.vo2max_runalyze
            FROM source_records sr
            JOIN activity_sources als ON als.source_record_id = sr.id
            JOIN activities a ON a.id = als.activity_id
            WHERE sr.source = ? AND sr.record_type = 'activity'
        """
        params: list[object] = [SOURCE]
        if start is not None:
            sql += " AND a.local_date >= ?"
            params.append(start.isoformat())
        if end is not None:
            sql += " AND a.local_date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY a.local_date, als.activity_id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return self.connection.execute(sql, params).fetchall()


def format_vo2max_summary(summary: RunalyzeVo2maxSummary) -> str:
    label = (
        "Runalyze VO2max dry run" if summary.dry_run else "Runalyze VO2max"
    )
    lines = [
        f"{label}: {summary.payloads} payloads, "
        f"{summary.with_value} with a value",
        f"  written: {summary.written}",
        f"  unchanged: {summary.unchanged}",
        f"  skipped excluded: {summary.skipped_excluded}",
    ]
    for error in summary.errors:
        lines.append(f"  error: {error}")
    if not summary.dry_run:
        lines.append(f"Import run: {summary.run_id}")
    return "\n".join(lines)


def _float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _same(current: object, value: float) -> bool:
    return (
        isinstance(current, (int, float))
        and abs(float(current) - value) < 0.005
    )
