"""Link planned race events to the activities that ran them.

The classifier only reads the activity name, so a past planned race whose
activity is named after the town (``Linz Marathon`` vs ``Linz Running``) stays
a long run or an interval session. This recompute matches each race event to
an activity on the same date and sport with a distance within 5%, then makes
the activity carry the ``race`` method under its own non-manual source.

Manual links and manual workout sets always win: an event with a manual link
is left alone, and an activity with manual methods never gets the derived
``race`` row. Intervals stores only the event date, not a start time, so there
is nothing to rank candidates by; more than one candidate is therefore
ambiguous and opens an ``ambiguous_race`` review item instead of guessing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from ..context import TaskContext
from ..registry import task

SOURCE = "race_link"
CATEGORY = "ambiguous_race"
DISTANCE_TOLERANCE = 0.05
MIN_TOLERANCE_M = 100.0

_COUNT_ORDER = (
    "events",
    "linked",
    "unchanged",
    "ambiguous",
    "removed",
    "methods_added",
    "methods_removed",
    "skipped",
)


@dataclass(frozen=True)
class RaceEvent:
    id: str
    local_date: date
    sport: str
    name: str
    distance_m: float | None
    source_record_id: int | None


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    distance_m: float
    started_at_utc: str


@task(
    "race_links_current",
    kind="recompute",
    description="Link planned races to activities and derive the race method.",
)
def race_links_current(context: TaskContext) -> None:
    events = _race_events(context)
    activities = _activities_by_day(context)
    current = _current_links(context)

    _prune_stale_auto_links(context, events)

    for event in events:
        context.count("events")

        manual = [
            link for link in current.get(event.id, []) if link["is_manual"]
        ]
        if manual:
            desired: list[str] = []
            context.count("skipped")
        elif event.distance_m is None or event.distance_m <= 0:
            desired = []
            context.count("skipped")
        else:
            candidates = _candidates(
                event,
                activities.get((event.local_date, event.sport), []),
            )
            if len(candidates) == 1:
                desired = [candidates[0].id]
            elif len(candidates) > 1:
                desired = []
                if _record_ambiguous(context, event, candidates):
                    context.count("ambiguous")
                else:
                    context.count("unchanged")
            else:
                desired = []

        existing = sorted(
            link["activity_id"]
            for link in current.get(event.id, [])
            if not link["is_manual"]
        )
        if existing == desired:
            if desired:
                context.count("unchanged")
            continue

        context.writer.replace_event_activity_links(
            event.id,
            desired,
            match_method="auto",
            confidence=_confidence(event, desired, activities),
        )
        if desired:
            context.count("linked")
        else:
            context.count("removed")

    if not events:
        context.note("No race events in scope.")

    _reconcile_methods(context, events, _current_links(context))


def _prune_stale_auto_links(
    context: TaskContext,
    events: list[RaceEvent],
) -> None:
    """Drop automatic links whose event is no longer a race event."""
    keep = {event.id for event in events}
    where = ["l.is_manual = 0"]
    params: list[object] = []

    if context.scope.start is not None:
        where.append("e.local_date >= ?")
        params.append(context.scope.start.isoformat())
    if context.scope.end is not None:
        where.append("e.local_date <= ?")
        params.append(context.scope.end.isoformat())
    if context.scope.entity_id is not None:
        where.append("l.event_id = ?")
        params.append(context.scope.entity_id)

    rows = context.connection.execute(
        f"""
        SELECT DISTINCT l.event_id
        FROM event_activity_links l
        JOIN events e ON e.id = l.event_id
        WHERE {' AND '.join(where)}
        """,
        params,
    ).fetchall()

    for row in rows:
        if row["event_id"] not in keep:
            context.writer.replace_event_activity_links(row["event_id"], [])


def _race_events(context: TaskContext) -> list[RaceEvent]:
    where = [
        "e.excluded_at IS NULL",
        """
        EXISTS (
            SELECT 1 FROM event_workout_methods m
            WHERE m.event_id = e.id AND m.method = 'race'
        )
        """,
    ]
    params: list[object] = []

    if context.scope.start is not None:
        where.append("e.local_date >= ?")
        params.append(context.scope.start.isoformat())
    if context.scope.end is not None:
        where.append("e.local_date <= ?")
        params.append(context.scope.end.isoformat())
    if context.scope.entity_id is not None:
        where.append("e.id = ?")
        params.append(context.scope.entity_id)

    sql = f"""
        SELECT e.id, e.local_date, e.type, e.name, e.distance_m,
               e.source_record_id
        FROM events e
        WHERE {' AND '.join(where)}
        ORDER BY e.local_date, e.id
    """
    if context.scope.limit is not None:
        sql += " LIMIT ?"
        params.append(context.scope.limit)

    return [
        RaceEvent(
            id=row["id"],
            local_date=date.fromisoformat(row["local_date"]),
            sport=row["type"] or "",
            name=row["name"] or "",
            distance_m=row["distance_m"],
            source_record_id=row["source_record_id"],
        )
        for row in context.connection.execute(sql, params)
    ]


def _activities_by_day(
    context: TaskContext,
) -> dict[tuple[date, str], list[Candidate]]:
    rows = context.connection.execute(
        """
        SELECT id, local_date, sport, name, distance_m, started_at_utc
        FROM activities
        WHERE excluded_at IS NULL
        ORDER BY local_date, COALESCE(started_at_utc, local_date), id
        """
    ).fetchall()

    result: dict[tuple[date, str], list[Candidate]] = {}
    for row in rows:
        key = (date.fromisoformat(row["local_date"]), row["sport"])
        result.setdefault(key, []).append(
            Candidate(
                id=row["id"],
                name=row["name"] or "",
                distance_m=row["distance_m"] or 0.0,
                started_at_utc=row["started_at_utc"] or "",
            )
        )
    return result


def _candidates(
    event: RaceEvent,
    activities: list[Candidate],
) -> list[Candidate]:
    if event.distance_m is None:
        return []
    tolerance = max(event.distance_m * DISTANCE_TOLERANCE, MIN_TOLERANCE_M)
    return [
        activity
        for activity in activities
        if abs(activity.distance_m - event.distance_m) <= tolerance
    ]


def _confidence(
    event: RaceEvent,
    desired: list[str],
    activities: dict[tuple[date, str], list[Candidate]],
) -> float | None:
    if not desired or event.distance_m is None:
        return None
    for activity in activities.get((event.local_date, event.sport), []):
        if activity.id == desired[0]:
            diff = abs(activity.distance_m - event.distance_m)
            return round(max(0.0, 1.0 - diff / event.distance_m), 3)
    return None


def _record_ambiguous(
    context: TaskContext,
    event: RaceEvent,
    candidates: list[Candidate],
) -> bool:
    detail = (
        f"{event.name or 'Race'} on {event.local_date.isoformat()}: "
        f"{len(candidates)} activities within "
        f"{DISTANCE_TOLERANCE:.0%} of {event.distance_m:.0f} m"
    )
    _, created = context.writer.record_review_item(
        category=CATEGORY,
        detail=detail,
        fingerprint=f"race:{event.id}",
        source_record_id=event.source_record_id,
        context={
            "event_id": event.id,
            "event_date": event.local_date.isoformat(),
            "event_name": event.name,
            "distance_m": event.distance_m,
            "candidates": [
                {
                    "activity_id": candidate.id,
                    "name": candidate.name,
                    "distance_m": candidate.distance_m,
                    "started_at_utc": candidate.started_at_utc,
                }
                for candidate in candidates
            ],
        },
    )
    return created


def _current_links(
    context: TaskContext,
) -> dict[str, list[sqlite3.Row]]:
    result: dict[str, list[sqlite3.Row]] = {}
    for row in context.connection.execute(
        """
        SELECT l.event_id, l.activity_id, l.is_manual
        FROM event_activity_links l
        JOIN activities a ON a.id = l.activity_id
        WHERE a.excluded_at IS NULL
        ORDER BY l.event_id, l.activity_id
        """
    ):
        result.setdefault(row["event_id"], []).append(row)
    return result


def _reconcile_methods(
    context: TaskContext,
    events: list[RaceEvent],
    current: dict[str, list[sqlite3.Row]],
) -> None:
    linked: dict[str, int | None] = {}
    for event in events:
        for link in current.get(event.id, []):
            linked.setdefault(link["activity_id"], event.source_record_id)

    for activity_id, source_record_id in linked.items():
        methods = _methods(context.connection, activity_id)
        if any(row["is_manual"] for row in methods):
            if _drop_race_link(context, activity_id, methods):
                context.count("methods_removed")
            continue
        if any(row["method"] == "race" for row in methods):
            continue
        context.writer.replace_activity_workout_methods(
            activity_id,
            ["race"],
            source=SOURCE,
            source_record_id=source_record_id,
        )
        context.count("methods_added")

    for activity_id in _race_link_activities(context):
        if activity_id in linked:
            continue
        if _still_linked(context.connection, activity_id):
            continue
        methods = _methods(context.connection, activity_id)
        if _drop_race_link(context, activity_id, methods):
            context.count("methods_removed")

    context.order_counts(_COUNT_ORDER)


def _methods(
    connection: sqlite3.Connection,
    activity_id: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT method, source, is_manual FROM activity_workout_methods
        WHERE activity_id = ?
        """,
        (activity_id,),
    ).fetchall()


def _drop_race_link(
    context: TaskContext,
    activity_id: str,
    methods: list[sqlite3.Row],
) -> bool:
    present = any(
        row["method"] == "race" and row["source"] == SOURCE
        for row in methods
    )
    if not present:
        return False
    context.writer.replace_activity_workout_methods(
        activity_id,
        [],
        source=SOURCE,
    )
    return True


def _race_link_activities(context: TaskContext) -> list[str]:
    return [
        row["activity_id"]
        for row in context.connection.execute(
            """
            SELECT DISTINCT m.activity_id
            FROM activity_workout_methods m
            JOIN activities a ON a.id = m.activity_id
            WHERE m.source = ? AND m.method = 'race'
              AND a.excluded_at IS NULL
            ORDER BY m.activity_id
            """,
            (SOURCE,),
        )
    ]


def _still_linked(connection: sqlite3.Connection, activity_id: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM event_activity_links WHERE activity_id = ? LIMIT 1",
        (activity_id,),
    ).fetchone() is not None
