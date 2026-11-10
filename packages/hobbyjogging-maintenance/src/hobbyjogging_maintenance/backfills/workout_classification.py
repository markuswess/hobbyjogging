"""Backfill workout methods/targets from the classifier and the sheet.

The reports classifier proposes a set from the activity name/RPE/intervals;
the historical sheet proposes a set from its ``Trainigstyp`` code. When both
propose and the sets disagree, the activity is left unclassified and listed as
a conflict for manual review. Semantic sheet tags (hills, strength, bad data)
are merged into the existing ``sheet`` tags.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from hobbyjogging_core.model import Activity
from hobbyjogging_core.sports import RUN_SPORTS
from hobbyjogging_core.workouts import (
    classification_for_category,
    classification_for_sheet_code,
)
from hobbyjogging_report.classify import classify

from ..context import TaskContext
from ..registry import task

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


@dataclass
class Proposal:
    """One source's proposed method/target sets."""

    methods: set[str] = field(default_factory=set)
    targets: set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not self.methods and not self.targets


@dataclass
class Conflict:
    """A classifier/sheet disagreement left for manual review."""

    activity_id: str
    local_date: str
    name: str
    classifier: Proposal
    sheet: Proposal
    sheet_code: str

    def as_dict(self) -> dict[str, object]:
        return {
            "activity_id": self.activity_id,
            "local_date": self.local_date,
            "name": self.name,
            "classifier_methods": sorted(self.classifier.methods),
            "classifier_targets": sorted(self.classifier.targets),
            "sheet_code": self.sheet_code,
            "sheet_methods": sorted(self.sheet.methods),
            "sheet_targets": sorted(self.sheet.targets),
        }


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
    activities = _activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    conflicts: list[Conflict] = []

    for activity in activities:
        context.count("activities")

        intervals = context.repository.activity_intervals(activity.id)
        category = classify(activity, intervals)
        classifier = Proposal(
            *classification_for_category(
                category.group,
                category.kind,
                category.detail,
            )
        )

        sheet, sheet_record_id, sheet_tags, sheet_code = _sheet_proposal(
            context,
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
            if _disagrees(classifier, sheet):
                context.count("conflicts")
                conflicts.append(
                    Conflict(
                        activity_id=activity.id,
                        local_date=activity.date.isoformat(),
                        name=activity.name or "",
                        classifier=classifier,
                        sheet=sheet,
                        sheet_code=sheet_code,
                    )
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


def _activities(context: TaskContext) -> list[Activity]:
    start, end = _date_bounds(context)
    if start is None or end is None:
        return []

    activities = context.repository.activities(start, end)
    if context.scope.entity_id is not None:
        activities = [
            activity
            for activity in activities
            if activity.id == context.scope.entity_id
        ]
    if context.scope.limit is not None:
        activities = activities[: context.scope.limit]
    return activities


def _date_bounds(context: TaskContext) -> tuple[date | None, date | None]:
    scope = context.scope

    if scope.entity_id is not None:
        row = context.connection.execute(
            """
            SELECT local_date FROM activities
            WHERE id = ? AND excluded_at IS NULL
            """,
            (scope.entity_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown or excluded activity: {scope.entity_id}")
        day = date.fromisoformat(row["local_date"])
        return day, day

    start, end = scope.start, scope.end
    if start is None or end is None:
        row = context.connection.execute(
            """
            SELECT MIN(local_date), MAX(local_date) FROM activities
            WHERE excluded_at IS NULL
            """
        ).fetchone()
        if row[0] is None:
            return None, None
        start = start or date.fromisoformat(row[0])
        end = end or date.fromisoformat(row[1])

    return start, end


def _sheet_proposal(
    context: TaskContext,
    activity_id: str,
) -> tuple[Proposal | None, int | None, set[str], str]:
    row = context.connection.execute(
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


def _is_easy_default(activity: Activity, sheet: Proposal | None) -> bool:
    return (
        sheet is not None
        and activity.type in RUN_SPORTS
        and activity.avg_hr is not None
        and activity.avg_hr < EASY_MAX_HR
    )


def _disagrees(classifier: Proposal, sheet: Proposal) -> bool:
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
    return methods_conflict or targets_conflict


def _report(context: TaskContext, conflicts: list[Conflict]) -> list[str]:
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
        lines.append(
            f"  {conflict.local_date} {conflict.name or '-'} "
            f"[{conflict.activity_id}]"
        )
        lines.append(
            f"    classifier: methods={sorted(conflict.classifier.methods)} "
            f"targets={sorted(conflict.classifier.targets)}"
        )
        lines.append(
            f"    sheet ({conflict.sheet_code or '-'}): "
            f"methods={sorted(conflict.sheet.methods)} "
            f"targets={sorted(conflict.sheet.targets)}"
        )
    return lines
