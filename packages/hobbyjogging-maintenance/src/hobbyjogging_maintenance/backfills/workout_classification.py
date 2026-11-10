"""Backfill workout methods/targets from the classifier and the sheet.

The reports classifier proposes a set from the activity name/RPE/intervals;
the historical sheet proposes a set from its ``Trainigstyp`` code. When both
propose and the sets disagree, the activity is left unclassified and listed as
a conflict for manual review. Semantic sheet tags (hills, strength, bad data)
are merged into the existing ``sheet`` tags.
"""

from __future__ import annotations

from collections import Counter

from hobbyjogging_core.sports import RUN_SPORTS

from ..context import TaskContext
from ..registry import task
from ..workouts import (
    classifier_proposal,
    conflict_from,
    disagrees,
    scoped_activities,
    sheet_proposal,
)

SOURCE = "backfill"
EASY_MAX_HR = 140

_COUNT_ORDER = (
    "activities",
    "classified",
    "classifier_only",
    "sheet_only",
    "both",
    "conflicts",
    "easy_default",
    "unclassified",
    "tagged_activities",
    "tags_added",
)


@task(
    "workout_classification_v1",
    kind="backfill",
    description=(
        "Classify activities with workout methods/targets from the reports "
        "classifier and the historical sheet."
    ),
)
def workout_classification(context: TaskContext) -> None:
    """Classify every in-scope activity, leaving disagreements unclassified."""
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    conflicts = []

    for activity in activities:
        context.count("activities")

        intervals = context.repository.activity_intervals(activity.id)
        classifier = classifier_proposal(activity, intervals)
        sheet, sheet_record_id, sheet_tags, sheet_code = sheet_proposal(
            context.connection,
            activity.id,
        )

        if sheet_tags:
            _merge_sheet_tags(
                context,
                activity.id,
                sheet_tags,
                sheet_record_id,
            )

        classifier_has = not classifier.empty
        sheet_has = sheet is not None and not sheet.empty

        if not classifier_has and not sheet_has:
            # A sheet run with no training code and a low average HR is an
            # easy run by default.
            if _is_easy_default(activity, sheet):
                context.count("easy_default")
                methods, targets = {"continuous"}, {"base"}
            else:
                context.count("unclassified")
                continue
        elif classifier_has and not sheet_has:
            context.count("classifier_only")
            methods, targets = classifier.methods, classifier.targets
        elif sheet_has and not classifier_has:
            context.count("sheet_only")
            methods, targets = sheet.methods, sheet.targets
        else:
            assert sheet is not None
            if disagrees(classifier, sheet):
                context.count("conflicts")
                conflicts.append(
                    conflict_from(activity, classifier, sheet, sheet_code)
                )
                continue
            context.count("both")
            methods = classifier.methods | sheet.methods
            targets = classifier.targets | sheet.targets

        context.count("classified")
        context.writer.replace_activity_workout_methods(
            activity.id,
            sorted(methods),
            source=SOURCE,
        )
        context.writer.replace_activity_workout_targets(
            activity.id,
            sorted(targets),
            source=SOURCE,
        )

    context.order_counts(_COUNT_ORDER)
    context.details["conflicts"] = [item.as_dict() for item in conflicts]
    if conflicts:
        context.note(
            f"{len(conflicts)} conflicts left unclassified; "
            "use --output PATH to write the review list"
        )

    context.output_lines.extend(_report(context, conflicts))
    context.write_output()


def _merge_sheet_tags(
    context: TaskContext,
    activity_id: str,
    tags: set[str],
    source_record_id: int | None,
) -> None:
    existing = {
        item["tag"]
        for item in context.connection.execute(
            """
            SELECT tag FROM activity_tags
            WHERE activity_id = ? AND source = 'sheet'
            """,
            (activity_id,),
        )
    }
    added = tags - existing
    if not added:
        return

    context.count("tagged_activities")
    context.count("tags_added", len(added))
    context.writer.replace_activity_tags(
        activity_id,
        sorted(existing | tags),
        source="sheet",
        source_record_id=source_record_id,
    )


def _is_easy_default(activity, sheet) -> bool:
    return (
        sheet is not None
        and activity.type in RUN_SPORTS
        and activity.avg_hr is not None
        and activity.avg_hr < EASY_MAX_HR
    )


def _report(context: TaskContext, conflicts) -> list[str]:
    counts: Counter[str] = Counter(context.counts)
    lines = [
        f"Activities scanned: {counts['activities']}",
        f"Classified: {counts['classified']}",
        f"  classifier only: {counts['classifier_only']}",
        f"  sheet only: {counts['sheet_only']}",
        f"  both agree: {counts['both']}",
        f"Conflicts: {counts['conflicts']}",
        (
            "Easy defaults (sheet, no code, HR < "
            f"{EASY_MAX_HR}): {counts['easy_default']}"
        ),
        f"Unclassified: {counts['unclassified']}",
        f"Tagged activities: {counts['tagged_activities']}",
        f"Tags added: {counts['tags_added']}",
    ]

    if not conflicts:
        return lines

    lines.extend(["", "Conflicts (left unclassified for review):"])
    for conflict in conflicts:
        lines.extend(conflict.lines())
    return lines
