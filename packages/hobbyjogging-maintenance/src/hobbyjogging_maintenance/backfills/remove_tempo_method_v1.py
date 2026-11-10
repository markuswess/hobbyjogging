"""Retire the ``tempo`` workout method.

A tempo run is a continuous run with a threshold target, so the method only
duplicated information the target already carries. Every activity that still
has ``tempo`` is rewritten to ``continuous`` as a manual decision; its targets
are left alone.

Events were never classified when the method was retired, so
``event_workout_methods`` needs no conversion.
"""

from __future__ import annotations

from ..context import TaskContext
from ..registry import task

_COUNT_ORDER = ("activities", "already_continuous", "skipped")


@task(
    "remove_tempo_method_v1",
    kind="backfill",
    description="Convert the retired tempo method to continuous.",
)
def remove_tempo_method(context: TaskContext) -> None:
    rows = context.connection.execute(
        """
        SELECT m.activity_id, a.excluded_at
        FROM activity_workout_methods m
        JOIN activities a ON a.id = m.activity_id
        WHERE m.method = 'tempo'
        GROUP BY m.activity_id
        ORDER BY m.activity_id
        """
    ).fetchall()

    if not rows:
        context.note("No activities used the tempo method.")
        return

    for row in rows:
        activity_id = row["activity_id"]

        if row["excluded_at"]:
            context.count("skipped")
            continue

        methods = {
            item["method"]
            for item in context.connection.execute(
                """
                SELECT method FROM activity_workout_methods
                WHERE activity_id = ?
                """,
                (activity_id,),
            )
        }
        methods.discard("tempo")
        if "continuous" in methods:
            context.count("already_continuous")
        methods.add("continuous")

        context.writer.set_manual_activity_workout_methods(
            activity_id,
            sorted(methods),
        )
        context.count("activities")

    context.order_counts(_COUNT_ORDER)

    if context.counts.get("skipped"):
        context.note(
            f"{context.counts['skipped']} excluded activities left untouched"
        )
