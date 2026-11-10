"""Argument parser construction for the hobbyjogging import CLI."""

import argparse
from datetime import date
from pathlib import Path

from .causes import CAUSE_NAMES
from .config import default_fit_dir, default_garmin_dir


def date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


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

    sheet = subparsers.add_parser(
        "sheet",
        help="import the historical training-log spreadsheet (.ods)",
    )
    sheet.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="ODS workbook (default: data/laufen.ods)",
    )
    sheet.add_argument(
        "--inspect",
        type=Path,
        metavar="FILE",
        help="list worksheets and headers without importing",
    )
    sheet.add_argument(
        "--sheet",
        dest="sheet_name",
        metavar="NAME",
        help="worksheet to import: Rohdaten, Alternativtraining, or Material",
    )
    sheet.add_argument("--timezone", default="Europe/Vienna")
    sheet.add_argument("--from", dest="start", type=date_arg)
    sheet.add_argument("--to", dest="end", type=date_arg)
    sheet.add_argument("--limit", type=int)
    sheet.add_argument("--dry-run", action="store_true")
    sheet.add_argument("--database", type=Path)

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

    review_prune = review_sub.add_parser(
        "prune",
        help="resolve field conflicts whose values now agree",
    )
    review_prune.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be resolved without writing",
    )

    review_causes = review_sub.add_parser(
        "causes",
        help="summarize field conflicts by cause",
    )
    review_causes.add_argument(
        "--status",
        choices=("open", "ignored", "resolved", "all"),
        default="open",
    )

    review_classify = review_sub.add_parser(
        "classify",
        help="annotate existing field conflicts with a cause",
    )
    review_classify.add_argument(
        "--activity",
        metavar="ACTIVITY_ID",
        help="classify only this activity's conflicts",
    )
    review_classify.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )

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
        help="mark a review item resolved (or bulk-resolve a conflict cause)",
    )
    review_resolve.add_argument("id", type=int, nargs="?")
    review_resolve.add_argument(
        "--activity",
        metavar="ACTIVITY_ID",
        help=(
            "resolve an ambiguous match by linking its source record "
            "to this canonical activity"
        ),
    )
    review_resolve.add_argument(
        "--cause",
        choices=CAUSE_NAMES,
        help=(
            "bulk-resolve every open conflict with this cause "
            "(only advisory causes are allowed)"
        ),
    )
    review_resolve.add_argument(
        "--dry-run",
        action="store_true",
        help="with --cause: report what would be resolved without writing",
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
        "--cause",
        choices=CAUSE_NAMES,
        help="triage only field conflicts with this cause",
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
    parser.add_argument(
        "--cause",
        choices=CAUSE_NAMES,
        help="field conflicts only: filter by classified cause",
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
