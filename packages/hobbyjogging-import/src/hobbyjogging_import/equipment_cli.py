"""The ``equipment`` command: create, edit and retire gear by hand.

A manual row is an input. A later sheet, Runalyze or Strava import may attach a
source link, but ``upsert_equipment(..., is_manual=True)`` keeps the name,
brand, model, dates and notes from being rewritten. Retire sets ``retired_on``;
nothing is ever hard-deleted.
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from hobbyjogging_core import TrainingRepository, TrainingWriter, open_database

from .history import history_lines, record_changes
from .select import SelectionError, resolve_equipment
from .values import parse_distance_m

_TYPES = ("shoe", "bike", "other")
_FIELDS = (
    "type",
    "name",
    "brand",
    "model",
    "acquired_on",
    "retired_on",
    "target_distance_m",
    "notes",
)
SOURCE = "manual"


def add_equipment_parser(subparsers) -> None:
    """Register the ``equipment`` command on the import parser."""
    equipment = subparsers.add_parser(
        "equipment",
        help="create, edit and retire equipment by hand",
    )
    equipment.add_argument("--database", type=Path)
    equipment_sub = equipment.add_subparsers(
        dest="equipment_action",
        required=True,
    )
    equipment_add = equipment_sub.add_parser("add", help="create equipment")
    equipment_add.add_argument("name")
    equipment_add.add_argument(
        "--type",
        choices=("shoe", "bike", "other"),
        default="shoe",
    )
    equipment_add.add_argument("--brand", default="")
    equipment_add.add_argument("--model", default="")
    equipment_add.add_argument("--acquired")
    equipment_add.add_argument("--retired")
    equipment_add.add_argument(
        "--target-distance",
        help="target distance, e.g. 800km or 800000m",
    )
    equipment_add.add_argument("--notes", default="")
    equipment_add.add_argument("--note", help="edit-log note")
    equipment_add.add_argument("--dry-run", action="store_true")

    equipment_list = equipment_sub.add_parser("list", help="list equipment")
    equipment_list.add_argument(
        "--type",
        choices=("shoe", "bike", "other"),
    )
    equipment_list.add_argument("--limit", type=int)

    equipment_edit = equipment_sub.add_parser("edit", help="edit equipment")
    equipment_edit.add_argument(
        "equipment",
        metavar="EQUIPMENT",
        help="equipment id or a name substring",
    )
    equipment_edit.add_argument("--name")
    equipment_edit.add_argument(
        "--type",
        choices=("shoe", "bike", "other"),
    )
    equipment_edit.add_argument("--brand")
    equipment_edit.add_argument("--model")
    equipment_edit.add_argument("--acquired")
    equipment_edit.add_argument("--retired")
    equipment_edit.add_argument(
        "--target-distance",
        help="target distance, e.g. 800km or 800000m",
    )
    equipment_edit.add_argument("--notes")
    equipment_edit.add_argument("--note", help="edit-log note")
    equipment_edit.add_argument("--dry-run", action="store_true")

    equipment_retire = equipment_sub.add_parser(
        "retire",
        help="set retired_on (never delete)",
    )
    equipment_retire.add_argument(
        "equipment",
        metavar="EQUIPMENT",
        help="equipment id or a name substring",
    )
    equipment_retire.add_argument(
        "--on",
        help="retirement date (default: today)",
    )
    equipment_retire.add_argument("--note", help="edit-log note")
    equipment_retire.add_argument("--dry-run", action="store_true")

    equipment_history = equipment_sub.add_parser(
        "history",
        help="show one equipment item's edit history",
    )
    equipment_history.add_argument(
        "equipment",
        metavar="EQUIPMENT",
        help="equipment id or a name substring",
    )


def run_equipment(args, parser: argparse.ArgumentParser) -> int:
    action = args.equipment_action
    if action == "add":
        return _add(args, parser)
    if action == "list":
        return _list(args, parser)
    if action == "edit":
        return _edit(args, parser)
    if action == "retire":
        return _retire(args, parser)
    if action == "history":
        return _history(args, parser)

    parser.error(f"unknown equipment command: {action}")
    return 1


def _add(args, parser: argparse.ArgumentParser) -> int:
    name = str(args.name).strip()
    if not name:
        parser.error("equipment name must not be empty")
    type_ = args.type
    if type_ not in _TYPES:
        parser.error(f"unknown equipment type: {type_}")

    target = _target(args.target_distance, parser)
    acquired = _date(args.acquired, parser)
    retired = _date(args.retired, parser)

    connection = open_database(args.database)
    try:
        matches = _name_matches(
            connection,
            name,
            args.brand,
            args.model,
        )
        if matches:
            print("equipment name already exists:")
            for row in matches:
                print(f"  {row['id']}  {row['name']}")
            print("use `equipment edit <id>` or choose a different name")
            return 1

        equipment_id = _new_id(connection, name)
        new = {
            "type": type_,
            "name": name,
            "brand": args.brand or "",
            "model": args.model or "",
            "acquired_on": acquired,
            "retired_on": retired,
            "target_distance_m": target,
            "notes": args.notes or "",
        }
        TrainingWriter(connection).upsert_equipment(
            equipment_id,
            type=type_,
            name=name,
            brand=new["brand"],
            model=new["model"],
            acquired_on=acquired,
            retired_on=retired,
            target_distance_m=target,
            notes=new["notes"],
            is_manual=True,
        )
        record_changes(
            TrainingWriter(connection),
            entity_kind="equipment",
            entity_id=equipment_id,
            old={},
            new=new,
            source=SOURCE,
            note=args.note or "equipment add",
        )
        if args.dry_run:
            connection.rollback()
            print(f"Dry run: equipment {equipment_id} not written.")
        else:
            connection.commit()
            print(f"equipment added: {equipment_id}")
    finally:
        connection.close()
    return 0


def _edit(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        try:
            equipment_id = resolve_equipment(connection, args.equipment)
        except SelectionError as exc:
            parser.error(str(exc))
        old_row = connection.execute(
            "SELECT * FROM equipment WHERE id = ?",
            (equipment_id,),
        ).fetchone()
        old = {field: old_row[field] for field in _FIELDS}

        new = dict(old)
        if args.name is not None:
            new["name"] = args.name.strip()
        if args.type is not None:
            new["type"] = args.type
        if args.brand is not None:
            new["brand"] = args.brand
        if args.model is not None:
            new["model"] = args.model
        if args.acquired is not None:
            new["acquired_on"] = _iso(_date(args.acquired, parser))
        if args.retired is not None:
            new["retired_on"] = _iso(_date(args.retired, parser))
        if args.target_distance is not None:
            new["target_distance_m"] = _target(
                args.target_distance, parser
            )
        if args.notes is not None:
            new["notes"] = args.notes

        changed = _changed(old, new)
        if not changed:
            print("no change")
            return 0

        _write(connection, equipment_id, new)
        record_changes(
            TrainingWriter(connection),
            entity_kind="equipment",
            entity_id=equipment_id,
            old=old,
            new=new,
            source=SOURCE,
            note=args.note or "equipment edit",
        )
        if args.dry_run:
            connection.rollback()
            print(f"Dry run: equipment {equipment_id} not changed.")
        else:
            connection.commit()
            print(
                f"equipment updated: {equipment_id} "
                f"({', '.join(changed)})"
            )
    finally:
        connection.close()
    return 0


def _retire(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        try:
            equipment_id = resolve_equipment(connection, args.equipment)
        except SelectionError as exc:
            parser.error(str(exc))
        old_row = connection.execute(
            "SELECT * FROM equipment WHERE id = ?",
            (equipment_id,),
        ).fetchone()
        old = {field: old_row[field] for field in _FIELDS}
        retired_on = args.on or date.today().isoformat()
        try:
            date.fromisoformat(retired_on)
        except ValueError:
            parser.error(f"invalid date: {retired_on}")

        if old["retired_on"] == retired_on:
            print("no change")
            return 0

        new = dict(old)
        new["retired_on"] = retired_on
        _write(connection, equipment_id, new)
        record_changes(
            TrainingWriter(connection),
            entity_kind="equipment",
            entity_id=equipment_id,
            old=old,
            new=new,
            source=SOURCE,
            note=args.note or "equipment retire",
        )
        if args.dry_run:
            connection.rollback()
            print(f"Dry run: equipment {equipment_id} not retired.")
        else:
            connection.commit()
            print(f"equipment retired: {equipment_id} on {retired_on}")
    finally:
        connection.close()
    return 0


def _list(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        equipment = TrainingRepository(connection).equipment()
    finally:
        connection.close()

    if args.type is not None:
        equipment = [item for item in equipment if item.type == args.type]
    if args.limit is not None:
        equipment = equipment[: args.limit]

    if not equipment:
        print("No equipment stored.")
        return 0

    for item in equipment:
        dates = " ".join(
            part
            for part in (
                f"from {item.acquired_on}" if item.acquired_on else "",
                f"to {item.retired_on}" if item.retired_on else "",
            )
            if part
        )
        label = " ".join(
            part for part in (item.brand, item.model) if part
        )
        manual = " manual" if item.is_manual else ""
        target = (
            f"{item.target_distance_m / 1000:.0f} km"
            if item.target_distance_m
            else "-"
        )
        print(
            f"{item.id:<28} {item.type:<5} {item.name:<28} "
            f"{label:<20} {dates:<24} {target:>8}{manual}"
        )

    return 0


def _history(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        try:
            equipment_id = resolve_equipment(connection, args.equipment)
        except SelectionError as exc:
            parser.error(str(exc))
        entries = TrainingRepository(connection).edit_history(
            "equipment", equipment_id
        )
    finally:
        connection.close()

    for line in history_lines(entries):
        print(line)
    return 0


def _write(connection, equipment_id: str, values: dict) -> None:
    TrainingWriter(connection).upsert_equipment(
        equipment_id,
        type=values["type"],
        name=values["name"],
        brand=values["brand"],
        model=values["model"],
        acquired_on=values["acquired_on"],
        retired_on=values["retired_on"],
        target_distance_m=values["target_distance_m"],
        notes=values["notes"],
        is_manual=True,
    )


def _changed(old: dict, new: dict) -> list[str]:
    return [
        field
        for field in _FIELDS
        if old.get(field) != new.get(field)
    ]


def _name_matches(connection, name: str, brand: str, model: str):
    wanted = _normalize(name)
    wanted_pair = _normalize(" ".join(part for part in (brand, model) if part))
    matches = []
    for row in connection.execute("SELECT * FROM equipment ORDER BY name, id"):
        if _normalize(row["name"]) == wanted:
            matches.append(row)
            continue
        pair = _normalize(
            " ".join(
                part for part in (row["brand"], row["model"]) if part
            )
        )
        if wanted_pair and pair == wanted_pair:
            matches.append(row)
    return matches


def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _new_id(connection, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize(name)).strip("-")
    base = f"manual:equipment:{slug or 'item'}"
    candidate = base
    index = 2
    while connection.execute(
        "SELECT 1 FROM equipment WHERE id = ?", (candidate,)
    ).fetchone():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _target(value: str | None, parser: argparse.ArgumentParser):
    if value is None:
        return None
    try:
        return parse_distance_m(value)
    except ValueError as exc:
        parser.error(str(exc))


def _date(value: str | None, parser: argparse.ArgumentParser):
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        parser.error(f"invalid date: {value}")


def _iso(value: date | None):
    return value.isoformat() if value is not None else None
