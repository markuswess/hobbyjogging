"""Command-line interface for maintenance tasks."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from hobbyjogging_core import (
    SCHEMA_VERSION,
    default_database_path,
    open_database,
)

from .context import Scope
from .registry import KINDS, Task, all_tasks, get_task
from .runner import TaskRun, run_task
from .store import applied_ids, recent_runs


def date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hobbyjogging-maintenance",
        description=(
            "Apply schema migrations and run registered data maintenance "
            "tasks."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    listing = subparsers.add_parser("list", help="list registered tasks")
    listing.add_argument("--kind", choices=KINDS)
    listing.add_argument("--database", type=Path)

    status = subparsers.add_parser(
        "status",
        help="show the schema version, applied backfills, and recent runs",
    )
    status.add_argument("--runs", type=int, default=10)
    status.add_argument("--database", type=Path)

    run = subparsers.add_parser(
        "run",
        help="run one task or every pending backfill",
    )
    run.add_argument("task", nargs="?", help="task id")
    run.add_argument(
        "--all",
        action="store_true",
        help="run every backfill that has not been applied yet",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="run and roll back, reporting what would change",
    )
    run.add_argument(
        "--force",
        action="store_true",
        help="run a task that is already applied",
    )
    run.add_argument("--from", dest="start", type=date_arg)
    run.add_argument("--to", dest="end", type=date_arg)
    run.add_argument(
        "--entity",
        help="restrict the task to one activity or event id",
    )
    run.add_argument("--limit", type=int)
    run.add_argument(
        "--output",
        type=Path,
        help="write the task's detailed findings (e.g. conflicts) here",
    )
    run.add_argument("--database", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        return _list(args)
    if args.command == "status":
        return _status(args)
    return _run(args, parser)


def _open(path: Path | None):
    try:
        return open_database(path)
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean exit
        raise SystemExit(f"could not open database: {exc}") from exc


def _list(args) -> int:
    connection = _open(args.database)
    try:
        applied = applied_ids(connection)
    finally:
        connection.close()

    tasks = [
        item
        for item in all_tasks()
        if args.kind is None or item.kind == args.kind
    ]
    if not tasks:
        print("No tasks registered.")
        return 0

    width = max(len(item.id) for item in tasks)
    for item in tasks:
        print(
            f"{item.id:<{width}}  {item.kind:<9}  "
            f"{_state(item, applied):<22}  {item.description}"
        )
    return 0


def _state(task: Task, applied: dict) -> str:
    if not task.applied_once:
        return "always runs"
    row = applied.get(task.id)
    if row is None:
        return "pending"
    return f"applied {row['applied_at'][:10]}"


def _status(args) -> int:
    connection = _open(args.database)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        applied = applied_ids(connection)
        runs = recent_runs(connection, args.runs)
    finally:
        connection.close()

    print(f"Schema version: {version} (supported: {SCHEMA_VERSION})")

    print(f"Applied backfills: {len(applied)}")
    for task_id, row in applied.items():
        print(f"  {task_id}  {row['applied_at']}")

    pending = [
        item
        for item in all_tasks()
        if item.applied_once and item.id not in applied
    ]
    if pending:
        print("Pending backfills:")
        for item in pending:
            print(f"  {item.id}")

    if not runs:
        print("No maintenance runs yet.")
        return 0

    print("Recent runs:")
    for row in runs:
        mode = "dry-run" if row["dry_run"] else "write"
        print(
            f"  {row['started_at']}  {row['task']}  {row['kind']}  "
            f"{mode}  {row['status']}"
        )
    return 0


def _run(args, parser: argparse.ArgumentParser) -> int:
    if args.all and args.task:
        parser.error("give a task id or --all, not both")
    if not args.all and not args.task:
        parser.error("give a task id or --all")
    if args.all and args.output is not None:
        parser.error("--output only applies to a single task")

    if args.all:
        tasks = [item for item in all_tasks() if item.applied_once]
    else:
        try:
            tasks = [get_task(args.task)]
        except KeyError as exc:
            parser.error(str(exc).strip('"'))

    scope = Scope(
        start=args.start,
        end=args.end,
        entity_id=args.entity,
        limit=args.limit,
    )

    connection = _open(args.database)
    results: list[TaskRun] = []
    try:
        for item in tasks:
            result = run_task(
                connection,
                item,
                scope=scope,
                dry_run=args.dry_run,
                force=args.force,
                output=args.output,
            )
            _print_run(result)
            results.append(result)
            if not result.ok:
                break
    finally:
        connection.close()

    print(f"Database: {args.database or default_database_path()}")
    return 0 if all(result.ok for result in results) else 1


def _print_run(result: TaskRun) -> None:
    print(f"{result.task.id} ({result.task.kind})")

    if result.status == "skipped":
        print("  already applied; use --force to run it again")
        return

    for name, value in result.counts.items():
        print(f"  {_label(name)}: {value}")
    for note in result.notes:
        print(f"  {note}")
    if result.output is not None:
        print(f"  report: {result.output}")
    if result.error is not None:
        print(f"  error: {result.error}")

    if result.dry_run:
        print("Dry run: transaction rolled back, no changes written.")
    elif result.status == "ok":
        print("Applied.")


def _label(name: str) -> str:
    return name.replace("_", " ").capitalize()


if __name__ == "__main__":
    raise SystemExit(main())
