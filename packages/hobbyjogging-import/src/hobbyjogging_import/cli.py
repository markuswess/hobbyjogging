"""Command-line interface for hobbyjogging imports."""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_core import default_database_path, open_database

from .config import default_fit_dir, resolve_fit_path
from .fit import fit_file_to_dict, format_fit_file, parse_fit_file
from .intervals import IntervalsImporter


def date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def resolve_range(
    days: int,
    start: date | None = None,
    end: date | None = None,
    today: date | None = None,
) -> tuple[date, date]:
    if days < 0:
        raise ValueError("--days must be zero or greater")

    today = today or date.today()

    if start is not None and end is not None:
        if start > end:
            raise ValueError("--from must not be after --to")
        return start, end

    if start is not None:
        if start > today:
            raise ValueError("--from must not be after today")
        return start, today

    if end is not None:
        return end - timedelta(days=days), end

    return today - timedelta(days=days), today


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hobbyjogging-import",
        description="Import training data into the canonical database.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    intervals = subparsers.add_parser(
        "intervals",
        help="import activities, wellness, events, and intervals from Intervals.icu",
    )
    intervals.add_argument("--days", type=int, default=30)
    intervals.add_argument("--from", dest="start", type=date_arg)
    intervals.add_argument("--to", dest="end", type=date_arg)
    intervals.add_argument("--database", type=Path)
    intervals.add_argument(
        "--no-intervals",
        action="store_true",
        help="skip per-activity interval downloads",
    )

    fit = subparsers.add_parser(
        "fit",
        help="inspect FIT files (import support will follow)",
    )
    fit.add_argument(
        "--inspect",
        type=Path,
        metavar="FILE",
        help=(
            "parse and print one FIT file without writing "
            f"(default directory: {default_fit_dir()})"
        ),
    )
    fit.add_argument(
        "--json",
        action="store_true",
        help="print the normalized FIT summary as JSON",
    )
    fit.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="FIT files or directories for future imports",
    )

    return parser


def run_fit_inspect(args, parser: argparse.ArgumentParser) -> int:
    if args.inspect is None:
        parser.error("FIT import is not implemented yet; use --inspect FILE")

    if args.paths:
        parser.error(
            "--inspect accepts one file; positional FIT imports are not "
            "implemented yet"
        )

    path = resolve_fit_path(args.inspect)

    if not path.is_file():
        parser.error(f"FIT file not found: {path}")

    try:
        summary = parse_fit_file(path)
    except Exception as exc:
        raise SystemExit(f"could not parse {path}: {exc}") from exc

    if args.json:
        print(
            json.dumps(
                fit_file_to_dict(summary),
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(format_fit_file(summary))

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "fit":
        return run_fit_inspect(args, parser)

    if args.command != "intervals":
        parser.error(f"unknown command: {args.command}")

    try:
        start, end = resolve_range(args.days, args.start, args.end)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        connection = open_database(args.database)
    except Exception as exc:
        raise SystemExit(f"could not open database: {exc}") from exc

    try:
        try:
            importer = IntervalsImporter(connection)
            summary = importer.import_range(
                start,
                end,
                include_intervals=not args.no_intervals,
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    finally:
        connection.close()

    database_path = args.database or default_database_path()
    print(
        "Intervals.icu import complete: "
        f"{summary.activities_imported} activities, "
        f"{summary.wellness_imported} wellness days, "
        f"{summary.events_imported} events, "
        f"{summary.intervals_imported} intervals"
    )
    if summary.activities_skipped:
        print(f"Activities skipped: {summary.activities_skipped}")
    print(f"Import run: {summary.run_id}")
    print(f"Database: {database_path}")
    return 0
