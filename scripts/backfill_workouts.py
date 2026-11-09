#!/usr/bin/env python3
"""One-off backfill of workout methods/targets from the classifier and sheet.

The reports classifier proposes a set from the activity name/RPE/intervals;
the historical sheet proposes a set from its ``Trainigstyp`` code. When both
propose and the sets disagree, the activity is listed as a conflict and its
classification is left for review. Semantic sheet tags (hills, strength,
bad data) are merged into the existing ``sheet`` tags.

Run with ``--dry-run`` first.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date

from hobbyjogging_core import (
    TrainingRepository,
    TrainingWriter,
    open_database,
)
from hobbyjogging_core.workouts import (
    classification_for_category,
    classification_for_sheet_code,
)
from hobbyjogging_report.classify import classify


@dataclass
class Proposal:
    methods: set[str]
    targets: set[str]


@dataclass
class Conflict:
    activity_id: str
    local_date: str
    name: str
    classifier: Proposal
    sheet: Proposal


def _sheet_proposal(connection, activity_id: str) -> tuple[Proposal | None, int | None, set[str], str]:
    row = connection.execute(
        """
        SELECT sr.id, sr.payload_json
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE als.activity_id = ?
          AND sr.source = 'sheet'
          AND sr.record_type = 'activity'
        ORDER BY sr.id
        LIMIT 1
        """,
        (activity_id,),
    ).fetchone()

    if row is None:
        return None, None, set(), ""

    try:
        values = json.loads(row["payload_json"] or "{}").get("values") or {}
    except (TypeError, ValueError):
        values = {}

    code = str(values.get("Trainigstyp") or "")
    methods, targets, tags = classification_for_sheet_code(code)
    return Proposal(methods, targets), row["id"], tags, code


def _activity_ids(connection, args) -> list[str]:
    if args.activity:
        return [args.activity]

    start = args.start
    end = args.end
    if start is None or end is None:
        row = connection.execute(
            "SELECT MIN(local_date), MAX(local_date) FROM activities "
            "WHERE excluded_at IS NULL"
        ).fetchone()
        if row[0] is None:
            return []
        start = start or date.fromisoformat(row[0])
        end = end or date.fromisoformat(row[1])

    rows = connection.execute(
        """
        SELECT id FROM activities
        WHERE local_date BETWEEN ? AND ?
          AND excluded_at IS NULL
        ORDER BY local_date, id
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return [row["id"] for row in rows]


def run(args) -> int:
    connection = open_database(args.database)
    repository = TrainingRepository(connection)
    writer = TrainingWriter(connection)

    activity_ids = _activity_ids(connection, args)
    if args.limit is not None:
        activity_ids = activity_ids[: args.limit]

    counts: Counter[str] = Counter()
    conflicts: list[Conflict] = []
    conflict_details = []

    for activity_id in activity_ids:
        row = connection.execute(
            "SELECT local_date, name, sport FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        if row is None:
            continue

        activity = None
        for candidate in repository.activities(
            date.fromisoformat(row["local_date"]),
            date.fromisoformat(row["local_date"]),
        ):
            if candidate.id == activity_id:
                activity = candidate
                break
        if activity is None:
            continue

        intervals = repository.activity_intervals(activity_id)
        category = classify(activity, intervals)
        c_methods, c_targets = classification_for_category(
            category.group,
            category.kind,
            category.detail,
        )
        classifier = Proposal(c_methods, c_targets)

        sheet, sheet_record_id, sheet_tags, sheet_code = _sheet_proposal(
            connection, activity_id
        )

        counts["activities"] += 1

        # Merge semantic sheet tags without removing existing sheet tags.
        if sheet_tags:
            existing = {
                item["tag"]
                for item in connection.execute(
                    "SELECT tag FROM activity_tags "
                    "WHERE activity_id = ? AND source = 'sheet'",
                    (activity_id,),
                )
            }
            merged = existing | sheet_tags
            added = merged - existing
            if added:
                counts["tagged_activities"] += 1
                counts["tags_added"] += len(added)
                if not args.dry_run:
                    writer.replace_activity_tags(
                        activity_id,
                        sorted(merged),
                        source="sheet",
                        source_record_id=sheet_record_id,
                    )

        classifier_has = bool(classifier.methods or classifier.targets)
        sheet_has = bool(
            sheet is not None and (sheet.methods or sheet.targets)
        )

        if not classifier_has and not sheet_has:
            counts["unclassified"] += 1
            continue

        if classifier_has and not sheet_has:
            counts["classifier_only"] += 1
            methods, targets = classifier.methods, classifier.targets
        elif sheet_has and not classifier_has:
            counts["sheet_only"] += 1
            methods, targets = sheet.methods, sheet.targets
        else:
            methods_conflict = (
                bool(classifier.methods)
                and bool(sheet.methods)
                and classifier.methods != sheet.methods
            )
            targets_conflict = (
                bool(classifier.targets)
                and bool(sheet.targets)
                and classifier.targets != sheet.targets
            )
            if methods_conflict or targets_conflict:
                counts["conflicts"] += 1
                conflicts.append(
                    Conflict(
                        activity_id=activity_id,
                        local_date=row["local_date"],
                        name=row["name"] or "",
                        classifier=classifier,
                        sheet=sheet,
                    )
                )
                if len(conflict_details) < args.max_conflicts:
                    conflict_details.append(
                        (
                            row["local_date"],
                            row["name"] or "",
                            activity_id,
                            sheet_code,
                            sorted(classifier.methods),
                            sorted(classifier.targets),
                            sorted(sheet.methods),
                            sorted(sheet.targets),
                        )
                    )
                continue
            counts["both"] += 1
            methods = classifier.methods | sheet.methods
            targets = classifier.targets | sheet.targets

        counts["classified"] += 1
        if not args.dry_run:
            writer.replace_activity_workout_methods(
                activity_id,
                sorted(methods),
                source="backfill",
            )
            writer.replace_activity_workout_targets(
                activity_id,
                sorted(targets),
                source="backfill",
            )

    if not args.dry_run:
        connection.commit()

    print(f"Activities scanned: {counts['activities']}")
    print(f"Classified: {counts['classified']}")
    print(f"  classifier only: {counts['classifier_only']}")
    print(f"  sheet only: {counts['sheet_only']}")
    print(f"  both agree: {counts['both']}")
    print(f"Conflicts: {counts['conflicts']}")
    print(f"Unclassified: {counts['unclassified']}")
    print(f"Tagged activities: {counts['tagged_activities']}")
    print(f"Tags added: {counts['tags_added']}")

    if conflict_details:
        print("\nConflicts (left unclassified for review):")
        for (
            local_date,
            name,
            activity_id,
            code,
            c_methods,
            c_targets,
            s_methods,
            s_targets,
        ) in conflict_details:
            print(f"  {local_date} {name or '-'} [{activity_id}]")
            print(f"    classifier: methods={c_methods} targets={c_targets}")
            print(f"    sheet ({code or '-'}): methods={s_methods} targets={s_targets}")

    if args.dry_run:
        print("\nDry run: no changes written.")
    else:
        print("\nBackfill written.")

    connection.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="database path (default: env/default)")
    parser.add_argument(
        "--from", dest="start", type=date.fromisoformat, help="first local date"
    )
    parser.add_argument(
        "--to", dest="end", type=date.fromisoformat, help="last local date"
    )
    parser.add_argument("--activity", help="backfill one activity id")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report proposals and conflicts without writing",
    )
    parser.add_argument(
        "--max-conflicts",
        type=int,
        default=50,
        help="print at most this many conflict details (default 50)",
    )
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
