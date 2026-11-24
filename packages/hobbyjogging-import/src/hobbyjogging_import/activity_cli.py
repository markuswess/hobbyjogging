"""The direct human write surface: `hobbyjogging activity edit <id>`.

Unlike triage, this command needs no review item. Every value it changes is
written as a manual override through the same ``editing`` functions triage
uses, so a reimport cannot undo it and the quality re-check never diverges.
"""

from __future__ import annotations

from typing import Callable

from hobbyjogging_core import TrainingRepository, TrainingWriter, open_database
from hobbyjogging_core.import_rules import MANUAL_FIELDS

from .editing import (
    SET_FIELDS,
    EditApplication,
    apply_manual_clear,
    apply_manual_edit,
    apply_manual_set_edit,
    format_change,
)
from .values import (
    VALUE_PROMPTS,
    parse_feel,
    parse_rpe,
    parse_text,
)

# Interactive walks the scalar fields in a stable, readable order.
SCALAR_ORDER = (
    "name",
    "description",
    "sport",
    "sub_sport",
    "rpe",
    "feel",
    "duration_s",
    "distance_m",
)

SCALAR_PARSERS = {
    "name": parse_text,
    "description": parse_text,
    "sport": VALUE_PROMPTS["sport"][1],
    "sub_sport": parse_text,
    "rpe": parse_rpe,
    "feel": parse_feel,
    "duration_s": VALUE_PROMPTS["duration_s"][1],
    "distance_m": VALUE_PROMPTS["distance_m"][1],
}

CLEAR_ALIASES = {
    "name": "name",
    "description": "description",
    "sport": "sport",
    "sub-sport": "sub_sport",
    "sub_sport": "sub_sport",
    "rpe": "rpe",
    "feel": "feel",
    "duration": "duration_s",
    "duration_s": "duration_s",
    "distance": "distance_m",
    "distance_m": "distance_m",
    "tag": "tags",
    "tags": "tags",
    "method": "methods",
    "methods": "methods",
    "target": "targets",
    "targets": "targets",
    "equipment": "equipment",
}

FLAG_FIELDS = (
    ("name", "name", parse_text),
    ("description", "description", parse_text),
    ("duration", "duration_s", VALUE_PROMPTS["duration_s"][1]),
    ("distance", "distance_m", VALUE_PROMPTS["distance_m"][1]),
    ("sport", "sport", VALUE_PROMPTS["sport"][1]),
    ("rpe", "rpe", parse_rpe),
    ("feel", "feel", parse_feel),
    ("sub_sport", "sub_sport", parse_text),
)


def run_activity(
    args,
    parser,
    *,
    read: Callable[[str], str] = input,
    print: Callable[..., None] = print,
) -> int:
    if args.activity_action != "edit":
        parser.error(f"unknown activity action: {args.activity_action}")

    connection = open_database(args.database)
    try:
        writer = TrainingWriter(connection)
        return _run_edit(args, writer, parser, read=read, print=print)
    finally:
        connection.close()


def _run_edit(args, writer, parser, *, read, print) -> int:
    row = writer.connection.execute(
        "SELECT id, local_date, sport, name, excluded_at "
        "FROM activities WHERE id = ?",
        (args.activity_id,),
    ).fetchone()
    if row is None:
        parser.error(f"unknown activity: {args.activity_id}")

    if args.history:
        if _has_changes(args):
            parser.error("--history cannot be combined with edits")
        return _print_history(writer, args.activity_id, print)

    if args.item is not None and writer.review_item(args.item) is None:
        parser.error(f"unknown review item: {args.item}")

    try:
        scalars, sets, clears = _collect_changes(
            args,
            writer,
            parser,
            read=read,
            print=print,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if not scalars and not sets and not clears:
        print("Nothing to change.")
        return 0

    print(
        f"Editing {row['id']}  {row['local_date']}  "
        f"{row['sport']}  {row['name']}".rstrip()
    )

    applied = 0
    try:
        for field in clears:
            application = apply_manual_clear(
                writer,
                activity_id=args.activity_id,
                field=field,
                resolve_item_id=args.item,
                note=args.note,
                source="activity-edit",
            )
            if application is None:
                print(f"clear {field}: no manual value to remove")
                continue
            _report(application, print)
            applied += 1

        for field in ("tags", "methods", "targets", "equipment"):
            if field not in sets:
                continue
            application = apply_manual_set_edit(
                writer,
                activity_id=args.activity_id,
                field=field,
                values=sets[field],
                resolve_item_id=args.item,
                note=args.note,
                source="activity-edit",
            )
            _report(application, print)
            applied += 1

        for field, value in scalars.items():
            application = apply_manual_edit(
                writer,
                activity_id=args.activity_id,
                field=field,
                value=value,
                resolve_item_id=args.item,
                note=args.note,
                source="activity-edit",
            )
            _report(application, print)
            applied += 1
    except ValueError as exc:
        writer.connection.rollback()
        parser.error(str(exc))
    except Exception:
        writer.connection.rollback()
        raise

    if args.dry_run:
        writer.connection.rollback()
        print(f"Dry run: {applied} change(s) not written.")
    else:
        writer.connection.commit()
    return 0


# -- collecting changes --------------------------------------------------


def _has_changes(args) -> bool:
    return bool(
        args.name is not None
        or args.description is not None
        or args.duration is not None
        or args.distance is not None
        or args.sport is not None
        or args.rpe is not None
        or args.feel is not None
        or args.sub_sport is not None
        or args.tag
        or args.method
        or args.target
        or args.equipment
        or args.clear
    )


def _collect_changes(args, writer, parser, *, read, print):
    interactive = args.interactive or not _has_changes(args)
    if interactive:
        return _interactive_changes(
            args.activity_id,
            writer,
            read=read,
            print=print,
        )

    scalars: dict[str, object] = {}
    sets: dict[str, list[str]] = {}
    clears: list[str] = []

    for flag, field, parse in FLAG_FIELDS:
        text = getattr(args, flag)
        if text is None:
            continue
        scalars[field] = _parse(parse, text)

    if args.tag:
        sets["tags"] = list(args.tag)
    if args.method:
        sets["methods"] = list(args.method)
    if args.target:
        sets["targets"] = list(args.target)
    if args.equipment:
        sets["equipment"] = list(args.equipment)

    for raw in args.clear:
        field = CLEAR_ALIASES.get(raw.strip().lower())
        if field is None:
            parser.error(f"cannot clear unknown field: {raw}")
        if field in scalars or field in sets:
            parser.error(f"cannot both set and clear {field}")
        if field not in clears:
            clears.append(field)

    for field in clears:
        if field not in MANUAL_FIELDS and field not in SET_FIELDS:
            parser.error(f"field cannot be edited: {field}")

    return scalars, sets, clears


def _interactive_changes(activity_id, writer, *, read, print):
    row = writer.connection.execute(
        "SELECT * FROM activities WHERE id = ?",
        (activity_id,),
    ).fetchone()

    scalars: dict[str, object] = {}
    sets: dict[str, list[str]] = {}
    clears: list[str] = []

    for field in SCALAR_ORDER:
        current = row[field]
        parser = SCALAR_PARSERS[field]
        hint = VALUE_PROMPTS.get(field, (None, None))[0]
        prompt = f"  {field} [{format_change(field, current)}]"
        if hint:
            prompt += f" {hint}"
        else:
            prompt += ": "
        try:
            answer = read(prompt).strip()
        except EOFError:
            answer = ""

        if not answer:
            continue
        if answer == "-":
            clears.append(field)
            continue
        scalars[field] = _parse(parser, answer)

    for field in ("tags", "methods", "targets", "equipment"):
        current = _current_set(writer, activity_id, field)
        prompt = (
            f"  {field} [{format_change(field, current)}] "
            "(comma-separated; blank keeps, - clears): "
        )
        try:
            answer = read(prompt).strip()
        except EOFError:
            answer = ""

        if not answer:
            continue
        if answer == "-":
            clears.append(field)
            continue
        sets[field] = [
            item.strip() for item in answer.split(",") if item.strip()
        ]

    return scalars, sets, clears


def _current_set(writer, activity_id, field):
    query = {
        "tags": (
            "SELECT tag AS value FROM activity_tags "
            "WHERE activity_id = ? ORDER BY tag"
        ),
        "methods": (
            "SELECT method AS value FROM activity_workout_methods "
            "WHERE activity_id = ? ORDER BY method"
        ),
        "targets": (
            "SELECT target AS value FROM activity_workout_targets "
            "WHERE activity_id = ? ORDER BY target"
        ),
        "equipment": (
            "SELECT equipment_id AS value FROM activity_equipment "
            "WHERE activity_id = ? ORDER BY role, equipment_id"
        ),
    }[field]
    return [
        row["value"]
        for row in writer.connection.execute(query, (activity_id,))
    ]


def _parse(parser, text: str):
    try:
        return parser(text)
    except ValueError as exc:
        raise ValueError(str(exc)) from None


# -- output --------------------------------------------------------------


def _report(application: EditApplication, print) -> None:
    print(application.describe())
    for item_id in application.resolved_items:
        print(f"resolved #{item_id}")
    if application.field in SET_FIELDS:
        return
    if application.okay:
        print("quality: ok")
    else:
        print(
            "quality: still flagged — "
            f"{application.describe_findings()}"
        )


def _print_history(writer, activity_id: str, print) -> int:
    repository = TrainingRepository(writer.connection)
    entries = repository.edit_history("activity", activity_id)
    if not entries:
        print(f"No edits recorded for {activity_id}.")
        return 0

    for entry in entries:
        print(
            f"#{entry.id} {entry.created_at} [{entry.source}] "
            f"{entry.field}: {format_change(entry.field, entry.old)} → "
            f"{format_change(entry.field, entry.new)}"
        )
        if entry.note:
            print(f"    {entry.note}")
    return 0
