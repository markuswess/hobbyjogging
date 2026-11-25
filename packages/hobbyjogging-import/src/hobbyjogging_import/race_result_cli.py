"""The ``race-result`` command: official race metadata by hand.

Runalyze supplies race results for the races it knows; this fills the gaps and
lets a result be entered the day it happens, before any import sees it. The row
is keyed by activity and a manual row is never overwritten by a source. Every
change appends an ``edit_log`` row; the activity selector accepts an id, date,
``last`` or a name.
"""

from __future__ import annotations

import argparse

from hobbyjogging_core import TrainingRepository, TrainingWriter, open_database

from .history import history_lines, record_changes
from .select import SelectionError, resolve_activity
from .values import format_duration_s, parse_distance_m, parse_duration_s

SOURCE = "manual"
ENTITY = "race_result"


def run_race_result(args, parser: argparse.ArgumentParser) -> int:
    action = args.race_result_action

    if action == "add":
        return _add(args, parser)
    if action == "list":
        return _list(args, parser)
    if action == "remove":
        return _remove(args, parser)
    if action == "history":
        return _history(args, parser)

    parser.error(f"unknown race-result command: {action}")
    return 1


def _add(args, parser: argparse.ArgumentParser) -> int:
    fields: dict[str, object] = {}

    try:
        if args.distance is not None:
            fields["official_distance_m"] = parse_distance_m(args.distance)
        if args.time is not None:
            fields["official_time_s"] = parse_duration_s(args.time)
    except ValueError as exc:
        parser.error(str(exc))

    optional = {
        "name": args.name,
        "place_total": args.place,
        "place_gender": args.place_gender,
        "place_ageclass": args.place_ageclass,
        "participants_total": args.participants,
        "participants_gender": args.participants_gender,
        "participants_ageclass": args.participants_ageclass,
        "priority_level": args.priority,
        "status": args.status,
        "notes": args.notes,
        "event_id": args.event_id,
    }
    fields.update(
        {key: value for key, value in optional.items() if value is not None}
    )

    if args.officially_measured:
        fields["officially_measured"] = True

    if not fields:
        parser.error("nothing to write: pass at least one field")

    connection = open_database(args.database)
    try:
        try:
            activity_id = resolve_activity(connection, args.activity)
        except SelectionError as exc:
            parser.error(str(exc))
        old = _row(connection, activity_id)
        writer = TrainingWriter(connection)
        written = writer.upsert_race_result(
            activity_id,
            source=SOURCE,
            **fields,
        )
        if not written:
            connection.rollback()
            print("no change: the existing row is not replaceable")
            return 1
        record_changes(
            writer,
            entity_kind=ENTITY,
            entity_id=activity_id,
            old=old,
            new=fields,
            source=SOURCE,
            note=args.note or "race-result add",
        )
        if args.dry_run:
            connection.rollback()
            print(f"Dry run: race result for {activity_id} not written.")
        else:
            connection.commit()
            print(f"race result saved for {activity_id}")
    finally:
        connection.close()
    return 0


def _list(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        results = TrainingRepository(connection).race_results()
    finally:
        connection.close()

    if args.limit is not None:
        results = results[: args.limit]

    if not results:
        print("No race results stored.")
        return 0

    for result in results:
        distance = (
            f"{result.official_distance_m / 1000:.2f} km"
            if result.official_distance_m
            else "-"
        )
        time = (
            format_duration_s(result.official_time_s)
            if result.official_time_s
            else "-"
        )
        place = (
            f"{result.place_total}/{result.participants_total}"
            if result.place_total
            else "-"
        )
        label = result.name or result.activity_id
        print(
            f"{result.date}  {label:<32} {distance:>10}  {time:>8}  "
            f"{place:>10}  {result.status}"
        )

    return 0


def _remove(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        try:
            activity_id = resolve_activity(connection, args.activity)
        except SelectionError as exc:
            parser.error(str(exc))
        old = _row(connection, activity_id)
        if not old:
            parser.error(f"no race result for {activity_id}")

        cursor = connection.execute(
            "UPDATE race_results SET excluded_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP WHERE activity_id = ? "
            "AND excluded_at IS NULL",
            (activity_id,),
        )
        if not cursor.rowcount:
            parser.error(f"no race result for {activity_id}")

        record_changes(
            TrainingWriter(connection),
            entity_kind=ENTITY,
            entity_id=activity_id,
            old={"excluded_at": False},
            new={"excluded_at": True},
            source=SOURCE,
            note=args.note or "race-result remove",
        )
        if args.dry_run:
            connection.rollback()
            print(f"Dry run: race result for {activity_id} not excluded.")
        else:
            connection.commit()
            print(f"race result excluded for {activity_id}")
    finally:
        connection.close()
    return 0


def _history(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        try:
            activity_id = resolve_activity(connection, args.activity)
        except SelectionError as exc:
            parser.error(str(exc))
        entries = TrainingRepository(connection).edit_history(
            ENTITY, activity_id
        )
    finally:
        connection.close()

    for line in history_lines(entries):
        print(line)
    return 0


def _row(connection, activity_id: str) -> dict[str, object]:
    row = connection.execute(
        f"SELECT {', '.join(TrainingWriter.RACE_RESULT_FIELDS)} "
        "FROM race_results WHERE activity_id = ?",
        (activity_id,),
    ).fetchone()
    if row is None:
        return {}
    return {field: row[field] for field in TrainingWriter.RACE_RESULT_FIELDS}
