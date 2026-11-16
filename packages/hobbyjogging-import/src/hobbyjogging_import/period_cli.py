"""The ``period`` command: manual training periods (illness, travel, plan).

Intervals supplies the season starts and the sickness notes; a manual period
fills what it cannot — the end of an illness, a travel block, a plan. Manual
rows are never removed by the recompute.
"""

from __future__ import annotations

import argparse
from datetime import date

from hobbyjogging_core import TrainingRepository, TrainingWriter, open_database

KINDS = ("season", "plan", "illness", "travel", "recovery", "other")


def run_period(args, parser: argparse.ArgumentParser) -> int:
    action = args.period_action

    if action == "add":
        return _add(args, parser)
    if action == "list":
        return _list(args, parser)
    if action == "remove":
        return _remove(args, parser)

    parser.error(f"unknown period command: {action}")
    return 1


def _add(args, parser: argparse.ArgumentParser) -> int:
    if args.kind not in KINDS:
        parser.error(f"unknown kind: {args.kind} (choose {', '.join(KINDS)})")

    try:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else None
    except ValueError as exc:
        parser.error(f"invalid date: {exc}")

    if end is not None and end < start:
        parser.error("the end date is before the start date")

    period_id = f"manual:{args.kind}:{start.isoformat()}"

    connection = open_database(args.database)
    try:
        TrainingWriter(connection).upsert_training_period(
            period_id,
            kind=args.kind,
            start_date=start.isoformat(),
            end_date=end.isoformat() if end else None,
            label=args.label or "",
            notes=args.notes or "",
        )
        connection.commit()
    finally:
        connection.close()

    print(f"period saved: {period_id}")
    return 0


def _list(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        periods = TrainingRepository(connection).training_periods()
    finally:
        connection.close()

    if args.limit is not None:
        periods = periods[: args.limit]

    if not periods:
        print("No training periods stored.")
        return 0

    for period in periods:
        end = period.end_date.isoformat() if period.end_date else "open"
        label = period.label or "-"
        print(
            f"{period.start_date} → {end:<10} {period.kind:<8} "
            f"{label:<28} {period.source}"
        )

    return 0


def _remove(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        cursor = connection.execute(
            "UPDATE training_periods SET excluded_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ? "
            "AND excluded_at IS NULL",
            (args.period,),
        )
        connection.commit()
        removed = cursor.rowcount
    finally:
        connection.close()

    if not removed:
        parser.error(f"no training period with id {args.period}")

    print(f"period excluded: {args.period}")
    return 0
