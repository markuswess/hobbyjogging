"""Keep duplicate-session review items in sync with the detected pairs.

The pair rule lives in :mod:`hobbyjogging_import.duplicates`; this recompute
turns every pair into one non-idempotent ``duplicate`` item (fingerprint over
the sorted ids), links the likely weaker copy, and closes items whose pair no
longer matches or whose linked activity was excluded. It never merges or
excludes anything: the human decides.
"""

from __future__ import annotations

import sqlite3

from hobbyjogging_import.duplicates import (
    DuplicatePair,
    find_duplicates,
    preferred_activity,
)
from hobbyjogging_import.quality import DUPLICATE, review_fingerprint

from ..context import TaskContext
from ..registry import task
from ..workouts import scoped_activities

_COUNT_ORDER = ("activities", "pairs", "opened", "unchanged", "resolved")


@task(
    "duplicate_candidates_current",
    kind="recompute",
    description=(
        "Open duplicate review items for same-session activity pairs and "
        "close the ones that no longer apply."
    ),
)
def duplicate_candidates_current(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    context.count("activities", len(activities))
    sources = _source_sets(context.connection)
    pairs = find_duplicates(activities)

    wanted: dict[str, str] = {}
    for pair in pairs:
        context.count("pairs")
        fingerprint = _fingerprint(pair)
        linked = preferred_activity(pair, sources)
        wanted[fingerprint] = linked.id
        _, created = context.writer.record_review_item(
            category=DUPLICATE,
            detail=pair.detail(),
            context=pair.as_dict(),
            severity="warn",
            fingerprint=fingerprint,
            activity_id=linked.id,
        )
        context.count("opened" if created else "unchanged")

    _resolve_stale(
        context,
        wanted=wanted,
        activity_ids={activity.id for activity in activities},
    )
    context.order_counts(_COUNT_ORDER)


def _fingerprint(pair: DuplicatePair) -> str:
    return review_fingerprint([DUPLICATE, *pair.ids])


def _source_sets(
    connection: sqlite3.Connection,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for row in connection.execute(
        """
        SELECT als.activity_id, sr.source
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        JOIN activities a ON a.id = als.activity_id
        WHERE a.excluded_at IS NULL
        """
    ):
        result.setdefault(row["activity_id"], set()).add(row["source"])
    return result


def _resolve_stale(
    context: TaskContext,
    *,
    wanted: dict[str, str],
    activity_ids: set[str],
) -> None:
    for item in context.writer.review_items(category=DUPLICATE, status="open"):
        if item["activity_id"] not in activity_ids:
            continue
        linked = wanted.get(item["fingerprint"])
        if linked is None:
            context.writer.set_review_status(
                item["id"],
                "resolved",
                note="no longer a duplicate",
            )
            context.count("resolved")
            continue
        if linked != item["activity_id"]:
            context.writer.set_review_status(
                item["id"],
                "resolved",
                note="superseded: linked activity changed",
            )
            context.count("resolved")
