"""The ``race-result`` command: official race metadata by hand.

Runalyze supplies race results for the races it knows; this fills the gaps and
lets a result be entered the day it happens, before any import sees it. The row
is keyed by activity and a manual row is never overwritten by a source.
"""

from __future__ import annotations

import argparse

from hobbyjogging_core import TrainingRepository, TrainingWriter, open_database

from .values import format_duration_s, parse_distance_m, parse_duration_s

SOURCE = "manual"


def run_race_result(args, parser: argparse.ArgumentParser) -> int:
    action = args.race_result_action

    if action == "add":
        return _add(args, parser)
    if action == "list":
        return _list(args, parser)
    if action == "remove":
        return _remove(args, parser)

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
        writer = TrainingWriter(connection)

        row = connection.execute(
            "SELECT 1 FROM activities WHERE id = ?",
            (args.activity,),
        ).fetchone()
        if row is None:
            parser.error(f"unknown activity: {args.activity}")

        written = writer.upsert_race_result(
            args.activity,
            source=SOURCE,
            **fields,
        )
        connection.commit()
    finally:
        connection.close()

    if not written:
        print("no change: the existing row is not replaceable")
        return 1

    print(f"race result saved for {args.activity}")
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
        cursor = connection.execute(
            "UPDATE race_results SET excluded_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP WHERE activity_id = ? "
            "AND excluded_at IS NULL",
            (args.activity,),
        )
        connection.commit()
        removed = cursor.rowcount
    finally:
        connection.close()

    if not removed:
        parser.error(f"no race result for {args.activity}")

    print(f"race result excluded for {args.activity}")
    return 0

