"""Classifier and sheet proposals shared by the classification tasks.

The reports classifier proposes a set from the activity name/RPE/intervals;
the historical sheet proposes a set from its ``Trainigstyp`` code. Both the
backfill and the review-queue sync use these helpers, so they cannot drift.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from hobbyjogging_core.classify import classify
from hobbyjogging_core.model import Activity
from hobbyjogging_core.sports import RUN_SPORTS
from hobbyjogging_core.workouts import (
    classification_for_category,
    classification_for_sheet_code,
)
from hobbyjogging_import.quality import (
    WORKOUT_CLASSIFICATION,
    review_fingerprint,
)

from .context import TaskContext

# A sheet run with no training code and a low average HR is an easy run.
EASY_MAX_HR = 140


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

    def lines(self) -> list[str]:
        return [
            f"  {self.local_date} {self.name or '-'} [{self.activity_id}]",
            f"    classifier: methods={sorted(self.classifier.methods)} "
            f"targets={sorted(self.classifier.targets)}",
            f"    sheet ({self.sheet_code or '-'}): "
            f"methods={sorted(self.sheet.methods)} "
            f"targets={sorted(self.sheet.targets)}",
        ]


def classifier_proposal(
    activity: Activity,
    intervals: list | None = None,
) -> Proposal:
    """Propose sets from the heuristic classifier, never from stored values."""
    category = classify(activity, intervals, use_stored=False)
    methods, targets = classification_for_category(
        category.group,
        category.kind,
        category.detail,
    )
    return Proposal(methods, targets)


def sheet_proposal(
    connection: sqlite3.Connection,
    activity_id: str,
) -> tuple[Proposal | None, int | None, set[str], str]:
    """Return the sheet's proposal, its record id, its tags, and its code."""
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


def disagrees(classifier: Proposal, sheet: Proposal) -> bool:
    """Whether the two proposals disagree on a set both of them fill."""
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


def conflict_from(
    activity: Activity,
    classifier: Proposal,
    sheet: Proposal,
    sheet_code: str,
) -> Conflict:
    """Build the review payload for one disagreement."""
    return Conflict(
        activity_id=activity.id,
        local_date=activity.date.isoformat(),
        name=activity.name or "",
        classifier=classifier,
        sheet=sheet,
        sheet_code=sheet_code,
    )


def fingerprint(conflict: Conflict) -> str:
    """Stable identity for a disagreement; a changed proposal is a new item."""
    return review_fingerprint(
        [
            WORKOUT_CLASSIFICATION,
            conflict.activity_id,
            sorted(conflict.classifier.methods),
            sorted(conflict.classifier.targets),
            conflict.sheet_code,
            sorted(conflict.sheet.methods),
            sorted(conflict.sheet.targets),
        ]
    )


def is_easy_default(activity: Activity, sheet: Proposal | None) -> bool:
    """Whether an unproposed sheet run is an easy run by default."""
    return (
        sheet is not None
        and activity.type in RUN_SPORTS
        and activity.avg_hr is not None
        and activity.avg_hr < EASY_MAX_HR
    )


def scoped_activities(context: TaskContext) -> list[Activity]:
    """Return the in-scope activities in canonical order."""
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
