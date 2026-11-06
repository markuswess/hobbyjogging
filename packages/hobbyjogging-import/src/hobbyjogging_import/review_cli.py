"""Review workflow CLI: list, inspect, and resolve import review items."""

import json

from hobbyjogging_core import TrainingWriter, open_database
from .links import garmin_url, intervals_url
from .quality import MANUAL_FLAG, record_manual_flag
from .scan import scan_quality


def run_review(args, parser) -> int:
    action = args.review_action

    try:
        connection = open_database(args.database)
    except Exception as exc:
        raise SystemExit(f"could not open database: {exc}") from exc

    try:
        writer = TrainingWriter(connection)

        if action == "exclude":
            return _run_exclude(args, writer, parser)
        if action == "restore":
            return _run_restore(args, writer, parser)
        if action == "edit":
            return _run_edit(args, writer, parser)
        if action == "triage":
            return _run_triage(args, writer, parser)
        if action == "list":
            return _run_list(args, writer)
        if action == "show":
            return _run_show(args, writer, parser)
        if action == "resolve":
            return _run_resolve(args, writer, parser)
        if action == "ignore":
            return _run_ignore(args, writer, parser)
        if action == "flag":
            return _run_flag(args, writer, parser)
        if action == "scan":
            return _run_scan(args, writer, parser)

        parser.error(f"unknown review action: {action}")
    finally:
        connection.close()


def _run_scan(args, writer: TrainingWriter, parser) -> int:
    """Apply the canonical quality rule set to existing activities."""

    def on_finding(row, finding) -> None:
        print(f"finding {finding.rule}: {row['id']} — {finding.detail}")

    try:
        summary = scan_quality(
            writer,
            activity_id=args.activity,
            dry_run=args.dry_run,
            on_finding=on_finding,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.dry_run:
        print(f"Scan dry run: {summary.findings} finding(s)")
    else:
        print(
            f"Scan: {summary.findings} finding(s), "
            f"{summary.recorded} new review item(s)"
        )

    return 0


def _run_list(args, writer: TrainingWriter) -> int:
    items = writer.review_items(
        status=args.status,
        category=args.category,
    )

    if args.limit is not None:
        items = items[: args.limit]

    if not items:
        print(f"No {args.status} review items.")
        return 0

    for item in items:
        print(_format_summary_line(item))

    print(f"\n{len(items)} {args.status} review item(s)")
    return 0


def _run_show(args, writer: TrainingWriter, parser) -> int:
    item = writer.review_item(args.id)

    if item is None:
        parser.error(f"unknown review item: {args.id}")

    print(_format_summary_line(item))
    print(f"status: {item['status']}")
    print(f"activity: {item['activity_id'] or '-'}")
    print(f"source record: {item['source_record_id'] or '-'}")
    print(f"import run: {item['import_run_id'] or '-'}")
    print(f"fingerprint: {item['fingerprint'][:16]}...")
    print(f"reported: {item['reported_at']}")
    if item["resolved_at"]:
        print(f"resolved: {item['resolved_at']} ({item['resolved_note']})")

    links = [
        ("Intervals", intervals_url(writer.connection, item)),
        ("Garmin", garmin_url(writer.connection, item)),
    ]
    available = [(label, url) for label, url in links if url]
    if available:
        print("\nlinks:")
        for label, url in available:
            print(f"  {label}: {url}")

    print("\ndetail:")
    print(f"  {item['detail']}")

    context = json.loads(item["context_json"] or "{}")
    if context:
        print("context:")
        print(json.dumps(context, indent=2, ensure_ascii=False))

    return 0


def _run_resolve(args, writer: TrainingWriter, parser) -> int:
    if writer.review_item(args.id) is None:
        parser.error(f"unknown review item: {args.id}")

    if args.activity is not None:
        try:
            writer.resolve_review_match(args.id, args.activity, note=args.note)
            connection = writer.connection
            connection.commit()
            print(f"Resolved #{args.id}: linked to {args.activity}")
            print(
                "Re-run the matching importer over the record "
                "(e.g. hobbyjogging-import fit <file>) to apply the record's "
                "field values to the chosen activity."
            )
        except ValueError as exc:
            parser.error(str(exc))
    else:
        writer.set_review_status(args.id, "resolved", note=args.note)
        writer.connection.commit()
        print(f"Resolved #{args.id}")

    return 0


def _run_ignore(args, writer: TrainingWriter, parser) -> int:
    if writer.review_item(args.id) is None:
        parser.error(f"unknown review item: {args.id}")

    writer.set_review_status(args.id, "ignored", note=args.note)
    writer.connection.commit()
    print(f"Ignored #{args.id}")
    return 0


def _run_flag(args, writer: TrainingWriter, parser) -> int:
    detail = args.note or "manually flagged"
    created = record_manual_flag(
        writer,
        activity_id=args.activity_id,
        category=args.category,
        detail=detail,
        severity=args.severity,
    )
    writer.connection.commit()

    if created:
        print(f"Flagged {args.category}: {args.activity_id}")
    else:
        print(f"Already flagged ({args.category}): {args.activity_id}")

    return 0


def _run_exclude(args, writer: TrainingWriter, parser) -> int:
    if not writer.connection.execute(
        "SELECT 1 FROM activities WHERE id = ?", (args.activity,)
    ).fetchone():
        parser.error(f"unknown activity: {args.activity}")

    resolved = writer.exclude_activity(args.activity, resolve_note=args.note)
    writer.connection.commit()
    print(f"Excluded {args.activity}")
    print(f"Review items resolved: {resolved}")
    return 0


def _run_edit(args, writer: TrainingWriter, parser) -> int:
    """Apply one or more manual field edits and re-run quality rules."""
    from .editing import apply_manual_edit
    from .values import parse_distance_m, parse_duration_s, parse_sport

    row = writer.connection.execute(
        "SELECT 1 FROM activities WHERE id = ?",
        (args.activity,),
    ).fetchone()
    if row is None:
        parser.error(f"unknown activity: {args.activity}")

    planned = []
    for text, field, parse in (
        (args.duration, "duration_s", parse_duration_s),
        (args.distance, "distance_m", parse_distance_m),
        (args.sport, "sport", parse_sport),
    ):
        if text is None:
            continue
        try:
            value = parse(text)
        except ValueError as exc:
            parser.error(str(exc))
        planned.append((field, value))

    if not planned:
        parser.error(
            "nothing to edit: use --duration, --distance, or --sport"
        )

    if args.item is not None and writer.review_item(args.item) is None:
        parser.error(f"unknown review item: {args.item}")

    try:
        for field, value in planned:
            try:
                application = apply_manual_edit(
                    writer,
                    activity_id=args.activity,
                    field=field,
                    value=value,
                    resolve_item_id=args.item,
                    note=args.note,
                )
            except ValueError as exc:
                writer.connection.rollback()
                parser.error(str(exc))

            print(application.describe())
            if args.item is not None:
                print(f"Resolved #{args.item}")
            if application.okay:
                print("quality: ok")
            else:
                print(
                    "quality: still flagged — "
                    f"{application.describe_findings()}"
                )
    finally:
        writer.connection.commit()

    return 0


def _run_restore(args, writer: TrainingWriter, parser) -> int:
    if not writer.connection.execute(
        "SELECT 1 FROM activities WHERE id = ?", (args.activity,)
    ).fetchone():
        parser.error(f"unknown activity: {args.activity}")

    writer.restore_activity(args.activity)
    writer.connection.commit()
    print(f"Restored {args.activity} (review items stay resolved)")
    return 0


def _run_triage(args, writer: TrainingWriter, parser) -> int:
    """Interactive walk over open review items."""
    from .triage import TriageRunner

    runner = TriageRunner(writer)
    runner.run(
        limit=args.limit,
        category=args.category,
        severity=args.severity,
        activity_id=args.activity_id,
    )
    return 0


def _format_summary_line(item) -> str:
    record = ""
    if item["record_source"]:
        external = item["external_id"] or ""
        record = f" [{item['record_source']} {external[:32]}]"

    excluded = " [excluded]" if item["activity_excluded_at"] else ""

    if item["local_date"]:
        name = item["activity_name"] or item["sport"] or ""
        return (
            f"#{item['id']} {item['severity']:<4} "
            f"{item['category']}/{item['status']}  "
            f"{item['local_date']}{record}  {name}{excluded}  "
            f"({item['detail'][:64]})"
        )

    return (
        f"#{item['id']} {item['severity']:<4} "
        f"{item['category']}/{item['status']}  "
        f"{record}{excluded}  ({item['detail'][:64]})"
    )
