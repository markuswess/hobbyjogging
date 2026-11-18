"""Import Runalyze's official race results (phase 4).

Runalyze keeps one row per activity it marks as a race: official distance and
time, placement, participant counts, priority and status. The row carries
Runalyze's activity id, which is the stored payload's ``external_id``, so the
import only writes where a canonical activity is already linked; it never
guesses a match and never overwrites a manual ``race-result`` row.

``official_ascent``/``official_descent`` have no column in ``race_results`` and
are not imported; ``race_event_id`` is Runalyze's own event identity and does
not map to our Intervals-authoritative ``events``, so ``event_id`` stays empty.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from hobbyjogging_core import TrainingWriter

from .runalyze import RunalyzeApi

SOURCE = "runalyze"
RACE_RESULT_RECORD_TYPE = "race_result"
RACE_RESULT_COLLECTION = "raceresult"
PER_PAGE = 500

PLACE_FIELDS = (
    "place_total",
    "place_gender",
    "place_ageclass",
    "participants_total",
    "participants_gender",
    "participants_ageclass",
)


@dataclass
class RunalyzeRaceSummary:
    run_id: int | None = None
    dry_run: bool = False
    race_results: int = 0
    written: int = 0
    unchanged: int = 0
    kept_manual: int = 0
    unmatched: int = 0
    unmatched_rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class RunalyzeRaceImporter:
    """Write Runalyze race results onto the linked canonical activities."""

    def __init__(self, connection: sqlite3.Connection, client: RunalyzeApi):
        self.connection = connection
        self.client = client
        self.writer = TrainingWriter(connection)

    def import_races(
        self,
        *,
        limit: int | None = None,
        dry_run: bool = False,
        output: str | Path | None = None,
    ) -> RunalyzeRaceSummary:
        summary = RunalyzeRaceSummary(dry_run=dry_run)

        if not dry_run:
            summary.run_id = self.writer.start_import_run(
                SOURCE,
                {"race_results": True, "limit": limit},
            )

        try:
            rows = fetch_race_results(self.client)
            if limit is not None:
                rows = rows[:limit]
            summary.race_results = len(rows)

            links = self._activity_links()

            for row in rows:
                if not isinstance(row, dict):
                    continue
                runalyze_id = row.get("activity_id")
                link = links.get(str(runalyze_id))
                if link is None:
                    summary.unmatched += 1
                    summary.unmatched_rows.append(
                        {
                            "date": row.get("date"),
                            "name": row.get("name"),
                            "runalyze_activity_id": runalyze_id,
                            "reason": "no_linked_activity",
                        }
                    )
                    continue

                activity_id, source_record_id = link
                fields = _race_fields(row)
                if not fields:
                    continue

                if _unchanged(self.connection, activity_id, fields):
                    summary.unchanged += 1
                    continue

                summary.written += 1
                if dry_run:
                    continue

                write_id = self.writer.upsert_source_record(
                    source=SOURCE,
                    record_type=RACE_RESULT_RECORD_TYPE,
                    external_id=_external_id(runalyze_id),
                    checksum=_checksum(row),
                    payload_json=_payload_json(row),
                    import_run_id=summary.run_id,
                )
                written = self.writer.upsert_race_result(
                    activity_id,
                    source=SOURCE,
                    source_record_id=write_id,
                    **fields,
                )
                if not written:
                    summary.written -= 1
                    summary.kept_manual += 1

            if output is not None:
                _write_unmatched(Path(output), summary.unmatched_rows)

            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "success",
                    records_seen=summary.race_results,
                    records_imported=summary.written,
                    records_skipped=summary.unchanged + summary.unmatched,
                )
            return summary

        except Exception as exc:
            self.connection.rollback()
            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "failed",
                    records_seen=summary.race_results,
                    records_imported=summary.written,
                    records_skipped=summary.unchanged,
                    error=str(exc),
                )
            raise

    def _activity_links(self) -> dict[str, tuple[str, int]]:
        """Map a Runalyze activity id to (canonical id, source record id)."""
        return {
            str(row["external_id"]): (
                row["activity_id"],
                row["source_record_id"],
            )
            for row in self.connection.execute(
                """
                SELECT sr.external_id, sr.id AS source_record_id,
                       als.activity_id
                FROM source_records sr
                JOIN activity_sources als
                    ON als.source_record_id = sr.id
                WHERE sr.source = ? AND sr.record_type = 'activity'
                """,
                (SOURCE,),
            )
        }


def fetch_race_results(client: RunalyzeApi) -> list[dict]:
    """Read every race-result page."""
    items: list[dict] = []
    page = 1

    while True:
        response = client.get(
            RACE_RESULT_COLLECTION,
            {"page": page, "itemsPerPage": PER_PAGE},
        )
        if not response.ok:
            raise RuntimeError(
                "Runalyze race-result collection failed "
                f"(HTTP {response.status})"
            )

        batch = response.payload
        if not isinstance(batch, list) or not batch:
            break

        rows = [row for row in batch if isinstance(row, dict)]
        items.extend(rows)
        if len(batch) < PER_PAGE:
            break
        page += 1

    return items


def format_race_summary(summary: RunalyzeRaceSummary) -> str:
    label = (
        "Runalyze races dry run" if summary.dry_run else "Runalyze races"
    )
    lines = [
        f"{label}: {summary.race_results} race results",
        f"  written: {summary.written}",
        f"  unchanged: {summary.unchanged}",
        f"  kept manual: {summary.kept_manual}",
        f"  unmatched: {summary.unmatched}",
    ]
    for error in summary.errors:
        lines.append(f"  error: {error}")
    if not summary.dry_run:
        lines.append(f"Import run: {summary.run_id}")
    return "\n".join(lines)


def _race_fields(row: dict) -> dict[str, object]:
    fields: dict[str, object] = {}

    name = str(row.get("name") or "").strip()
    if name:
        fields["name"] = name

    distance = _number(row.get("official_distance"))
    if distance is not None and distance > 0:
        fields["official_distance_m"] = distance * 1000.0

    time_s = _number(row.get("official_time"))
    if time_s is not None and time_s > 0:
        fields["official_time_s"] = time_s

    measured = row.get("officially_measured")
    if isinstance(measured, bool):
        fields["officially_measured"] = int(measured)

    for key in PLACE_FIELDS:
        value = _integer(row.get(key))
        if value is not None:
            fields[key] = value

    priority = str(row.get("priority_level") or "").strip()
    if priority:
        fields["priority_level"] = priority

    fields["status"] = str(row.get("status") or "").strip() or "completed"
    return fields


def _unchanged(
    connection: sqlite3.Connection,
    activity_id: str,
    fields: dict[str, object],
) -> bool:
    current = connection.execute(
        "SELECT * FROM race_results WHERE activity_id = ?",
        (activity_id,),
    ).fetchone()
    if current is None or current["excluded_at"]:
        return False
    if current["source"] != SOURCE:
        return False

    for key, value in fields.items():
        stored = current[key]
        if isinstance(value, int) and isinstance(stored, int):
            if value != stored:
                return False
        elif stored != value:
            return False
    return True


def _write_unmatched(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"unmatched": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _external_id(runalyze_activity_id: object) -> str:
    return f"runalyze:{runalyze_activity_id}"


def _payload_json(row: dict) -> str:
    return json.dumps(
        row,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _checksum(row: dict) -> str:
    return hashlib.sha256(
        _payload_json(row).encode("utf-8")
    ).hexdigest()


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
