"""Import a Strava bulk export: social text and gear, never training data."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from hobbyjogging_core import TrainingWriter

from .matching import MatchPolicy, decide_match
from .strava import (
    StravaActivity,
    StravaGear,
    gear_key,
    gear_ref_key,
    gear_slug,
    payload_json,
    read_export,
)

SOURCE = "strava"


@dataclass
class StravaSummary:
    run_id: int | None = None
    dry_run: bool = False
    activities_seen: int = 0
    social_written: int = 0
    social_created: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    no_date: int = 0
    gear_seen: int = 0
    gear_created: int = 0
    gear_linked: int = 0
    gear_ambiguous: int = 0
    activities_linked_to_gear: int = 0


class StravaCsvImporter:
    """Match a Strava manifest to canonical activities and write social rows."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.writer = TrainingWriter(connection)

    def import_export(
        self,
        path: str | Path,
        *,
        dry_run: bool = False,
        distance_unit: str = "km",
        start: date | None = None,
        end: date | None = None,
    ) -> StravaSummary:
        export = read_export(path, distance_unit=distance_unit)
        summary = StravaSummary(dry_run=dry_run)

        if not dry_run:
            summary.run_id = self.writer.start_import_run(
                SOURCE,
                {
                    "path": str(path),
                    "distance_unit": distance_unit,
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                },
            )

        try:
            equipment = self._import_gear(export.gear, summary)
            for activity in export.activities:
                if not _in_range(activity, start, end):
                    continue
                summary.activities_seen += 1
                self._import_activity(activity, equipment, summary)
        except Exception as exc:
            self.connection.rollback()
            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "error",
                    records_seen=summary.activities_seen,
                    records_imported=summary.social_written,
                    error=str(exc),
                )
            raise

        if summary.run_id is not None:
            self.writer.finish_import_run(
                summary.run_id,
                "success",
                records_seen=summary.activities_seen,
                records_imported=summary.social_written,
                records_skipped=summary.unmatched + summary.ambiguous,
            )
        return summary

    def _import_gear(
        self,
        gear: list[StravaGear],
        summary: StravaSummary,
    ) -> dict[str, str]:
        """Resolve gear names to equipment ids, creating only unknown rows."""
        index = self._equipment_index()
        existing_ids = set(self._equipment_ids())
        resolved: dict[str, str] = {
            key: ids[0]
            for key, ids in index.items()
            if len(ids) == 1
        }

        for item in gear:
            summary.gear_seen += 1
            matches = index.get(item.external_id, [])

            if len(matches) > 1:
                summary.gear_ambiguous += 1
                continue

            if matches:
                equipment_id = matches[0]
                source_record_id = self._gear_source_record(item, summary)
                if source_record_id is not None:
                    self.writer.link_equipment_source(
                        equipment_id,
                        source_record_id,
                    )
                summary.gear_linked += 1
                resolved[item.external_id] = equipment_id
                continue

            equipment_id = f"strava:gear:{gear_slug(item.name)}"
            source_record_id = self._gear_source_record(item, summary)
            if equipment_id in existing_ids:
                if source_record_id is not None:
                    self.writer.link_equipment_source(
                        equipment_id,
                        source_record_id,
                    )
                summary.gear_linked += 1
            else:
                if not summary.dry_run:
                    self.writer.upsert_equipment(
                        equipment_id,
                        type=item.type,
                        name=item.name,
                        brand=item.brand,
                        model=item.model,
                        source_record_id=source_record_id,
                    )
                summary.gear_created += 1
            resolved[item.external_id] = equipment_id

        return resolved

    def _gear_source_record(
        self,
        item: StravaGear,
        summary: StravaSummary,
    ) -> int | None:
        if summary.dry_run:
            return None
        payload = json.dumps(
            {
                "external_id": item.external_id,
                "type": item.type,
                "name": item.name,
                "brand": item.brand,
                "model": item.model,
            },
            sort_keys=True,
        )
        return self.writer.upsert_source_record(
            source=SOURCE,
            record_type="gear",
            external_id=item.external_id,
            checksum=_checksum(payload),
            payload_json=payload,
            import_run_id=summary.run_id,
        )

    def _import_activity(
        self,
        activity: StravaActivity,
        equipment: dict[str, str],
        summary: StravaSummary,
    ) -> None:
        if activity.started_at_local is None:
            summary.no_date += 1
            return

        decision = decide_match(
            self.connection,
            source=SOURCE,
            started_at_local=activity.started_at_local,
            elapsed_s=activity.elapsed_s,
            duration_s=activity.elapsed_s,
            distance_m=activity.distance_m,
            local_date=activity.local_date,
            policy=MatchPolicy(),
            allow_create=False,
        )

        if decision.activity_id is None:
            if decision.reason == "ambiguous_match":
                summary.ambiguous += 1
            else:
                summary.unmatched += 1
            return

        source_record_id = self._social_source_record(activity, summary)
        if not summary.dry_run:
            created = self.writer.upsert_activity_social(
                decision.activity_id,
                source=SOURCE,
                source_record_id=source_record_id,
                title=activity.name,
                description=activity.description,
                external_id=activity.external_id,
                url=activity.url,
            )
            summary.social_created += int(created)
        summary.social_written += 1

        equipment_id = self._resolve_gear(activity.gear, equipment)
        if equipment_id is None:
            return

        if not summary.dry_run:
            linked = self.writer.link_activity_equipment(
                decision.activity_id,
                equipment_id,
                source=SOURCE,
                source_record_id=source_record_id,
                role="primary",
            )
            summary.activities_linked_to_gear += int(linked)
        else:
            summary.activities_linked_to_gear += 1

    def _social_source_record(
        self,
        activity: StravaActivity,
        summary: StravaSummary,
    ) -> int | None:
        if summary.dry_run:
            return None
        payload = payload_json(activity)
        return self.writer.upsert_source_record(
            source=SOURCE,
            record_type="social",
            external_id=activity.external_id,
            checksum=_checksum(payload),
            payload_json=payload,
            import_run_id=summary.run_id,
        )

    def _equipment_index(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for row in self.connection.execute(
            "SELECT id, name FROM equipment ORDER BY id"
        ):
            index.setdefault(gear_key(row["name"]), []).append(row["id"])
        return index

    def _equipment_ids(self) -> list[str]:
        return [
            row["id"]
            for row in self.connection.execute("SELECT id FROM equipment")
        ]

    def _resolve_gear(
        self,
        reference: str,
        equipment: dict[str, str],
    ) -> str | None:
        key = gear_ref_key(reference)
        if not key:
            return None
        return equipment.get(key)


def format_strava_summary(summary: StravaSummary, path: str) -> str:
    mode = "dry run" if summary.dry_run else "applied"
    lines = [
        f"Strava export: {path} ({mode})",
        f"  activities: {summary.activities_seen} seen, "
        f"{summary.social_written} social rows "
        f"({summary.social_created} created), "
        f"{summary.unmatched} unmatched, "
        f"{summary.ambiguous} ambiguous, "
        f"{summary.no_date} without a date",
        f"  gear: {summary.gear_seen} seen, "
        f"{summary.gear_created} created, "
        f"{summary.gear_linked} linked, "
        f"{summary.gear_ambiguous} ambiguous; "
        f"{summary.activities_linked_to_gear} activity links",
    ]
    if summary.run_id is not None:
        lines.append(f"  import run: {summary.run_id}")
    return "\n".join(lines)


def _in_range(
    activity: StravaActivity,
    start: date | None,
    end: date | None,
) -> bool:
    local_date = activity.local_date
    if local_date is None:
        return start is None and end is None
    day = date.fromisoformat(local_date)
    if start is not None and day < start:
        return False
    if end is not None and day > end:
        return False
    return True


def _checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
