"""Keep workout-classification review items in sync with the proposals.

The backfill writes the agreed classifications and leaves disagreements
unclassified. This recompute turns those disagreements into review items so
they can be resolved with `hobbyjogging-import review triage`, and closes
items that no longer apply. A classified activity is left alone unless a
mapped tag or an explicit description claims a method or target its stored set
does not contain; that evidence becomes a choice in triage, never an automatic
write.
"""

from __future__ import annotations

import sqlite3

from hobbyjogging_import.quality import WORKOUT_CLASSIFICATION

from ..context import TaskContext
from ..registry import task
from ..workouts import (
    Proposal,
    classifier_proposal,
    conflict_from,
    disagrees,
    evidence_conflict_from,
    evidence_conflicts,
    evidence_proposal,
    fingerprint,
    scoped_activities,
    sheet_proposal,
)

_COUNT_ORDER = ("opened", "unchanged", "superseded", "resolved")


@task(
    "workout_classification_queue",
    kind="recompute",
    description=(
        "Record classifier/sheet disagreements and tag/comment evidence "
        "conflicts as workout-classification review items and close the ones "
        "that no longer apply."
    ),
)
def workout_classification_queue(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    open_items = _open_items(context.connection)

    for activity in activities:
        items = open_items.pop(activity.id, [])
        evidence, evidence_source = evidence_proposal(activity)

        # A classified activity needs a decision only when the tag or
        # description claims a method or target the stored set lacks.
        if activity.quality is not None:
            stored = Proposal(
                set(activity.workout_methods),
                set(activity.workout_targets),
            )
            if (
                evidence is None
                or evidence.empty
                or not evidence_conflicts(stored, evidence)
            ):
                _resolve(context, items, "classified")
                continue

            intervals = context.repository.activity_intervals(activity.id)
            classifier = classifier_proposal(activity, intervals)
            sheet, _, _, code = sheet_proposal(
                context.connection,
                activity.id,
            )
            conflict = evidence_conflict_from(
                activity,
                evidence=evidence,
                evidence_source=evidence_source,
                stored=stored,
                classifier=classifier,
                sheet=sheet,
                sheet_code=code,
            )
            wanted = fingerprint(conflict)
            _supersede(context, items, wanted)

            _, created = context.writer.record_review_item(
                category=WORKOUT_CLASSIFICATION,
                detail=(
                    f"{evidence_source} evidence vs stored classification"
                ),
                context=conflict.as_dict(),
                severity="info",
                fingerprint=wanted,
                activity_id=activity.id,
            )
            context.count("opened" if created else "unchanged")
            continue

        intervals = context.repository.activity_intervals(activity.id)
        classifier = classifier_proposal(activity, intervals)
        sheet, _, _, code = sheet_proposal(
            context.connection,
            activity.id,
        )

        if (
            classifier.empty
            or sheet is None
            or sheet.empty
            or not disagrees(classifier, sheet)
        ):
            _resolve(context, items, "no longer a conflict")
            continue

        conflict = conflict_from(activity, classifier, sheet, code)
        wanted = fingerprint(conflict)
        _supersede(context, items, wanted)

        _, created = context.writer.record_review_item(
            category=WORKOUT_CLASSIFICATION,
            detail=f"classifier vs sheet ({code or '-'}) disagree",
            context=conflict.as_dict(),
            severity="info",
            fingerprint=wanted,
            activity_id=activity.id,
        )
        context.count("opened" if created else "unchanged")

    context.order_counts(_COUNT_ORDER)


def _open_items(
    connection: sqlite3.Connection,
) -> dict[str, list[sqlite3.Row]]:
    items: dict[str, list[sqlite3.Row]] = {}
    for item in connection.execute(
        """
        SELECT id, activity_id, fingerprint
        FROM review_items
        WHERE category = ? AND status = 'open'
        """,
        (WORKOUT_CLASSIFICATION,),
    ):
        items.setdefault(item["activity_id"], []).append(item)
    return items


def _supersede(
    context: TaskContext,
    items: list[sqlite3.Row],
    wanted: str,
) -> None:
    for item in items:
        if item["fingerprint"] != wanted:
            context.writer.set_review_status(
                item["id"],
                "resolved",
                note="superseded: proposals changed",
            )
            context.count("superseded")


def _resolve(context: TaskContext, items: list[sqlite3.Row], note: str) -> None:
    for item in items:
        context.writer.set_review_status(item["id"], "resolved", note=note)
        context.count("resolved")
