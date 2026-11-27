"""Link equipment named by a mapped activity tag.

A trailer tag is evidence that the trailer was used, on a run or a ride. The
mapping lives beside the tag lexicon; this recompute resolves the normalized
equipment name and links it as secondary when the activity already has gear,
primary only when it has none. It never displaces a manual or existing primary
and an existing link of the same item is left alone.
"""

from __future__ import annotations

import sqlite3

from hobbyjogging_import.tag_lexicon import (
    equipment_names_for,
    normalize_tag,
    unmapped_equipment_tags,
)

from ..context import TaskContext
from ..registry import task
from ..workouts import scoped_activities

SOURCE = "tag"

_COUNT_ORDER = (
    "activities",
    "tagged",
    "linked",
    "already",
    "missing_equipment",
    "ambiguous_equipment",
)


@task(
    "equipment_from_tags_current",
    kind="recompute",
    description=(
        "Link mapped equipment tags (Thule) to their activities, secondary "
        "when other gear exists and primary only when the activity has none."
    ),
)
def equipment_from_tags_current(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    equipment = _equipment_by_name(context.connection)
    all_tags: set[str] = set()

    for activity in activities:
        context.count("activities")
        all_tags.update(activity.tags)
        names = equipment_names_for(activity.tags)
        if not names:
            continue

        context.count("tagged")
        links = _links(context.connection, activity.id)
        existing = {row["equipment_id"] for row in links}
        has_links = bool(links)

        for name in names:
            candidates = equipment.get(_normalize_name(name), [])
            if not candidates:
                context.count("missing_equipment")
                continue
            if len(candidates) > 1:
                context.count("ambiguous_equipment")
                continue

            equipment_id = candidates[0]
            if equipment_id in existing:
                context.count("already")
                continue

            written = context.writer.link_activity_equipment(
                activity.id,
                equipment_id,
                source=SOURCE,
                role="secondary" if has_links else "primary",
            )
            if written:
                context.count("linked")
                existing.add(equipment_id)
                has_links = True
            else:
                context.count("already")

    context.order_counts(_COUNT_ORDER)

    unmapped = unmapped_equipment_tags(all_tags)
    if unmapped:
        context.note(
            "Unmapped gear-like tags: " + ", ".join(unmapped)
        )


def _links(connection: sqlite3.Connection, activity_id: str):
    return connection.execute(
        """
        SELECT equipment_id, role, source, is_manual
        FROM activity_equipment
        WHERE activity_id = ?
        """,
        (activity_id,),
    ).fetchall()


def _equipment_by_name(
    connection: sqlite3.Connection,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in connection.execute(
        "SELECT id, name FROM equipment ORDER BY name, id"
    ):
        result.setdefault(_normalize_name(row["name"]), []).append(row["id"])
    return result


def _normalize_name(value: object) -> str:
    return normalize_tag(value)
