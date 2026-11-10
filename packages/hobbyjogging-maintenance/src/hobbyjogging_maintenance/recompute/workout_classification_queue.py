"""Keep workout-classification review items in sync with the proposals.

The backfill writes the agreed classifications and leaves disagreements
unclassified. This recompute turns those disagreements into review items so
they can be resolved with `hobbyjogging-import review triage`, and closes
items that no longer apply.
"""

from __future__ import annotations

import sqlite3

from hobbyjogging_import.quality import WORKOUT_CLASSIFICATION

from ..context import TaskContext
from ..registry import task
from ..workouts import (
    classifier_proposal,
    conflict_from,
    disagrees,
    fingerprint,
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

        # A classified activity needs no decision: close anything stale.
        if activity.quality is not None:
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

        for item in items:
            if item["fingerprint"] != wanted:
                context.writer.set_review_status(
                    item["id"],
                    "resolved",
                    note="superseded: proposals changed",
                )
                context.count("superseded")

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


def _resolve(context: TaskContext, items: list[sqlite3.Row], note: str) -> None:
    for item in items:
        context.writer.set_review_status(item["id"], "resolved", note=note)
        context.count("resolved")
