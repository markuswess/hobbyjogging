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
from .review_cli import run_review
from .sync import format_sync_summary, run_sync


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hobbyjogging-import",
        description="Import training data into the canonical database.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser(
        "sync",
        help="incrementally sync Garmin, Intervals, FIT, and review",
    )
    sync.add_argument("--days", type=int, default=30)
    sync.add_argument("--since", type=date_arg)
    sync.add_argument("--plan-days", type=int, default=182)
    sync.add_argument(
        "--no-garmin",
        action="store_true",
        help="skip the Garmin fetch",
    )
    sync.add_argument(
        "--no-intervals",
        action="store_true",
        help="skip the Intervals.icu import",
    )
    sync.add_argument(
        "--no-fit",
        action="store_true",
        help="skip the FIT archive scan",
    )
    sync.add_argument(
        "--no-scan",
        action="store_true",
        help="skip the quality review scan",
    )
    sync.add_argument(
        "--full",
        action="store_true",
        help="re-import all FIT files instead of skipping known paths",
    )
    sync.add_argument("--database", type=Path)

    intervals = subparsers.add_parser(
        "intervals",
        help="import activities, wellness, events, and intervals from Intervals.icu",
    )
    intervals.add_argument("--days", type=int, default=30)
    intervals.add_argument("--from", dest="start", type=date_arg)
    intervals.add_argument("--to", dest="end", type=date_arg)
    intervals.add_argument(
        "--plan-days",
        type=int,
        default=182,
        help=(
            "fetch planned calendar events this many days ahead "
            "(default: 182; 0 disables)"
        ),
    )
    intervals.add_argument("--database", type=Path)
    intervals.add_argument(
        "--no-intervals",
        action="store_true",
        help="skip per-activity interval downloads",
    )

    events = subparsers.add_parser(
        "events",
        help="sync planned calendar events",
    )
    events_sub = events.add_subparsers(
        dest="events_action",
        required=True,
    )
    events_sync = events_sub.add_parser(
        "sync",
        help="reconcile planned events from Intervals.icu",
    )
    events_sync.add_argument("--from", dest="start", type=date_arg)
    events_sync.add_argument("--to", dest="end", type=date_arg)
    events_sync.add_argument("--plan-days", type=int, default=182)
    events_sync.add_argument("--database", type=Path)
    events_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="report changes without writing",
    )

    fit = subparsers.add_parser(
        "fit",
        help="inspect or import FIT files",
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
        help="print the normalized FIT summary as JSON with --inspect",
    )
    fit.add_argument(
        "--recursive",
        action="store_true",
        help="search directories recursively",
    )
    fit.add_argument("--from", dest="start", type=date_arg)
    fit.add_argument("--to", dest="end", type=date_arg)
    fit.add_argument("--database", type=Path)
    fit.add_argument(
        "--dry-run",
        action="store_true",
        help="report matches without writing to the database",
    )
    fit.add_argument(
        "--limit",
        type=int,
        help="maximum number of activity FIT files to process",
    )
    fit.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="FIT files or directories (default: configured FIT directory)",
    )

    garmin = subparsers.add_parser(
        "garmin",
        help="fetch original FIT files from Garmin Connect",
    )
    garmin_sub = garmin.add_subparsers(
        dest="garmin_action",
        required=True,
    )
    garmin_fetch = garmin_sub.add_parser(
        "fetch",
        help="download missing activity FITs into the archive",
    )
    garmin_fetch.add_argument("--days", type=int, default=30)
    garmin_fetch.add_argument("--since", dest="start", type=date_arg)
    garmin_fetch.add_argument("--to", dest="end", type=date_arg)
    garmin_fetch.add_argument("--database", type=Path)
    garmin_fetch.add_argument(
        "--fit-dir",
        type=Path,
        help=(
            "destination directory for fetched FITs "
            f"(default: {default_garmin_dir()})"
        ),
    )
    garmin_fetch.add_argument(
        "--limit",
        type=int,
        help="download at most this many new activities",
    )
    garmin_fetch.add_argument(
        "--force",
        action="store_true",
        help="re-download activity ids already in the manifest",
    )
    garmin_fetch.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be fetched without writing",
    )

    review = subparsers.add_parser(
        "review",
        help="list and resolve import conflicts and quality review items",
    )
    review.add_argument("--database", type=Path)
    review_sub = review.add_subparsers(
        dest="review_action",
        required=True,
    )

    review_list = review_sub.add_parser(
        "list",
        help="list review items",
    )
    _add_review_status_args(review_list)
    review_list.add_argument(
        "--limit",
        type=int,
        help="show at most this many items",
    )

    review_show = review_sub.add_parser(
        "show",
        help="show one review item in full detail",
    )
    review_show.add_argument("id", type=int)

    review_scan = review_sub.add_parser(
        "scan",
        help="run quality rules over existing activities and record items",
    )
    review_scan.add_argument(
        "--activity",
        metavar="ACTIVITY_ID",
        help="scan a single activity instead of the whole database",
    )
    review_scan.add_argument(
        "--dry-run",
        action="store_true",
        help="report findings without recording them",
    )

    review_resolve = review_sub.add_parser(
        "resolve",
        help="mark a review item resolved",
    )
    review_resolve.add_argument("id", type=int)
    review_resolve.add_argument(
        "--activity",
        metavar="ACTIVITY_ID",
        help=(
            "resolve an ambiguous match by linking its source record "
            "to this canonical activity"
        ),
    )
    review_resolve.add_argument("--note", default="")

    review_ignore = review_sub.add_parser(
        "ignore",
        help="mark a review item ignored (kept, never reopens)",
    )
    review_ignore.add_argument("id", type=int)
    review_ignore.add_argument("--note", default="")

    review_flag = review_sub.add_parser(
        "flag",
        help="manually flag an activity for review",
    )
    review_flag.add_argument("activity_id", metavar="ACTIVITY_ID")
    _add_review_flag_args(review_flag)
    review_flag.add_argument(
        "--note",
        help="why the activity is flagged (stored as the detail)",
    )

    review_exclude = review_sub.add_parser(
        "exclude",
        help=(
            "durably exclude (soft-delete) an activity: hidden from reports, "
            "skipped by reimports"
        ),
    )
    review_exclude.add_argument("activity", metavar="ACTIVITY_ID")
    review_exclude.add_argument(
        "--note",
        default="excluded",
        help="note stored on the resolved review items",
    )

    review_restore = review_sub.add_parser(
        "restore",
        help="undo an exclusion (review items stay resolved)",
    )
    review_restore.add_argument("activity", metavar="ACTIVITY_ID")

    review_edit = review_sub.add_parser(
        "edit",
        help="manually edit activity values (outranks all import sources)",
    )
    review_edit.add_argument("activity", metavar="ACTIVITY_ID")
    review_edit.add_argument(
        "--duration",
        help="new duration: 46:20, 1:02:03, or seconds",
    )
    review_edit.add_argument(
        "--distance",
        help="new distance: 8.2km, 8200m, or plain km",
    )
    review_edit.add_argument("--sport", help="new sport, e.g. trail_running")
    review_edit.add_argument(
        "--item",
        type=int,
        metavar="REVIEW_ITEM_ID",
        help="review item to resolve with this edit",
    )
    review_edit.add_argument(
        "--note",
        help="override the resolution note for the review item",
    )

    review_triage = review_sub.add_parser(
        "triage",
        help="interactively walk the open review queue",
    )
    review_triage.add_argument(
        "--limit",
        type=int,
        help="queue at most this many items",
    )
    review_triage.add_argument(
        "--category",
        choices=(
            "ambiguous_match",
            "field_conflict",
            "quality",
            "duplicate",
            "manual_flag",
        ),
    )
    review_triage.add_argument(
        "--severity",
        choices=("info", "warn", "error"),
    )
    review_triage.add_argument(
        "--activity",
        dest="activity_id",
        metavar="ACTIVITY_ID",
        help="triage only items for this activity",
    )

    return parser


def _add_review_status_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--status",
        choices=("open", "ignored", "resolved", "all"),
        default="open",
    )
    parser.add_argument(
        "--category",
        choices=(
            "ambiguous_match",
            "field_conflict",
            "quality",
            "duplicate",
            "manual_flag",
        ),
    )


def _add_review_flag_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--category",
        choices=("quality", "duplicate", "manual_flag"),
        default="manual_flag",
    )
    parser.add_argument(
        "--severity",
        choices=("info", "warn", "error"),
        default="warn",
    )


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
