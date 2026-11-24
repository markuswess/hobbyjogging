"""Argument parser construction for the hobbyjogging import CLI."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .causes import CAUSE_NAMES
from .config import default_fit_dir, default_garmin_dir
from .freshness import default_strava_dir
from .quality import REVIEW_CATEGORIES


def date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def _id_list(value: str) -> list[str]:
    ids = [item.strip() for item in value.split(",") if item.strip()]
    if not ids:
        raise argparse.ArgumentTypeError("expected at least one id")
    return ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hobbyjogging-import",
        description="Import training data into the canonical database.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser(
        "sync",
        help="incrementally sync every configured source",
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
        "--no-runalyze",
        action="store_true",
        help="skip the Runalyze enrichment and offline derivations",
    )
    sync.add_argument(
        "--no-strava",
        action="store_true",
        help="skip the newest unimported Strava export",
    )
    sync.add_argument(
        "--no-derive",
        action="store_true",
        help="skip the offline Runalyze gear/VO2max/races derivations",
    )
    sync.add_argument(
        "--no-scan",
        action="store_true",
        help="skip the quality review scan",
    )
    sync.add_argument(
        "--strava-dir",
        type=Path,
        help=(
            "directory holding export_*.zip "
            f"(default: {default_strava_dir()})"
        ),
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

    sources = subparsers.add_parser(
        "sources",
        help="show the effective source configuration",
    )
    sources.add_argument(
        "--config",
        type=Path,
        help="sources.toml path (default: HOBBYJOGGING_SOURCES or ./sources.toml)",
    )

    settings = subparsers.add_parser(
        "settings",
        help="render the import rules, policy and mapping as Markdown",
    )
    settings.add_argument(
        "--config",
        type=Path,
        help="sources.toml path (default: HOBBYJOGGING_SOURCES or ./sources.toml)",
    )

    strava = subparsers.add_parser(
        "strava",
        help="import a Strava bulk export (social text and gear)",
    )
    strava.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="Strava export ZIP or extracted directory",
    )
    strava.add_argument("--from", dest="start", type=date_arg)
    strava.add_argument("--to", dest="end", type=date_arg)
    strava.add_argument(
        "--distance-unit",
        choices=("km", "m"),
        default="km",
        help=(
            "unit of a single Distance column; the wide export's second "
            "column is always metres (default: km)"
        ),
    )
    strava.add_argument(
        "--date-zone",
        choices=("auto", "local", "utc"),
        default="auto",
        help=(
            "interpret Activity Date as local wall time or UTC; auto picks "
            "the one that matches more activities (default: auto)"
        ),
    )
    strava.add_argument(
        "--timezone",
        default="Europe/Vienna",
        help="timezone used when creating from a local-date export",
    )
    create_group = strava.add_mutually_exclusive_group()
    create_group.add_argument(
        "--create",
        action="store_true",
        help="create an activity when nothing matches",
    )
    create_group.add_argument(
        "--no-create",
        action="store_true",
        help="never create; use the configured review/ignore policy",
    )
    strava.add_argument("--dry-run", action="store_true")
    strava.add_argument("--database", type=Path)

    runalyze = subparsers.add_parser(
        "runalyze",
        help="read-only Runalyze API access",
    )
    runalyze_sub = runalyze.add_subparsers(
        dest="runalyze_action",
        required=True,
    )
    runalyze_inventory = runalyze_sub.add_parser(
        "inventory",
        help="report what the API exposes per endpoint, field and year",
    )
    runalyze_inventory.add_argument("--since", dest="start", type=date_arg)
    runalyze_inventory.add_argument("--to", dest="end", type=date_arg)
    runalyze_inventory.add_argument(
        "--limit",
        type=int,
        help="read at most this many activities",
    )
    runalyze_inventory.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="activities per API page (default: 100)",
    )
    runalyze_inventory.add_argument(
        "--base-url",
        help="override the API base URL (default: RUNALYZE_API_BASE_URL)",
    )
    runalyze_inventory.add_argument(
        "--dry-run",
        action="store_true",
        help="report only; the inventory never writes",
    )

    runalyze_enrich = runalyze_sub.add_parser(
        "enrich",
        help="fill blank descriptions and import tags for matched activities",
    )
    runalyze_enrich.add_argument("--since", dest="start", type=date_arg)
    runalyze_enrich.add_argument("--to", dest="end", type=date_arg)
    runalyze_enrich.add_argument(
        "--limit",
        type=int,
        help="enrich at most this many Runalyze activities",
    )
    runalyze_enrich.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="activities per API page (default: 100)",
    )
    runalyze_enrich.add_argument(
        "--base-url",
        help="override the API base URL (default: RUNALYZE_API_BASE_URL)",
    )
    runalyze_enrich.add_argument("--database", type=Path)
    runalyze_create = runalyze_enrich.add_mutually_exclusive_group()
    runalyze_create.add_argument(
        "--create",
        action="store_true",
        help="create an activity when no same-day candidate exists",
    )
    runalyze_create.add_argument(
        "--no-create",
        action="store_true",
        help="never create; use the configured review/ignore policy",
    )
    runalyze_enrich.add_argument(
        "--output",
        type=Path,
        help="write the unmatched/ambiguous rows as JSON",
    )
    runalyze_enrich.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )
    runalyze_enrich.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch details even when the stored copy is current",
    )
    runalyze_enrich.add_argument(
        "--refresh-before",
        metavar="TIMESTAMP",
        help=(
            "re-fetch every detail stored before this ISO timestamp; with "
            "--wait it sweeps across rate-limit windows until none remain"
        ),
    )
    runalyze_enrich.add_argument(
        "--wait",
        action="store_true",
        help=(
            "sleep across rate-limit windows and resume until the range "
            "is complete"
        ),
    )
    runalyze_enrich.add_argument(
        "--ids",
        type=_id_list,
        help=(
            "repair only these Runalyze activity ids (comma-separated), "
            "without reading the collection"
        ),
    )

    runalyze_gear = runalyze_sub.add_parser(
        "gear",
        help="resolve stored Runalyze gear into equipment and activity links",
    )
    runalyze_gear.add_argument("--since", dest="start", type=date_arg)
    runalyze_gear.add_argument("--to", dest="end", type=date_arg)
    runalyze_gear.add_argument(
        "--limit",
        type=int,
        help="process at most this many gear records",
    )
    runalyze_gear.add_argument("--database", type=Path)
    runalyze_gear.add_argument(
        "--output",
        type=Path,
        help="write the ambiguous gear resolutions as JSON",
    )
    runalyze_gear.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )

    runalyze_vo2max = runalyze_sub.add_parser(
        "vo2max",
        help="fill vo2max_runalyze from the stored activity payloads",
    )
    runalyze_vo2max.add_argument("--since", dest="start", type=date_arg)
    runalyze_vo2max.add_argument("--to", dest="end", type=date_arg)
    runalyze_vo2max.add_argument(
        "--limit",
        type=int,
        help="process at most this many stored payloads",
    )
    runalyze_vo2max.add_argument("--database", type=Path)
    runalyze_vo2max.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )

    runalyze_types = runalyze_sub.add_parser(
        "types",
        help="audit the stored Runalyze workout types and their mapping",
    )
    runalyze_types.add_argument("--database", type=Path)

    runalyze_races = runalyze_sub.add_parser(
        "races",
        help="import official race results from Runalyze",
    )
    runalyze_races.add_argument(
        "--limit",
        type=int,
        help="import at most this many race results",
    )
    runalyze_races.add_argument(
        "--base-url",
        help="override the API base URL (default: RUNALYZE_API_BASE_URL)",
    )
    runalyze_races.add_argument("--database", type=Path)
    runalyze_races.add_argument(
        "--output",
        type=Path,
        help="write the race results with no linked activity as JSON",
    )
    runalyze_races.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
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
    garmin_wellness = garmin_sub.add_parser(
        "wellness",
        help="import daily resting HR, HRV, sleep, steps and weight",
    )
    garmin_wellness.add_argument("--days", type=int, default=30)
    garmin_wellness.add_argument("--since", dest="start", type=date_arg)
    garmin_wellness.add_argument("--to", dest="end", type=date_arg)
    garmin_wellness.add_argument("--database", type=Path)

    threshold = subparsers.add_parser(
        "threshold",
        help="record manual max HR, LTHR and threshold pace",
    )
    threshold.add_argument("--database", type=Path)
    threshold_sub = threshold.add_subparsers(
        dest="threshold_action",
        required=True,
    )
    threshold_add = threshold_sub.add_parser(
        "add",
        help="save a dated threshold snapshot",
    )
    threshold_add.add_argument("--sport", default="run")
    threshold_add.add_argument(
        "--from",
        dest="effective_from",
        help=(
            "first day the snapshot applies (default: today; "
            "'first' = the earliest activity of the sport)"
        ),
    )
    threshold_add.add_argument("--max-hr", type=float)
    threshold_add.add_argument("--lthr", type=float)
    threshold_add.add_argument(
        "--threshold-pace",
        help="threshold pace as 4:30 (min/km) or 3.70mps",
    )
    threshold_list = threshold_sub.add_parser(
        "list",
        help="list stored threshold snapshots",
    )
    threshold_list.add_argument("--sport")
    threshold_list.add_argument("--limit", type=int)

    period = subparsers.add_parser(
        "period",
        help="record manual training periods (illness, travel, plan)",
    )
    period.add_argument("--database", type=Path)
    period_sub = period.add_subparsers(dest="period_action", required=True)
    period_add = period_sub.add_parser("add", help="create or update a period")
    period_add.add_argument(
        "--kind",
        required=True,
        choices=("season", "plan", "illness", "travel", "recovery", "other"),
    )
    period_add.add_argument("--start", required=True)
    period_add.add_argument("--end")
    period_add.add_argument("--label")
    period_add.add_argument("--notes")
    period_list = period_sub.add_parser("list", help="list stored periods")
    period_list.add_argument("--limit", type=int)
    period_remove = period_sub.add_parser(
        "remove",
        help="soft-exclude one period",
    )
    period_remove.add_argument("period")

    race_result = subparsers.add_parser(
        "race-result",
        help="record official race metadata by hand",
    )
    race_result.add_argument("--database", type=Path)
    race_result_sub = race_result.add_subparsers(
        dest="race_result_action",
        required=True,
    )
    race_result_add = race_result_sub.add_parser(
        "add",
        help="create or replace one activity's race result",
    )
    race_result_add.add_argument("activity")
    race_result_add.add_argument("--distance", help="10k, 10000, 21.1km")
    race_result_add.add_argument("--time", help="42:30 or 2:37:49")
    race_result_add.add_argument("--name")
    race_result_add.add_argument("--place", type=int)
    race_result_add.add_argument("--place-gender", type=int)
    race_result_add.add_argument("--place-ageclass", type=int)
    race_result_add.add_argument("--participants", type=int)
    race_result_add.add_argument("--participants-gender", type=int)
    race_result_add.add_argument("--participants-ageclass", type=int)
    race_result_add.add_argument(
        "--officially-measured",
        action="store_true",
        help="the course distance is certified",
    )
    race_result_add.add_argument("--priority", help="A, B, C or unknown")
    race_result_add.add_argument("--status", default="completed")
    race_result_add.add_argument("--notes")
    race_result_add.add_argument("--event-id")

    race_result_list = race_result_sub.add_parser(
        "list",
        help="list stored race results",
    )
    race_result_list.add_argument("--limit", type=int)

    race_result_remove = race_result_sub.add_parser(
        "remove",
        help="soft-exclude one activity's race result",
    )
    race_result_remove.add_argument("activity")

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
        "--prune",
        action="store_true",
        help=(
            "resolve open quality items whose rule no longer triggers "
            "(or whose activity is excluded)"
        ),
    )
    review_scan.add_argument(
        "--dry-run",
        action="store_true",
        help="report findings without recording or resolving them",
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
        choices=REVIEW_CATEGORIES,
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
        choices=REVIEW_CATEGORIES,
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
