"""Review workflow CLI: list, inspect, and resolve import review items."""

import json

from hobbyjogging_core import TrainingWriter, open_database
from .quality import MANUAL_FLAG, record_manual_flag


def run_review(args, parser) -> int:
    action = args.review_action

    try:
        connection = open_database(args.database)
    except Exception as exc:
        raise SystemExit(f"could not open database: {exc}") from exc

    try:
        writer = TrainingWriter(connection)

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
    from .quality import record_quality_findings

    if args.activity is not None:
        rows = writer.connection.execute(
            """
            SELECT id, sport, duration_s, elapsed_s, distance_m
            FROM activities WHERE id = ?
            """,
            (args.activity,),
        ).fetchall()

        if not rows:
            parser.error(f"unknown activity: {args.activity}")
    else:
        rows = writer.connection.execute(
            """
            SELECT id, sport, duration_s, elapsed_s, distance_m
            FROM activities
            ORDER BY local_date, id
            """
        ).fetchall()

    total_findings = 0
    recorded = 0

    for row in rows:
        from .quality import quality_findings

        findings = quality_findings(
            sport=row["sport"] or "",
            duration_s=row["duration_s"] or 0,
            elapsed_s=row["elapsed_s"] or 0,
            distance_m=row["distance_m"] or 0,
        )
        if not findings:
            continue

        total_findings += len(findings)

        for finding in findings:
            print(f"finding {finding.rule}: {row['id']} — {finding.detail}")

        if args.dry_run:
            continue

        recorded += record_quality_findings(
            writer,
            activity_id=row["id"],
            source_record_id=None,
            import_run_id=None,
            sport=row["sport"] or "",
            duration_s=row["duration_s"] or 0,
            elapsed_s=row["elapsed_s"] or 0,
            distance_m=row["distance_m"] or 0,
        )

    writer.connection.commit()

    if args.dry_run:
        print(f"Scan dry run: {total_findings} finding(s)")
    else:
        print(f"Scan: {total_findings} finding(s), {recorded} new review item(s)")

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


def _format_summary_line(item) -> str:
    record = ""
    if item["record_source"]:
        external = item["external_id"] or ""
        record = f" [{item['record_source']} {external[:32]}]"

    if item["local_date"]:
        name = item["activity_name"] or item["sport"] or ""
        return (
            f"#{item['id']} {item['severity']:<4} "
            f"{item['category']}/{item['status']}  "
            f"{item['local_date']}{record}  {name}  "
            f"({item['detail'][:64]})"
        )

    return (
        f"#{item['id']} {item['severity']:<4} "
        f"{item['category']}/{item['status']}  "
        f"{record}  ({item['detail'][:64]})"
    )
