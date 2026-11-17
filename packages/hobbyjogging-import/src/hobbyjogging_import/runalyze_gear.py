"""Resolve Runalyze gear records from stored activity payloads.

Phase 3 is offline: every Runalyze detail already sits in ``source_records``,
so gear needs no activity-detail request. A gear record is resolved in this
order (root item 12):

1. co-occurrence with the sheet shoes on its matched activities
   (at least 3 activities, one item on at least 80% of them);
2. exact normalized name against existing equipment names / brand+model;
3. a new ``runalyze:equipment:<id>`` row.

Ambiguity (a split co-occurrence or several name matches) opens a non-hiding
``ambiguous_equipment`` review item; the gear is never guessed. Resolved gear
is linked to its activities: the first shoe/bike item is primary, the rest
secondary, manual and sheet links win.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from hobbyjogging_core import TrainingWriter

from .quality import AMBIGUOUS_EQUIPMENT, review_fingerprint

SOURCE = "runalyze"
GEAR_RECORD_TYPE = "gear"
GEAR_EXTERNAL_PREFIX = "runalyze:"
GEAR_EQUIPMENT_PREFIX = "runalyze:equipment:"

CATEGORY_TYPES = {
    78697: "shoe",
    78699: "bike",
}
OTHER_CATEGORY_TYPE = "other"
PRIMARY_TYPES = frozenset({"shoe", "bike"})

CO_OCCURRENCE_MIN_ACTIVITIES = 3
CO_OCCURRENCE_SHARE = 0.80


@dataclass
class GearItem:
    gear_id: int
    name: str = ""
    category_id: int | None = None
    notes: str = ""
    acquired_on: str | None = None
    retired_on: str | None = None
    activities: set[str] = field(default_factory=set)
    payload: dict = field(default_factory=dict)

    @property
    def type(self) -> str:
        return CATEGORY_TYPES.get(self.category_id, OTHER_CATEGORY_TYPE)


@dataclass
class RunalyzeGearSummary:
    run_id: int | None = None
    dry_run: bool = False
    payloads: int = 0
    gear_items: int = 0
    created: int = 0
    linked_existing: int = 0
    already_linked: int = 0
    ambiguous: int = 0
    ambiguous_resolved: int = 0
    reviews_recorded: int = 0
    activity_links: int = 0
    primary_links: int = 0
    secondary_links: int = 0
    skipped_links: int = 0
    ambiguous_rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class RunalyzeGearImporter:
    """Resolve stored Runalyze gear into equipment and activity links."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.writer = TrainingWriter(connection)

    def import_gear(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        dry_run: bool = False,
        output: str | Path | None = None,
    ) -> RunalyzeGearSummary:
        summary = RunalyzeGearSummary(dry_run=dry_run)

        if not dry_run:
            summary.run_id = self.writer.start_import_run(
                SOURCE,
                {
                    "gear": True,
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                    "limit": limit,
                },
            )

        try:
            payloads, gear, activity_order = self._load(
                start,
                end,
                summary,
            )
            summary.payloads = payloads
            summary.gear_items = len(gear)

            gear_ids = sorted(gear)
            if limit is not None:
                gear_ids = gear_ids[:limit]

            context = self._contexts()
            primary = _primary_by_activity(gear, activity_order)

            for gear_id in gear_ids:
                self._resolve_one(
                    gear[gear_id],
                    context,
                    primary,
                    summary,
                    dry_run=dry_run,
                )

            if output is not None:
                _write_ambiguous(Path(output), summary.ambiguous_rows)

            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "success",
                    records_seen=summary.payloads,
                    records_imported=summary.gear_items,
                    records_skipped=summary.ambiguous,
                )
            return summary

        except Exception as exc:
            self.connection.rollback()
            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "failed",
                    records_seen=summary.payloads,
                    records_imported=summary.gear_items,
                    records_skipped=summary.ambiguous,
                    error=str(exc),
                )
            raise

    # -- loading ------------------------------------------------------------

    def _load(
        self,
        start: date | None,
        end: date | None,
        summary: RunalyzeGearSummary,
    ) -> tuple[int, dict[int, GearItem], dict[str, list[int]]]:
        sql = """
            SELECT sr.id AS source_record_id, sr.payload_json, als.activity_id
            FROM source_records sr
            JOIN activity_sources als
                ON als.source_record_id = sr.id
            JOIN activities a ON a.id = als.activity_id
            WHERE sr.source = ? AND sr.record_type = 'activity'
              AND a.excluded_at IS NULL
        """
        params: list[object] = [SOURCE]
        if start is not None:
            sql += " AND a.local_date >= ?"
            params.append(start.isoformat())
        if end is not None:
            sql += " AND a.local_date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY a.local_date, als.activity_id"

        rows = self.connection.execute(sql, params).fetchall()

        gear: dict[int, GearItem] = {}
        activity_order: dict[str, list[int]] = {}
        source_records: set[int] = set()

        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except ValueError:
                summary.errors.append(
                    f"activity source {row['source_record_id']}: invalid JSON"
                )
                continue
            if not isinstance(payload, dict):
                continue

            items = payload.get("equipment") or []
            if not isinstance(items, list):
                continue

            activity_id = row["activity_id"]
            source_records.add(row["source_record_id"])

            for item in items:
                if not isinstance(item, dict):
                    continue
                gear_id = _gear_id(item.get("id"))
                if gear_id is None:
                    continue

                entry = gear.get(gear_id)
                if entry is None:
                    entry = GearItem(gear_id=gear_id)
                    gear[gear_id] = entry
                entry.name = str(item.get("name") or entry.name)
                entry.category_id = (
                    item.get("category_id") or entry.category_id
                )
                entry.notes = str(item.get("notes") or entry.notes)
                entry.acquired_on = (
                    item.get("date_start") or entry.acquired_on
                )
                entry.retired_on = (
                    item.get("date_end") or entry.retired_on
                )
                entry.payload = item

                if activity_id is not None:
                    entry.activities.add(activity_id)
                    order = activity_order.setdefault(activity_id, [])
                    if gear_id not in order:
                        order.append(gear_id)

        return len(source_records), gear, activity_order

    def _contexts(self) -> dict[str, object]:
        equipment = {}
        name_map: dict[str, list[str]] = defaultdict(list)
        for row in self.connection.execute(
            "SELECT id, name, brand, model FROM equipment"
        ):
            equipment[row["id"]] = row["name"]
            name_map[_normalize(row["name"])].append(row["id"])
            combined = f"{row['brand'] or ''} {row['model'] or ''}".strip()
            if combined:
                name_map[_normalize(combined)].append(row["id"])

        sheet_links: dict[str, set[str]] = defaultdict(set)
        for row in self.connection.execute(
            """
            SELECT activity_id, equipment_id FROM activity_equipment
            WHERE source = 'sheet'
            """
        ):
            sheet_links[row["activity_id"]].add(row["equipment_id"])

        linked_pairs = {
            (row["activity_id"], row["equipment_id"])
            for row in self.connection.execute(
                "SELECT activity_id, equipment_id FROM activity_equipment"
            )
        }

        return {
            "equipment": equipment,
            "name_map": name_map,
            "sheet_links": sheet_links,
            "linked_pairs": linked_pairs,
        }

    # -- resolution ---------------------------------------------------------

    def _resolve_one(
        self,
        gear: GearItem,
        context: dict,
        primary: dict[str, int],
        summary: RunalyzeGearSummary,
        *,
        dry_run: bool,
    ) -> None:
        external_id = _external_id(gear.gear_id)
        payload_json = _payload_json(gear.payload)

        if dry_run:
            source_record_id = self._gear_source_id(external_id)
        else:
            source_record_id = self.writer.upsert_source_record(
                source=SOURCE,
                record_type=GEAR_RECORD_TYPE,
                external_id=external_id,
                checksum=_checksum(payload_json),
                payload_json=payload_json,
                import_run_id=summary.run_id,
            )

        current = (
            self._linked_equipment(source_record_id)
            if source_record_id is not None
            else None
        )

        if current is not None:
            equipment_id = current
            summary.already_linked += 1
            self._resolve_ambiguous(
                external_id,
                "resolved: gear linked",
                summary,
                dry_run,
            )
        else:
            resolution = _resolve(
                gear,
                context["sheet_links"],
                context["name_map"],
            )
            if resolution[0] == "ambiguous":
                self._record_ambiguous(
                    gear,
                    resolution[1],
                    context["equipment"],
                    summary,
                    dry_run,
                )
                return

            equipment_id = resolution[1]
            if resolution[0] == "existing":
                summary.linked_existing += 1
                if not dry_run:
                    self.writer.link_equipment_source(
                        equipment_id,
                        source_record_id,
                    )
            else:
                summary.created += 1
                if not dry_run:
                    self.writer.upsert_equipment(
                        equipment_id,
                        type=gear.type,
                        name=gear.name,
                        acquired_on=gear.acquired_on,
                        retired_on=gear.retired_on,
                        notes=gear.notes,
                        source_record_id=source_record_id,
                    )
            self._resolve_ambiguous(
                external_id,
                "resolved: gear linked",
                summary,
                dry_run,
            )

        self._link_activities(
            gear,
            equipment_id,
            primary,
            context["linked_pairs"],
            summary,
            dry_run=dry_run,
        )

    def _link_activities(
        self,
        gear: GearItem,
        equipment_id: str,
        primary: dict[str, int],
        linked_pairs: set[tuple[str, str]],
        summary: RunalyzeGearSummary,
        *,
        dry_run: bool,
    ) -> None:
        for activity_id in sorted(gear.activities):
            pair = (activity_id, equipment_id)
            if pair in linked_pairs:
                summary.skipped_links += 1
                continue

            role = (
                "primary"
                if primary.get(activity_id) == gear.gear_id
                else "secondary"
            )

            if dry_run:
                linked_pairs.add(pair)
                _count_link(summary, role)
                continue

            written = self.writer.link_activity_equipment(
                activity_id,
                equipment_id,
                source=SOURCE,
                role=role,
            )
            if not written and role == "primary":
                written = self.writer.link_activity_equipment(
                    activity_id,
                    equipment_id,
                    source=SOURCE,
                    role="secondary",
                )
                if written:
                    role = "secondary"

            if written:
                linked_pairs.add(pair)
                _count_link(summary, role)

    # -- review items -------------------------------------------------------

    def _record_ambiguous(
        self,
        gear: GearItem,
        candidates: list[dict],
        equipment_names: dict[str, str],
        summary: RunalyzeGearSummary,
        dry_run: bool,
    ) -> None:
        external_id = _external_id(gear.gear_id)
        rows = [
            {
                "equipment_id": candidate["equipment_id"],
                "name": equipment_names.get(candidate["equipment_id"], ""),
                "count": candidate.get("count"),
                "reason": candidate.get("reason", ""),
            }
            for candidate in candidates
        ]
        fingerprint = review_fingerprint(
            [
                AMBIGUOUS_EQUIPMENT,
                GEAR_RECORD_TYPE,
                external_id,
                sorted(row["equipment_id"] for row in rows),
            ]
        )

        summary.ambiguous += 1
        summary.ambiguous_rows.append(
            {
                "gear_external_id": external_id,
                "gear_id": gear.gear_id,
                "gear_name": gear.name,
                "candidates": rows,
            }
        )

        for item in self.writer.review_items(
            category=AMBIGUOUS_EQUIPMENT,
            status="open",
        ):
            context = _context(item)
            if context.get("gear_external_id") != external_id:
                continue
            if item["fingerprint"] == fingerprint:
                continue
            if not dry_run:
                self.writer.set_review_status(
                    item["id"],
                    "resolved",
                    note="superseded: candidates changed",
                )

        if dry_run:
            return

        _, created = self.writer.record_review_item(
            category=AMBIGUOUS_EQUIPMENT,
            detail=f'gear "{gear.name}" has several candidate equipment rows',
            context={
                "rule": AMBIGUOUS_EQUIPMENT,
                "gear_external_id": external_id,
                "gear_name": gear.name,
                "candidates": rows,
            },
            severity="info",
            fingerprint=fingerprint,
        )
        summary.reviews_recorded += int(created)

    def _resolve_ambiguous(
        self,
        external_id: str,
        note: str,
        summary: RunalyzeGearSummary,
        dry_run: bool,
    ) -> None:
        for item in self.writer.review_items(
            category=AMBIGUOUS_EQUIPMENT,
            status="open",
        ):
            if _context(item).get("gear_external_id") != external_id:
                continue
            summary.ambiguous_resolved += 1
            if not dry_run:
                self.writer.set_review_status(
                    item["id"],
                    "resolved",
                    note=note,
                )

    # -- lookups ------------------------------------------------------------

    def _gear_source_id(self, external_id: str) -> int | None:
        row = self.connection.execute(
            """
            SELECT id FROM source_records
            WHERE source = ? AND record_type = ? AND external_id = ?
            """,
            (SOURCE, GEAR_RECORD_TYPE, external_id),
        ).fetchone()
        return row["id"] if row is not None else None

    def _linked_equipment(self, source_record_id: int) -> str | None:
        row = self.connection.execute(
            """
            SELECT equipment_id FROM equipment_source_links
            WHERE source_record_id = ?
            """,
            (source_record_id,),
        ).fetchone()
        return row["equipment_id"] if row is not None else None


def _resolve(
    gear: GearItem,
    sheet_links: dict[str, set[str]],
    name_map: dict[str, list[str]],
) -> tuple[str, object]:
    """Return (existing|new|ambiguous, equipment id or candidate list)."""
    with_links = [
        activity_id
        for activity_id in gear.activities
        if sheet_links.get(activity_id)
    ]

    if len(with_links) >= CO_OCCURRENCE_MIN_ACTIVITIES:
        counts: Counter[str] = Counter()
        for activity_id in with_links:
            for equipment_id in sheet_links[activity_id]:
                counts[equipment_id] += 1

        top, hits = counts.most_common(1)[0]
        if hits / len(with_links) >= CO_OCCURRENCE_SHARE:
            return "existing", top
        return "ambiguous", [
            {
                "equipment_id": equipment_id,
                "count": count,
                "reason": "co_occurrence",
            }
            for equipment_id, count in counts.most_common()
        ]

    candidates = sorted(set(name_map.get(_normalize(gear.name), [])))
    if len(candidates) == 1:
        return "existing", candidates[0]
    if len(candidates) > 1:
        return "ambiguous", [
            {
                "equipment_id": equipment_id,
                "reason": "name",
            }
            for equipment_id in candidates
        ]

    return "new", f"{GEAR_EQUIPMENT_PREFIX}{gear.gear_id}"


def _primary_by_activity(
    gear: dict[int, GearItem],
    activity_order: dict[str, list[int]],
) -> dict[str, int]:
    primary: dict[str, int] = {}
    for activity_id, gear_ids in activity_order.items():
        for gear_id in gear_ids:
            entry = gear.get(gear_id)
            if entry is not None and entry.type in PRIMARY_TYPES:
                primary[activity_id] = gear_id
                break
    return primary


def format_gear_summary(summary: RunalyzeGearSummary) -> str:
    label = "Runalyze gear dry run" if summary.dry_run else "Runalyze gear"
    lines = [
        f"{label}: {summary.payloads} payloads, "
        f"{summary.gear_items} gear records",
        f"  created: {summary.created}",
        f"  linked existing: {summary.linked_existing}",
        f"  already linked: {summary.already_linked}",
        f"  ambiguous: {summary.ambiguous}",
        f"  ambiguous resolved: {summary.ambiguous_resolved}",
        f"  review items recorded: {summary.reviews_recorded}",
        f"  activity links: {summary.activity_links} "
        f"({summary.primary_links} primary, "
        f"{summary.secondary_links} secondary, "
        f"{summary.skipped_links} already present)",
    ]

    for error in summary.errors:
        lines.append(f"  error: {error}")

    if not summary.dry_run:
        lines.append(f"Import run: {summary.run_id}")

    return "\n".join(lines)


def _write_ambiguous(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ambiguous": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _count_link(summary: RunalyzeGearSummary, role: str) -> None:
    summary.activity_links += 1
    if role == "primary":
        summary.primary_links += 1
    else:
        summary.secondary_links += 1


def _gear_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _external_id(gear_id: int) -> str:
    return f"{GEAR_EXTERNAL_PREFIX}{gear_id}"


def _normalize(value: object) -> str:
    text = str(value or "").casefold().replace("-", " ").replace("_", " ")
    return " ".join(text.split())


def _context(item) -> dict:
    try:
        data = json.loads(item["context_json"] or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _payload_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
