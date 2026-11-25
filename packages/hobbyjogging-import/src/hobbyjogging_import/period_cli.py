"""The ``period`` command: manual training periods (illness, travel, plan).

Intervals supplies the season starts and the sickness notes; a manual period
fills what it cannot — the end of an illness, a travel block, a plan. Manual
rows are never removed by the recompute.
"""

from __future__ import annotations

import argparse
from datetime import date

from hobbyjogging_core import TrainingRepository, TrainingWriter, open_database

from .history import history_lines, record_changes
from .select import SelectionError, resolve_period

KINDS = ("season", "plan", "illness", "travel", "recovery", "other")
SOURCE = "manual"
ENTITY = "training_period"


def run_period(args, parser: argparse.ArgumentParser) -> int:
    action = args.period_action

    if action == "add":
        return _add(args, parser)
    if action == "list":
        return _list(args, parser)
    if action == "remove":
        return _remove(args, parser)
    if action == "history":
        return _history(args, parser)

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
    new = {
        "kind": args.kind,
        "label": args.label or "",
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
        "notes": args.notes or "",
    }

    connection = open_database(args.database)
    try:
        old = _row(connection, period_id)
        writer = TrainingWriter(connection)
        writer.upsert_training_period(
            period_id,
            kind=args.kind,
            start_date=new["start_date"],
            end_date=new["end_date"],
            label=new["label"],
            notes=new["notes"],
        )
        record_changes(
            writer,
            entity_kind=ENTITY,
            entity_id=period_id,
            old=old,
            new=new,
            source=SOURCE,
            note=args.note or "period add",
        )
        if args.dry_run:
            connection.rollback()
            print(f"Dry run: period {period_id} not written.")
        else:
            connection.commit()
            print(f"period saved: {period_id}")
    finally:
        connection.close()

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
        try:
            period_id = resolve_period(connection, args.period)
        except SelectionError as exc:
            parser.error(str(exc))
        if not _row(connection, period_id):
            parser.error(f"no training period with id {period_id}")

        cursor = connection.execute(
            "UPDATE training_periods SET excluded_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ? "
            "AND excluded_at IS NULL",
            (period_id,),
        )
        if not cursor.rowcount:
            parser.error(f"no training period with id {period_id}")

        record_changes(
            TrainingWriter(connection),
            entity_kind=ENTITY,
            entity_id=period_id,
            old={"excluded_at": False},
            new={"excluded_at": True},
            source=SOURCE,
            note=args.note or "period remove",
        )
        if args.dry_run:
            connection.rollback()
            print(f"Dry run: period {period_id} not excluded.")
        else:
            connection.commit()
            print(f"period excluded: {period_id}")
    finally:
        connection.close()
    return 0


def _history(args, parser: argparse.ArgumentParser) -> int:
    connection = open_database(args.database)
    try:
        try:
            period_id = resolve_period(connection, args.period)
        except SelectionError as exc:
            parser.error(str(exc))
        entries = TrainingRepository(connection).edit_history(
            ENTITY, period_id
        )
    finally:
        connection.close()

    for line in history_lines(entries):
        print(line)
    return 0


def _row(connection, period_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT kind, label, start_date, end_date, notes "
        "FROM training_periods WHERE id = ? AND excluded_at IS NULL",
        (period_id,),
    ).fetchone()
    if row is None:
        return {}
    return {
        "kind": row["kind"],
        "label": row["label"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "notes": row["notes"],
    }
