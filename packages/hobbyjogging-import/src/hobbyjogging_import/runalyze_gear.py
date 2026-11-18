"""Resolve Runalyze gear records from stored activity payloads.

Phase 3 is offline: every Runalyze detail already sits in ``source_records``,
so gear needs no activity-detail request. Resolution order (root item 12):

1. co-occurrence with the sheet shoes on its matched activities
   (at least 3 activities, one item on at least 80% of them);
2. exact normalized name against existing equipment names / brand+model,
   then the same comparison with a trailing colour/size parenthetical removed
   (Runalyze tracks gear from 2023 on, so the sheet is the only bridge for the
   older shoes and its names carry no colour);
3. a new ``runalyze:equipment:<id>`` row.

Clothing (category 78698) is skipped: it is kit, not equipment. Ambiguity (a
split co-occurrence, or several name matches after stripping the parenthetical)
opens a non-hiding ``ambiguous_equipment`` review item; the gear is never
guessed. Resolved gear is linked to its activities: the first shoe/bike item is
primary, the rest secondary, manual and sheet links win.

A gear row the importer created earlier is reconciled: when the rule now
resolves it to an existing equipment row, its activity and source links move
there and the importer-owned duplicate is removed. Rows with manual links or
another source link are left alone.
"""

from __future__ import annotations

import hashlib
import json
import re
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
# Clothing and kit: Runalyze tracks it next to gear, but a T-shirt is not
# equipment in the canonical model and would only add one-link rows.
IGNORED_CATEGORIES = frozenset({78698})
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
    skipped_clothing: int = 0
    created: int = 0
    linked_existing: int = 0
    already_linked: int = 0
    reconciled: int = 0
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

            gear_ids = [
                gear_id
                for gear_id in sorted(gear)
                if gear[gear_id].category_id not in IGNORED_CATEGORIES
            ]
            summary.skipped_clothing = len(gear) - len(gear_ids)
            summary.gear_items = len(gear_ids)
            if limit is not None:
                gear_ids = gear_ids[:limit]

            context = self._contexts()
            primary = _primary_by_activity(gear, activity_order)

            for gear_id in gear_ids:
                changed = self._resolve_one(
                    gear[gear_id],
                    context,
                    primary,
                    summary,
                    dry_run=dry_run,
                )
                if changed:
                    # A created or merged row changes the name map; keep the
                    # next gear from resolving to a row this run removed.
                    context = self._contexts()

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
            combined = f"{row['brand'] or ''} {row['model'] or ''}"
            for value in (row["name"], combined):
                for key in _name_keys(value):
                    name_map[key].append(row["id"])

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

        # Rows the importer created for another gear record are not candidates:
        # two Runalyze gear ids are two items, even when the names differ only
        # in the colour parenthetical.
        gear_owned = {
            row["equipment_id"]
            for row in self.connection.execute(
                """
                SELECT esl.equipment_id
                FROM equipment_source_links esl
                JOIN source_records sr ON sr.id = esl.source_record_id
                WHERE sr.source = ? AND sr.record_type = ?
                """,
                (SOURCE, GEAR_RECORD_TYPE),
            )
        }

        return {
            "equipment": equipment,
            "name_map": name_map,
            "sheet_links": sheet_links,
            "linked_pairs": linked_pairs,
            "gear_owned": gear_owned,
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
    ) -> bool:
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
            target = self._reconciled_target(gear, context, current)
            if target is not None:
                self._merge_equipment(
                    current,
                    target,
                    context["linked_pairs"],
                    dry_run=dry_run,
                )
                summary.reconciled += 1
                equipment_id = target
                changed = True
            else:
                equipment_id = current
                summary.already_linked += 1
                changed = False
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
                context["gear_owned"],
            )
            if resolution[0] == "ambiguous":
                self._record_ambiguous(
                    gear,
                    resolution[1],
                    context["equipment"],
                    summary,
                    dry_run,
                )
                return False

            equipment_id = resolution[1]
            if resolution[0] == "existing":
                summary.linked_existing += 1
                changed = False
                if not dry_run:
                    self.writer.link_equipment_source(
                        equipment_id,
                        source_record_id,
                    )
            else:
                summary.created += 1
                changed = True
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
        return changed

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

    # -- reconciliation -----------------------------------------------------

    def _reconciled_target(
        self,
        gear: GearItem,
        context: dict,
        current: str,
    ) -> str | None:
        """Return a better existing row for a gear the importer already linked.

        Only an importer-owned row qualifies: a human-edited row or one that
        another source also links must keep its identity.
        """
        if not current.startswith(GEAR_EQUIPMENT_PREFIX):
            return None
        if self.connection.execute(
            """
            SELECT 1 FROM activity_equipment
            WHERE equipment_id = ? AND is_manual = 1
            """,
            (current,),
        ).fetchone():
            return None
        if self.connection.execute(
            """
            SELECT 1 FROM equipment_source_links
            WHERE equipment_id = ? AND source_record_id NOT IN (
                SELECT id FROM source_records
                WHERE source = ? AND record_type = ?
            )
            """,
            (current, SOURCE, GEAR_RECORD_TYPE),
        ).fetchone():
            return None

        resolution = _resolve(
            gear,
            context["sheet_links"],
            context["name_map"],
            context["gear_owned"],
        )
        if resolution[0] != "existing" or resolution[1] == current:
            return None
        target = resolution[1]
        if self.connection.execute(
            "SELECT 1 FROM equipment WHERE id = ?",
            (target,),
        ).fetchone() is None:
            return None
        return target

    def _merge_equipment(
        self,
        old_id: str,
        new_id: str,
        linked_pairs: set[tuple[str, str]],
        *,
        dry_run: bool,
    ) -> None:
        """Move a duplicate gear row's links onto the match, then drop it."""
        rows = self.connection.execute(
            """
            SELECT activity_id, role FROM activity_equipment
            WHERE equipment_id = ?
            ORDER BY activity_id, role
            """,
            (old_id,),
        ).fetchall()

        for row in rows:
            activity_id = row["activity_id"]
            role = row["role"]
            linked_pairs.add((activity_id, new_id))
            if dry_run:
                linked_pairs.discard((activity_id, old_id))
                continue

            if role == "primary":
                holder = self.connection.execute(
                    """
                    SELECT equipment_id FROM activity_equipment
                    WHERE activity_id = ? AND role = 'primary'
                    """,
                    (activity_id,),
                ).fetchone()
                if holder is not None and holder["equipment_id"] != old_id:
                    # The sheet or a human owns the primary slot.
                    role = "secondary"
            self.connection.execute(
                """
                DELETE FROM activity_equipment
                WHERE activity_id = ? AND equipment_id = ?
                """,
                (activity_id, old_id),
            )
            exists = self.connection.execute(
                """
                SELECT 1 FROM activity_equipment
                WHERE activity_id = ? AND equipment_id = ? AND role = ?
                """,
                (activity_id, new_id, role),
            ).fetchone()
            if exists is None:
                self.connection.execute(
                    """
                    INSERT INTO activity_equipment (
                        activity_id, equipment_id, role, source
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (activity_id, new_id, role, SOURCE),
                )
            linked_pairs.discard((activity_id, old_id))

        if dry_run:
            return

        self.connection.execute(
            """
            UPDATE equipment_source_links SET equipment_id = ?
            WHERE equipment_id = ?
            """,
            (new_id, old_id),
        )
        self.connection.execute(
            "DELETE FROM equipment WHERE id = ?",
            (old_id,),
        )

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
    gear_owned: set[str] = frozenset(),
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

    candidates = _name_candidates(
        gear.name,
        name_map,
        "name",
        gear_owned,
    )
    if candidates:
        if len(candidates) == 1:
            return "existing", candidates[0][0]
        return "ambiguous", [
            {"equipment_id": equipment_id, "reason": reason}
            for equipment_id, reason in candidates
        ]

    return "new", f"{GEAR_EQUIPMENT_PREFIX}{gear.gear_id}"


def _name_candidates(
    value: str,
    name_map: dict[str, list[str]],
    reason: str,
    excluded: set[str] = frozenset(),
) -> list[tuple[str, str]]:
    """Match an exact name, then with the colour/size parenthetical gone."""
    exact = sorted(set(name_map.get(_normalize(value), [])) - excluded)
    if exact:
        return [(equipment_id, reason) for equipment_id in exact]

    loose_key = _normalize(_PARENTHETICAL.sub("", value))
    if not loose_key or loose_key == _normalize(value):
        return []
    loose = sorted(set(name_map.get(loose_key, [])) - excluded)
    return [
        (equipment_id, f"{reason}_parenthetical")
        for equipment_id in loose
    ]


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
        f"  skipped clothing: {summary.skipped_clothing}",
        f"  created: {summary.created}",
        f"  linked existing: {summary.linked_existing}",
        f"  already linked: {summary.already_linked}",
        f"  reconciled duplicates: {summary.reconciled}",
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


_PARENTHETICAL = re.compile(r"\s*\([^()]*\)\s*$")


def _name_keys(value: object) -> list[str]:
    """Both comparison keys: the exact name and its colour-stripped form."""
    text = str(value or "")
    keys = [_normalize(text)]
    stripped = _normalize(_PARENTHETICAL.sub("", text))
    if stripped and stripped not in keys:
        keys.append(stripped)
    return [key for key in keys if key]


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
