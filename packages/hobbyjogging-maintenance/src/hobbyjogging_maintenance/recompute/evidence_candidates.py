"""Evidence candidates from tags and stored measurements.

Two recomputes turn evidence the log already carries into non-hiding review
items. They never write the proposed value: a period or a sport stays a human
decision.

- ``illness_candidates_current`` groups illness-tagged days, lets
  ``wieder gesund`` close a range, and opens a ``period_candidate`` item when
  the range is not covered by a stored illness period.
- ``trail_candidates_current`` combines session/lap elevation, sub-sport,
  trail tags and route names into a ``consistency`` item suggesting
  ``trail_run``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from hobbyjogging_core.sports import RUN_SPORTS
from hobbyjogging_import.quality import (
    CONSISTENCY,
    PERIOD_CANDIDATE,
    review_fingerprint,
)
from hobbyjogging_import.tag_lexicon import lookup_tag

from ..context import TaskContext
from ..registry import task
from ..workouts import scoped_activities

TRAIL_M_PER_KM = 40.0
ILLNESS_GAP_DAYS = 3
RECOVERY_WINDOW_DAYS = 21

_ILLNESS_COUNTS = (
    "activities",
    "candidates",
    "opened",
    "unchanged",
    "resolved",
)
_TRAIL_COUNTS = (
    "activities",
    "candidates",
    "opened",
    "unchanged",
    "resolved",
)


@task(
    "illness_candidates_current",
    kind="recompute",
    description=(
        "Open period_candidate items for illness tags outside a stored "
        "illness period."
    ),
)
def illness_candidates_current(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    periods = _illness_periods(context.connection)
    tagged, recovered = _illness_days(activities)
    candidates = _illness_ranges(tagged, recovered, periods)
    context.count("activities", len(activities))

    candidates.sort(
        key=lambda item: (item["start_date"], item["end_date"], item["tags"])
    )

    wanted: set[str] = set()
    for candidate in candidates:
        context.count("candidates")
        fingerprint = _illness_fingerprint(candidate)
        wanted.add(fingerprint)
        detail = _illness_detail(candidate)
        _, created = context.writer.record_review_item(
            category=PERIOD_CANDIDATE,
            detail=detail,
            context={
                "rule": "illness_candidate",
                "kind": "illness",
                "start_date": candidate["start_date"],
                "end_date": candidate["end_date"],
                "tags": candidate["tags"],
            },
            severity="info",
            fingerprint=fingerprint,
            activity_id=candidate["activity_id"],
        )
        context.count("opened" if created else "unchanged")

    _resolve_stale(
        context,
        category=PERIOD_CANDIDATE,
        rule="illness_candidate",
        wanted=wanted,
        activity_ids={activity.id for activity in activities},
    )
    context.order_counts(_ILLNESS_COUNTS)


@task(
    "trail_candidates_current",
    kind="recompute",
    description=(
        "Open consistency items for run activities with trail evidence."
    ),
)
def trail_candidates_current(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    wanted: set[str] = set()
    for activity in activities:
        context.count("activities")
        if activity.type == "trail_run" or activity.type not in RUN_SPORTS:
            continue
        if not activity.distance_m:
            continue

        evidence = _trail_evidence(context, activity)
        if not evidence:
            continue

        context.count("candidates")
        fingerprint = review_fingerprint(
            [CONSISTENCY, activity.id, "trail_run"]
        )
        wanted.add(fingerprint)
        _, created = context.writer.record_review_item(
            category=CONSISTENCY,
            detail=(
                f"{activity.type} looks like a trail run: "
                + ", ".join(evidence)
            ),
            context={
                "rule": "trail_candidate",
                "suggested": "trail_run",
                "current_sport": activity.type,
                "evidence": evidence,
            },
            severity="info",
            fingerprint=fingerprint,
            activity_id=activity.id,
        )
        context.count("opened" if created else "unchanged")

    _resolve_stale(
        context,
        category=CONSISTENCY,
        rule="trail_candidate",
        wanted=wanted,
        activity_ids={activity.id for activity in activities},
    )
    context.order_counts(_TRAIL_COUNTS)


# -- illness -------------------------------------------------------------


def _illness_days(
    activities,
) -> tuple[dict[date, list[tuple[str, str]]], set[date]]:
    tagged: dict[date, list[tuple[str, str]]] = {}
    recovered: set[date] = set()

    for activity in activities:
        for tag in activity.tags:
            meaning = lookup_tag(tag)
            if meaning is None:
                continue
            if meaning.kind == "illness":
                tagged.setdefault(activity.date, []).append(
                    (activity.id, tag)
                )
            elif meaning.kind == "recovered":
                recovered.add(activity.date)

    return tagged, recovered


def _illness_ranges(tagged, recovered, periods) -> list[dict]:
    days = sorted(tagged)
    if not days:
        return []

    runs: list[list[date]] = []
    for day in days:
        if runs and (day - runs[-1][-1]).days <= ILLNESS_GAP_DAYS:
            runs[-1].append(day)
        else:
            runs.append([day])

    candidates = []
    for run in runs:
        start = run[0]
        end = run[-1]
        recovered_days = sorted(
            day
            for day in recovered
            if start <= day <= end + timedelta(days=RECOVERY_WINDOW_DAYS)
        )
        if recovered_days:
            end = recovered_days[0]

        if any(
            start >= period[0] and end <= (period[1] or period[0])
            for period in periods
        ):
            continue

        tags = sorted({tag for day in run for _, tag in tagged[day]})
        candidates.append(
            {
                "activity_id": tagged[start][0][0],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "tags": tags,
            }
        )

    return _merge_ranges(candidates)


def _merge_ranges(candidates: list[dict]) -> list[dict]:
    """Merge overlapping illness ranges (a shared recovery day can overlap)."""
    merged: list[dict] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (item["start_date"], item["end_date"]),
    ):
        if merged and candidate["start_date"] <= merged[-1]["end_date"]:
            merged[-1]["end_date"] = max(
                merged[-1]["end_date"], candidate["end_date"]
            )
            merged[-1]["tags"] = sorted(
                set(merged[-1]["tags"]) | set(candidate["tags"])
            )
        else:
            merged.append(candidate)
    return merged


def _illness_detail(candidate: dict) -> str:
    start = candidate["start_date"]
    end = candidate["end_date"]
    tags = ", ".join(candidate["tags"])
    if start == end:
        return f"illness evidence {start} ({tags}) is not covered by a period"
    return (
        f"illness evidence {start}..{end} ({tags}) is not covered by a period"
    )


def _illness_fingerprint(candidate: dict) -> str:
    return review_fingerprint(
        [
            PERIOD_CANDIDATE,
            "illness",
            candidate["start_date"],
            candidate["end_date"],
            candidate["tags"],
        ]
    )


def _illness_periods(
    connection: sqlite3.Connection,
) -> list[tuple[date, date | None]]:
    return [
        (
            date.fromisoformat(row["start_date"]),
            date.fromisoformat(row["end_date"]) if row["end_date"] else None,
        )
        for row in connection.execute(
            """
            SELECT start_date, end_date FROM training_periods
            WHERE kind = 'illness' AND excluded_at IS NULL
            """
        )
    ]


# -- trail ---------------------------------------------------------------


def _trail_evidence(context: TaskContext, activity) -> list[str]:
    gain = activity.elevation_gain_m
    if gain is None:
        laps = context.repository.activity_laps(activity.id)
        gain = sum(lap.elevation_gain_m or 0 for lap in laps) or None

    evidence = []
    m_per_km = 0.0
    if gain is not None and gain > 0:
        m_per_km = gain / (activity.distance_m / 1000.0)
        if m_per_km >= TRAIL_M_PER_KM:
            evidence.append(f"{m_per_km:.0f} m/km")

    sub_sport = str(activity.sub_sport or "").lower()
    if sub_sport in {"trail", "mountain"} or "trail" in sub_sport:
        evidence.append(f"sub_sport={sub_sport}")

    if any(
        (meaning := lookup_tag(tag)) is not None
        and meaning.kind == "trail"
        for tag in activity.tags
    ):
        evidence.append("trail tag")

    route_names = [
        route.name
        for route in activity.routes
        if route.name
        and (
            "trail" in route.name.lower()
            or "berg" in route.name.lower()
        )
    ]
    if route_names and evidence:
        evidence.append("route: " + ", ".join(sorted(route_names)))

    return evidence


# -- shared --------------------------------------------------------------


def _resolve_stale(
    context: TaskContext,
    *,
    category: str,
    rule: str,
    wanted: set[str],
    activity_ids: set[str],
) -> None:
    for item in context.writer.review_items(
        category=category,
        status="open",
    ):
        if item["activity_id"] not in activity_ids:
            continue
        try:
            item_context = json.loads(item["context_json"] or "{}")
        except ValueError:
            continue
        if item_context.get("rule") != rule:
            continue
        if item["fingerprint"] in wanted:
            continue
        context.writer.set_review_status(
            item["id"],
            "resolved",
            note="no longer applies",
        )
        context.count("resolved")
