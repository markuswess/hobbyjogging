"""Import the historical training log from an ODS workbook.

The spreadsheet is a legacy, hand-maintained log. It writes canonical
activities and equipment through the same writer as the other sources, so
owner-based precedence, manual values, and review items behave uniformly.

Source layout:

- ``Rohdaten`` - historical runs.
- ``Alternativtraining`` - cross-training sessions.
- ``Material`` - shoes/gear, plus the shoe ids referenced by ``Rohdaten``.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from hobbyjogging_core import TrainingWriter
from hobbyjogging_core.db.writer import CONFLICT_FIELDS

from .matching import ActivityMatcher, MatchCandidate, linked_activity
from .ods import Sheet, read_sheet
from .quality import (
    record_ambiguous_match,
    record_field_conflicts,
    record_quality_findings,
    resolve_agreed_field_conflicts,
)
from .sheet import (
    ALTERNATIVTRAINING,
    DEFAULT_TIMEZONE,
    MATERIAL,
    ROHDATEN,
    SOURCE,
    SUPPORTED_SHEETS,
    alternativtraining_values,
    as_clock,
    as_date,
    clean_text,
    equipment_id,
    equipment_values,
    rohdaten_values,
    row_payload,
    row_record,
)

REQUIRED_HEADERS = {
    ROHDATEN: ("Datum", "Distanz in m"),
    ALTERNATIVTRAINING: ("Datum", "Was"),
    MATERIAL: ("Id", "Marke"),
}

MATERIAL_BLANK_HEADERS = {4: "Farbe"}


@dataclass
class SheetImportSummary:
    """Results of importing one worksheet."""

    run_id: int | None = None
    sheet: str = ""
    dry_run: bool = False
    rows_seen: int = 0
    rows_skipped: int = 0
    rows_filtered: int = 0
    rows_limited: int = 0
    activities_imported: int = 0
    activities_created: int = 0
    activities_matched: int = 0
    equipment_created: int = 0
    equipment_updated: int = 0
    equipment_linked: int = 0
    equipment_missing: int = 0
    tags_written: int = 0
    review_recorded: int = 0
    ambiguous_matches: list[tuple[str, list[MatchCandidate]]] = field(
        default_factory=list
    )


class SheetImporter:
    """Import activities and equipment from the historical ODS log."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        timezone_name: str = DEFAULT_TIMEZONE,
    ):
        self.connection = connection
        self.writer = TrainingWriter(connection)
        self.matcher = ActivityMatcher(connection)
        self.timezone_name = timezone_name

    def import_sheet(
        self,
        path: str | Path,
        sheet_name: str,
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> SheetImportSummary:
        """Import one worksheet, optionally limited to a date range."""
        if sheet_name not in SUPPORTED_SHEETS:
            supported = ", ".join(SUPPORTED_SHEETS)
            raise ValueError(
                f"unsupported sheet {sheet_name!r} (choose from {supported})"
            )
        if start is not None and end is not None and start > end:
            raise ValueError("start must not be after end")
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than zero")

        sheet = read_sheet(path, sheet_name)
        summary = SheetImportSummary(sheet=sheet_name, dry_run=dry_run)

        header_index = sheet.header_index(REQUIRED_HEADERS[sheet_name])
        headers = sheet.rows[header_index]
        data_rows = sheet.rows[header_index + 1 :]

        if not dry_run:
            summary.run_id = self.writer.start_import_run(
                SOURCE,
                {
                    "sheet": sheet_name,
                    "path": str(path),
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                },
            )

        try:
            with self.connection:
                if sheet_name == MATERIAL:
                    self._import_material(
                        headers,
                        data_rows,
                        summary,
                        header_index=header_index,
                    )
                else:
                    self._import_activities(
                        sheet,
                        headers,
                        data_rows,
                        summary,
                        header_index=header_index,
                        start=start,
                        end=end,
                        limit=limit,
                    )

            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "success",
                    records_seen=summary.rows_seen,
                    records_imported=(
                        summary.activities_imported
                        + summary.equipment_created
                        + summary.equipment_updated
                    ),
                    records_skipped=summary.rows_skipped,
                )
            return summary

        except Exception as exc:
            self.connection.rollback()
            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "failed",
                    records_seen=summary.rows_seen,
                    records_imported=(
                        summary.activities_imported
                        + summary.equipment_created
                        + summary.equipment_updated
                    ),
                    records_skipped=summary.rows_skipped,
                    error=str(exc),
                )
            raise

    def _import_material(
        self,
        headers: list[object],
        rows: list[list[object]],
        summary: SheetImportSummary,
        *,
        header_index: int,
    ) -> None:
        for offset, row in enumerate(rows):
            record = row_record(
                headers,
                row,
                blank_names=MATERIAL_BLANK_HEADERS,
            )
            if "Id" not in record:
                continue

            summary.rows_seen += 1
            try:
                equipment = equipment_values(record)
            except ValueError:
                summary.rows_skipped += 1
                continue

            payload = row_payload(
                MATERIAL,
                header_index + offset + 2,
                record,
            )
            if summary.dry_run:
                exists = self.connection.execute(
                    "SELECT 1 FROM equipment WHERE id = ?",
                    (equipment.equipment_id,),
                ).fetchone()
                if exists is None:
                    summary.equipment_created += 1
                else:
                    summary.equipment_updated += 1
                continue

            source_record_id = self._activity_source_record(
                record_type="equipment",
                external_id=equipment.equipment_id,
                payload=payload,
                summary=summary,
            )
            created = self.writer.upsert_equipment(
                equipment.equipment_id,
                type=equipment.type,
                name=equipment.name,
                brand=equipment.brand,
                model=equipment.model,
                acquired_on=equipment.acquired_on,
                retired_on=equipment.retired_on,
                notes=equipment.notes,
                source_record_id=source_record_id,
            )
            if created:
                summary.equipment_created += 1
            else:
                summary.equipment_updated += 1

    def _import_activities(
        self,
        sheet: Sheet,
        headers: list[object],
        rows: list[list[object]],
        summary: SheetImportSummary,
        *,
        header_index: int,
        start: date | None,
        end: date | None,
        limit: int | None,
    ) -> None:
        candidates: list[tuple[int, dict[str, object], date]] = []

        for offset, row in enumerate(rows):
            record = row_record(headers, row)
            if not record:
                continue

            summary.rows_seen += 1
            day = as_date(record.get("Datum"))
            if day is None:
                summary.rows_skipped += 1
                continue
            if (start is not None and day < start) or (
                end is not None and day > end
            ):
                summary.rows_filtered += 1
                continue
            if limit is not None and len(candidates) >= limit:
                summary.rows_limited += 1
                continue
            candidates.append(
                (header_index + offset + 2, record, day)
            )

        occurrences: dict[str, int] = {}
        keys = [
            self._external_key(record, day)
            for _, record, day in candidates
        ]
        for key in keys:
            occurrences[key] = occurrences.get(key, 0) + 1

        for (row_number, record, day), key in zip(candidates, keys):
            payload = row_payload(sheet.name, row_number, record)
            external_id = key
            if occurrences[key] > 1:
                digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                external_id = f"{key}|{digest[:12]}"

            if self.writer.is_source_record_excluded(
                source=SOURCE,
                record_type="activity",
                external_id=external_id,
            ):
                summary.rows_skipped += 1
                continue

            source_record_id = None
            existing_link = None
            if summary.dry_run:
                source_record_id = self._source_record_id(
                    "activity",
                    external_id,
                )
                if source_record_id is not None:
                    existing_link = linked_activity(
                        self.connection,
                        source_record_id,
                    )
            else:
                source_record_id = self._activity_source_record(
                    record_type="activity",
                    external_id=external_id,
                    payload=payload,
                    summary=summary,
                )
                existing_link = linked_activity(
                    self.connection,
                    source_record_id,
                )

            try:
                if sheet.name == ROHDATEN:
                    values, tags, shoe = rohdaten_values(
                        record,
                        timezone_name=self.timezone_name,
                    )
                else:
                    values = alternativtraining_values(
                        record,
                        timezone_name=self.timezone_name,
                    )
                    tags, shoe = [], None
            except ValueError:
                summary.rows_skipped += 1
                continue

            activity_id, match_method, confidence, created = (
                self._resolve_activity(
                    external_id,
                    values,
                    existing_link,
                    summary,
                    source_record_id=source_record_id,
                )
            )
            if activity_id is None:
                summary.rows_skipped += 1
                continue

            if created:
                summary.activities_created += 1
            else:
                summary.activities_matched += 1
            summary.activities_imported += 1

            values = self._precise_start_preserved(
                activity_id,
                values,
                match_method,
            )

            if summary.dry_run:
                continue

            if source_record_id is None:
                raise RuntimeError("sheet source record was not created")

            conflicts = self.writer.upsert_activity(
                activity_id,
                values,
                source=SOURCE,
                source_record_id=source_record_id,
            )
            summary.review_recorded += record_field_conflicts(
                self.writer,
                activity_id=activity_id,
                source_record_id=source_record_id,
                import_run_id=summary.run_id,
                conflicts=conflicts,
            )
            resolve_agreed_field_conflicts(
                self.writer,
                activity_id=activity_id,
                fields=(
                    (set(values) & CONFLICT_FIELDS)
                    - {conflict.field_name for conflict in conflicts}
                ),
            )
            self.writer.link_activity_source(
                activity_id,
                source_record_id,
                match_method=match_method,
                confidence=confidence,
            )
            if tags:
                summary.tags_written += self.writer.replace_activity_tags(
                    activity_id,
                    tags,
                    source=SOURCE,
                    source_record_id=source_record_id,
                )
            summary.review_recorded += record_quality_findings(
                self.writer,
                activity_id=activity_id,
                source_record_id=source_record_id,
                import_run_id=summary.run_id,
                sport=str(values.get("sport") or ""),
                duration_s=float(values.get("duration_s") or 0),
                elapsed_s=float(values.get("duration_s") or 0),
                distance_m=float(values.get("distance_m") or 0),
            )
            if shoe is not None:
                equipment = self._resolve_equipment(shoe)
                if equipment is None:
                    summary.equipment_missing += 1
                elif self.writer.link_activity_equipment(
                    activity_id,
                    equipment,
                    source=SOURCE,
                    source_record_id=source_record_id,
                ):
                    summary.equipment_linked += 1

    def _resolve_activity(
        self,
        external_id: str,
        values: dict[str, object],
        existing_link,
        summary: SheetImportSummary,
        *,
        source_record_id: int | None,
    ) -> tuple[str | None, str, float | None, bool]:
        if existing_link is not None:
            activity_id = existing_link["activity_id"]
            if self.writer.is_activity_excluded(activity_id):
                return None, "", None, False
            return (
                activity_id,
                existing_link["match_method"] or "external_id",
                existing_link["confidence"],
                False,
            )

        started_at = str(values.get("started_at_utc") or "")
        duration_s = float(values.get("duration_s") or 0)
        if started_at and duration_s > 0:
            matches = self.matcher.find(
                started_at_utc=started_at,
                source=SOURCE,
                elapsed_s=duration_s,
                duration_s=duration_s,
            )
            if len(matches) > 1:
                summary.ambiguous_matches.append((external_id, matches))
                if not summary.dry_run and source_record_id is not None:
                    summary.review_recorded += record_ambiguous_match(
                        self.writer,
                        source_record_id=source_record_id,
                        external_id=external_id,
                        candidates=matches,
                        import_run_id=summary.run_id,
                    )
                return None, "", None, False
            if matches:
                match = matches[0]
                return (
                    match.activity_id,
                    match.match_method,
                    match.confidence,
                    False,
                )

        return _stable_activity_id(external_id), "created", None, True

    def _activity_source_record(
        self,
        *,
        record_type: str,
        external_id: str,
        payload: str,
        summary: SheetImportSummary,
    ) -> int:
        return self.writer.upsert_source_record(
            source=SOURCE,
            record_type=record_type,
            external_id=external_id,
            checksum=_checksum(payload),
            payload_json=payload,
            import_run_id=summary.run_id,
        )

    def _source_record_id(
        self,
        record_type: str,
        external_id: str,
    ) -> int | None:
        row = self.connection.execute(
            """
            SELECT id FROM source_records
            WHERE source = ? AND record_type = ? AND external_id = ?
            """,
            (SOURCE, record_type, external_id),
        ).fetchone()
        return row["id"] if row is not None else None

    def _precise_start_preserved(
        self,
        activity_id: str,
        values: dict[str, object],
        match_method: str,
    ) -> dict[str, object]:
        """Keep an existing precise start time when the sheet only has minutes.

        The log records a wall-clock time rounded to the minute, while FIT and
        Intervals store seconds. Matching still uses the synthesized start, but
        a matched activity keeps its precise owner instead of opening a timing
        review item on every row.
        """
        if match_method == "created":
            return values

        row = self.connection.execute(
            "SELECT started_at_utc FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        if row is None or not row["started_at_utc"]:
            return values

        return {
            key: value
            for key, value in values.items()
            if key not in ("started_at_utc", "tz_offset_min")
        }

    def _resolve_equipment(self, value: object) -> str | None:
        candidate = equipment_id(value)
        if candidate is not None:
            row = self.connection.execute(
                "SELECT id FROM equipment WHERE id = ?",
                (candidate,),
            ).fetchone()
            if row is not None:
                return row["id"]

        name = clean_text(value)
        if not name:
            return None
        row = self.connection.execute(
            """
            SELECT id FROM equipment
            WHERE lower(name) = lower(?)
            ORDER BY id
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        return row["id"] if row is not None else None

    def _external_key(
        self,
        record: dict[str, object],
        day: date,
    ) -> str:
        clock = as_clock(record.get("Startzeit"))
        if clock is None:
            clock = as_clock(record.get("Uhrzeit"))
        when = f"{day.isoformat()}T{clock.isoformat()}" if clock else (
            day.isoformat()
        )
        route = clean_text(record.get("Strecke"))
        return f"{when}|{route}" if route else when


def format_sheet_summary(
    summary: SheetImportSummary,
    database_path,
) -> str:
    """Format an import summary for the CLI."""
    verb = "would import" if summary.dry_run else "imported"
    label = "Sheet dry run" if summary.dry_run else "Sheet import complete"
    lines = [
        f"{label}: "
        f"{summary.sheet}, {summary.rows_seen} rows seen, "
        f"{summary.activities_imported} activities {verb} "
        f"({summary.activities_matched} matched, "
        f"{summary.activities_created} created)"
    ]
    if summary.sheet == MATERIAL:
        lines[0] = (
            f"{label}: "
            f"{summary.sheet}, {summary.rows_seen} rows seen, "
            f"{summary.equipment_created} equipment created, "
            f"{summary.equipment_updated} updated"
        )

    if summary.tags_written:
        lines.append(f"Tags written: {summary.tags_written}")
    if summary.equipment_linked:
        lines.append(f"Shoe links: {summary.equipment_linked}")
    if summary.equipment_missing:
        lines.append(
            f"Shoe links skipped (unknown id): {summary.equipment_missing}"
        )
    if summary.rows_filtered:
        lines.append(f"Rows outside the date range: {summary.rows_filtered}")
    if summary.rows_limited:
        lines.append(f"Rows over the limit: {summary.rows_limited}")
    if summary.rows_skipped:
        lines.append(f"Rows skipped: {summary.rows_skipped}")
    if summary.review_recorded:
        lines.append(f"Review items recorded: {summary.review_recorded}")

    for external_id, matches in summary.ambiguous_matches:
        candidates = ", ".join(
            f"{match.activity_id} ({match.match_method}, "
            f"{match.confidence:.3f})"
            for match in matches
        )
        lines.append(f"Ambiguous match: {external_id} -> {candidates}")

    if not summary.dry_run:
        lines.append(f"Import run: {summary.run_id}")
    lines.append(f"Database: {database_path}")
    return "\n".join(lines)


def _stable_activity_id(external_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"hobbyjogging:sheet:activity:{external_id}",
        )
    )


def _checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
