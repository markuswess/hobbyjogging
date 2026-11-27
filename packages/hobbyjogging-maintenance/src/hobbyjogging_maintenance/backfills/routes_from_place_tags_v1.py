"""Create and link routes from geographic activity tags.

The modern tags `Wienerberg`, `kanal`, `Prater` and their aliases are place
evidence. Each canonical place becomes one source-scoped route
(`runalyze:tag:<slug>`) and the activity links it with ``source='tag'``. An
activity that already has a route link is left alone, so a manual or sheet
route wins and a re-run is a no-op.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata

from hobbyjogging_import.tag_lexicon import place_names_for

from ..context import TaskContext
from ..registry import task
from ..workouts import scoped_activities

SOURCE = "tag"

_COUNT_ORDER = ("activities", "tagged", "routes_created", "linked", "already")


@task(
    "routes_from_place_tags_v1",
    kind="backfill",
    description=(
        "Create source-scoped routes from geographic tags and link them with "
        "source='tag'; existing route links win."
    ),
)
def routes_from_place_tags(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    for activity in activities:
        context.count("activities")
        names = place_names_for(activity.tags)
        if not names:
            continue

        context.count("tagged")
        if _has_route(context.connection, activity.id):
            context.count("already")
            continue

        route_ids = []
        for name in names:
            route_id = _route_id(name)
            if context.writer.upsert_route(
                route_id,
                name=name,
                source=SOURCE,
            ):
                context.count("routes_created")
            route_ids.append(route_id)

        context.count(
            "linked",
            context.writer.replace_activity_routes(
                activity.id,
                route_ids,
                source=SOURCE,
            ),
        )

    context.order_counts(_COUNT_ORDER)


def _has_route(connection: sqlite3.Connection, activity_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM activity_routes WHERE activity_id = ? LIMIT 1",
        (activity_id,),
    ).fetchone()
    return row is not None


def _route_id(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return f"runalyze:tag:{slug or 'place'}"
