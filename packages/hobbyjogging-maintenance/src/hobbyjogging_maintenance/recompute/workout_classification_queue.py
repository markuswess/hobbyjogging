"""Keep workout-classification review items in sync with the proposals.

The backfill writes the agreed classifications and leaves disagreements
unclassified. This recompute turns those disagreements into review items so
they can be resolved with `hobbyjogging-import review triage`, and closes
items that no longer apply. A classified activity is left alone: tag evidence
refines a classifier projection in ``workout_sets_current``, and a sheet or
manual set wins over a tag or comment, so no evidence item is opened here.
"""

from __future__ import annotations

import sqlite3

from hobbyjogging_core.workouts import ADDITIVE_METHODS
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
    is_projection,
    scoped_activities,
    sheet_proposal,
)

_COUNT_ORDER = ("opened", "unchanged", "superseded", "resolved")


@task(
    "workout_classification_queue",
    kind="recompute",
    description=(
        "Record classifier/sheet disagreements as workout-classification "
        "review items and close the ones that no longer apply."
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

        # A classified activity takes a review item only for a structured
        # comment on a derived projection. Tag evidence refines in place, and
        # a sheet/manual set wins over every comment.
        if activity.quality is not None:
            evidence, evidence_source = evidence_proposal(
                activity,
                context.connection,
            )
            stored = Proposal(
                set(activity.workout_methods),
                set(activity.workout_targets),
            )
            specific = (
                evidence is not None
                and bool(
                    (evidence.methods - ADDITIVE_METHODS - {"other"})
                    or (evidence.targets - {"other"})
                )
            )
            if (
                evidence_source == "comment"
                and specific
                and is_projection(context.connection, activity.id)
                and evidence_conflicts(stored, evidence)
            ):
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
                    detail="comment evidence vs stored classification",
                    context=conflict.as_dict(),
                    severity="info",
                    fingerprint=wanted,
                    activity_id=activity.id,
                )
                context.count("opened" if created else "unchanged")
                continue

            _resolve(context, items, "classified")
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
