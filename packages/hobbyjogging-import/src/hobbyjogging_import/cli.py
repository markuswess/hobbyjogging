"""Command-line interface for hobbyjogging imports."""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_core import default_database_path, open_database

from .config import (
    default_fit_dir,
    default_garmin_dir,
    resolve_fit_path,
)
from .fit import fit_file_to_dict, format_fit_file, parse_fit_file
from .fit_import import FitImportAction, FitImporter, FitImportSummary
from .garmin import GarminFetcher, GarminFetchSummary
from .intervals import EventSyncSummary, IntervalsImporter
from .ods import OdsError, read_sheets
from .parsers import build_parser
from .review_cli import run_review
from .sheet_import import SheetImporter, format_sheet_summary
from .sync import format_sync_summary, run_sync


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


def resolve_event_range(
    start: date | None,
    end: date | None,
    plan_days: int,
    today: date | None = None,
) -> tuple[date, date]:
    if plan_days < 0:
        raise ValueError("--plan-days must be zero or greater")

    today = today or date.today()
    start = start or today
    if end is None:
        end = max(start, today + timedelta(days=plan_days))
    if start > end:
        raise ValueError("--from must not be after --to")
    return start, end


def resolve_sync_range(
    days: int,
    since: date | None,
    today: date | None = None,
) -> tuple[date, date]:
    if days < 0:
        raise ValueError("--days must be zero or greater")

    today = today or date.today()
    start = since or today - timedelta(days=days)
    if start > today:
        raise ValueError("--since must not be after today")
    return start, today


def run_fit(args, parser: argparse.ArgumentParser) -> int:
    if args.inspect is not None:
        if args.paths:
            parser.error("--inspect accepts one file")
        return _run_fit_inspect(args, parser)

    if args.json:
        parser.error("--json requires --inspect")

    return _run_fit_import(args, parser)


def _run_fit_inspect(args, parser: argparse.ArgumentParser) -> int:
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


def _run_fit_import(args, parser: argparse.ArgumentParser) -> int:
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be greater than zero")

    if (
        args.start is not None
        and args.end is not None
        and args.start > args.end
    ):
        parser.error("--from must not be after --to")

    try:
        connection = open_database(args.database)
    except Exception as exc:
        raise SystemExit(f"could not open database: {exc}") from exc

    paths = args.paths or [default_fit_dir()]

    try:
        importer = FitImporter(connection)
        summary = importer.import_paths(
            paths,
            recursive=args.recursive,
            start=args.start,
            end=args.end,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        connection.close()

    _print_fit_summary(
        summary,
        args.database or default_database_path(),
        dry_run=args.dry_run,
    )
    return 0


def run_sheet(args, parser: argparse.ArgumentParser) -> int:
    if args.inspect is not None:
        return _run_sheet_inspect(args, parser)

    if not args.sheet_name:
        parser.error("--sheet is required (or use --inspect)")

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be greater than zero")

    if args.start is not None and args.end is not None and args.start > args.end:
        parser.error("--from must not be after --to")

    path = args.path or Path("data/laufen.ods")
    if not path.is_file():
        parser.error(f"ODS file not found: {path}")

    try:
        connection = open_database(args.database)
    except Exception as exc:
        raise SystemExit(f"could not open database: {exc}") from exc

    try:
        try:
            importer = SheetImporter(
                connection,
                timezone_name=args.timezone,
            )
            summary = importer.import_sheet(
                path,
                args.sheet_name,
                start=args.start,
                end=args.end,
                limit=args.limit,
                dry_run=args.dry_run,
            )
        except (ValueError, OdsError) as exc:
            raise SystemExit(str(exc)) from exc
    finally:
        connection.close()

    print(
        format_sheet_summary(
            summary,
            args.database or default_database_path(),
        )
    )
    return 0


def _run_sheet_inspect(args, parser: argparse.ArgumentParser) -> int:
    path = args.inspect
    if not path.is_file():
        parser.error(f"ODS file not found: {path}")

    try:
        sheets = read_sheets(path)
    except OdsError as exc:
        raise SystemExit(str(exc)) from exc

    for sheet in sheets:
        print(f"{sheet.name}: {len(sheet.rows)} rows")
        for row in sheet.rows[:3]:
            values = [str(value) for value in row if value is not None]
            if values:
                print("  " + " | ".join(values))

    return 0


def run_garmin(args, parser: argparse.ArgumentParser) -> int:
    if args.garmin_action != "fetch":
        parser.error(f"unknown garmin command: {args.garmin_action}")

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be greater than zero")

    try:
        start, end = resolve_range(args.days, args.start, args.end)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        connection = open_database(args.database)
    except Exception as exc:
        raise SystemExit(f"could not open database: {exc}") from exc

    fit_dir = args.fit_dir or default_garmin_dir()

    try:
        try:
            fetcher = GarminFetcher(connection, fit_dir=fit_dir)
            summary = fetcher.fetch(
                start,
                end,
                dry_run=args.dry_run,
                limit=args.limit,
                force=args.force,
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    finally:
        connection.close()

    _print_garmin_summary(
        summary,
        args.database or default_database_path(),
        dry_run=args.dry_run,
    )
    return 0


def _print_garmin_summary(
    summary: GarminFetchSummary,
    database_path,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        print(
            "Garmin fetch dry run: "
            f"{summary.listed} listed, "
            f"{summary.new} new, "
            f"{summary.skipped_known} known, "
            f"{summary.skipped_limit} over limit, "
            f"{summary.failed} failed"
        )
        if summary.new_ids:
            print(f"New: {', '.join(summary.new_ids)}")
    else:
        print(
            "Garmin fetch complete: "
            f"{summary.listed} listed, "
            f"{summary.new} new, "
            f"{summary.downloaded} downloaded, "
            f"{summary.skipped_known} known, "
            f"{summary.skipped_limit} over limit, "
            f"{summary.failed} failed"
        )

    print(f"Archive: {summary.fit_dir}")

    for error in summary.errors:
        print(f"Error: {error}")

    if not dry_run:
        print(f"Import run: {summary.run_id}")
        print(f"Database: {database_path}")


def run_events(args, parser: argparse.ArgumentParser) -> int:
    if args.events_action != "sync":
        parser.error(f"unknown events command: {args.events_action}")

    try:
        start, end = resolve_event_range(
            args.start,
            args.end,
            args.plan_days,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        connection = open_database(args.database)
    except Exception as exc:
        raise SystemExit(f"could not open database: {exc}") from exc

    try:
        try:
            importer = IntervalsImporter(connection)
            summary = importer.sync_events(
                start,
                end,
                dry_run=args.dry_run,
                plan_days=args.plan_days,
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    finally:
        connection.close()

    _print_events_summary(
        summary,
        args.database or default_database_path(),
        dry_run=args.dry_run,
    )
    return 0


def run_sync_command(args, parser: argparse.ArgumentParser) -> int:
    try:
        start, end = resolve_sync_range(args.days, args.since)
    except ValueError as exc:
        parser.error(str(exc))

    if args.plan_days < 0:
        parser.error("--plan-days must be zero or greater")

    plan_end = end + timedelta(days=args.plan_days)

    try:
        connection = open_database(args.database)
    except Exception as exc:
        raise SystemExit(f"could not open database: {exc}") from exc

    try:
        summary = run_sync(
            connection,
            start=start,
            end=end,
            plan_end=plan_end,
            include_garmin=not args.no_garmin,
            include_intervals=not args.no_intervals,
            include_fit=not args.no_fit,
            include_scan=not args.no_scan,
            full=args.full,
            fit_dir=default_fit_dir(),
        )
    finally:
        connection.close()

    print(format_sync_summary(summary))
    return 1 if summary.failures else 0


def _print_events_summary(
    summary: EventSyncSummary,
    database_path,
    *,
    dry_run: bool,
) -> None:
    label = "Events sync dry run" if dry_run else "Events sync complete"
    print(
        f"{label}: "
        f"{summary.fetched} fetched, "
        f"{summary.new} new, "
        f"{summary.updated} updated, "
        f"{summary.unchanged} unchanged, "
        f"{summary.removed} removed, "
        f"{summary.revived} revived, "
        f"{summary.skipped} skipped"
    )
    print(f"Range: {summary.start} .. {summary.end}")

    if not dry_run:
        print(f"Import run: {summary.run_id}")
        print(f"Database: {database_path}")


def _print_fit_summary(
    summary: FitImportSummary,
    database_path,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        for action in summary.actions:
            print(_format_fit_action(action))

        print(
            "FIT dry run: "
            f"{summary.files_seen} files seen, "
            f"{summary.files_imported} with activities, "
            f"{summary.activities_imported} activities would import "
            f"({summary.activities_matched} matched, "
            f"{summary.activities_created} created), "
            f"{summary.laps_imported} laps"
        )
    else:
        for action in summary.actions:
            if action.action == "ambiguous":
                print(_format_fit_action(action))

        print(
            "FIT import complete: "
            f"{summary.files_imported} files, "
            f"{summary.activities_imported} activities "
            f"({summary.activities_matched} matched, "
            f"{summary.activities_created} created), "
            f"{summary.laps_imported} laps"
        )

    print(f"Files skipped: {summary.files_skipped}")
    print(f"Activities skipped: {summary.activities_skipped}")
    print(f"VO2max: {summary.vo2max_imported} activities with a Garmin value")
    print(f"Review items recorded: {summary.review_recorded}")

    for error in summary.errors:
        print(f"Error: {error}")

    if not dry_run:
        print(f"Import run: {summary.run_id}")
        print(f"Database: {database_path}")


def _format_fit_action(action: FitImportAction) -> str:
    location = f"{action.path} [{action.session_index}]"

    if action.action == "ambiguous":
        candidates = ", ".join(
            f"{match.activity_id} ({match.match_method}, "
            f"{match.confidence:.3f})"
            for match in action.matches
        )
        return f"AMBIGUOUS {location} -> {candidates}"

    if action.action == "skip":
        return f"SKIP {location} ({action.match_method})"

    confidence = (
        f", {action.confidence:.3f}"
        if action.confidence is not None
        else ""
    )
    return (
        f"{action.action.upper()} {location} -> {action.activity_id} "
        f"({action.match_method}{confidence})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "fit":
        return run_fit(args, parser)

    if args.command == "sheet":
        return run_sheet(args, parser)

    if args.command == "garmin":
        return run_garmin(args, parser)

    if args.command == "events":
        return run_events(args, parser)

    if args.command == "sync":
        return run_sync_command(args, parser)

    if args.command == "review":
        return run_review(args, parser)

    if args.command != "intervals":
        parser.error(f"unknown command: {args.command}")

    if args.plan_days < 0:
        parser.error("--plan-days must be zero or greater")

    try:
        start, end = resolve_range(args.days, args.start, args.end)
    except ValueError as exc:
        parser.error(str(exc))

    plan_end = end
    if args.plan_days > 0:
        plan_end = max(
            end,
            date.today() + timedelta(days=args.plan_days),
        )

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
                plan_end=plan_end,
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
    print(f"Plan range: {start} .. {summary.plan_end}")
    if summary.activities_skipped:
        print(f"Activities skipped: {summary.activities_skipped}")
    if summary.events_removed:
        print(f"Events removed: {summary.events_removed}")
    if summary.events_revived:
        print(f"Events revived: {summary.events_revived}")

    print(f"Review items recorded: {summary.review_recorded}")

    for external_id, matches in summary.ambiguous_matches:
        candidates = ", ".join(
            f"{match.activity_id} ({match.match_method}, "
            f"{match.confidence:.3f})"
            for match in matches
        )
        print(f"Ambiguous match: {external_id} -> {candidates}")

    print(f"Import run: {summary.run_id}")
    print(f"Database: {database_path}")
    return 0
