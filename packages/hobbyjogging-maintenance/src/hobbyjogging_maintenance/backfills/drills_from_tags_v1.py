"""Add the drills method to sessions tagged LTT or Lauftechnik.

The live tags describe running drills, not a threshold session. This backfill
adds ``drills`` to the non-manual workout sets of the tagged activities,
leaving the existing run method and target in place. A manual set stays for
the human.
"""

from __future__ import annotations

from hobbyjogging_import.tag_lexicon import normalize_tag

from ..context import TaskContext
from ..registry import task
from ..workouts import scoped_activities

DRILL_TAGS = frozenset(
    {"ltt", "lauftechnik", "drill", "drills", "lauf-abc", "lauf abc"}
)

_COUNT_ORDER = (
    "activities",
    "tagged",
    "added",
    "unchanged",
    "skipped_manual",
    "no_set",
)


@task(
    "drills_from_tags_v1",
    kind="backfill",
    description=(
        "Add the drills method to the non-manual workout sets of LTT and "
        "Lauftechnik activities."
    ),
)
def drills_from_tags(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    for activity in activities:
        context.count("activities")
        if not any(
            normalize_tag(tag) in DRILL_TAGS for tag in activity.tags
        ):
            continue

        context.count("tagged")
        rows = _workout_rows(context, activity.id)
        if not rows:
            context.count("no_set")
            continue
        if any(row["is_manual"] for row in rows):
            context.count("skipped_manual")
            continue

        existing = {
            row["method"]
            for row in context.connection.execute(
                """
                SELECT method FROM activity_workout_methods
                WHERE activity_id = ?
                """,
                (activity.id,),
            )
        }
        if "drills" in existing:
            context.count("unchanged")
            continue

        tag_methods = {
            row["method"]
            for row in context.connection.execute(
                """
                SELECT method FROM activity_workout_methods
                WHERE activity_id = ? AND source = 'tag' AND is_manual = 0
                """,
                (activity.id,),
            )
        }
        context.writer.replace_activity_workout_methods(
            activity.id,
            sorted(tag_methods | {"drills"}),
            source="tag",
        )
        context.count("added")

    context.order_counts(_COUNT_ORDER)


def _workout_rows(context: TaskContext, activity_id: str):
    return context.connection.execute(
        """
        SELECT is_manual FROM activity_workout_methods
        WHERE activity_id = ?
        UNION ALL
        SELECT is_manual FROM activity_workout_targets
        WHERE activity_id = ?
        """,
        (activity_id, activity_id),
    ).fetchall()
