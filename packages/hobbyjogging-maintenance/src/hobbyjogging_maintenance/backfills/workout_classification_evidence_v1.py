"""Resolve the one-time evidence-classification backlog.

Earlier evidence items compared a tag or comment with any stored set. The
policy now is narrower: a specific tag refines a classifier-owned projection
in place, a sheet or manual set wins over tag and comment evidence, a comment
only fills an empty classification, and generic ``other`` never overrides a
specific target. This backfill applies that policy once, then the queue stops
opening evidence items.
"""

from __future__ import annotations

import json
from datetime import date

from hobbyjogging_core.workouts import ADDITIVE_METHODS
from hobbyjogging_import.quality import WORKOUT_CLASSIFICATION
from hobbyjogging_import.tag_lexicon import normalize_tag

from ..context import TaskContext
from ..registry import task
from ..workouts import (
    sheet_proposal,
    stored_provenance,
    write_tag_refinement,
)

_COUNT_ORDER = ("items", "accepted", "closed", "skipped")

_RACE_DAY_TAGS = frozenset({"raceday", "race day"})
_RACE_TAGS = frozenset(
    {"race", "wettkampf", "virtual race", "marathontag"}
)


@task(
    "workout_classification_evidence_v1",
    kind="backfill",
    description=(
        "Accept specific tag evidence on classifier projections and close the "
        "rest of the evidence-classification backlog by policy."
    ),
)
def workout_classification_evidence(context: TaskContext) -> None:
    items = _items(context)
    if not items:
        context.note("No open evidence-classification items in scope.")
        return

    for item in items:
        context.count("items")
        context_json = _context(item)
        activity_id = item["activity_id"]
        evidence_source = context_json.get("evidence_source") or ""

        if not activity_id or not evidence_source:
            context.count("skipped")
            continue

        provenance = stored_provenance(
            context.connection,
            activity_id,
        )
        methods = {
            str(value)
            for value in (context_json.get("evidence_methods") or [])
        }
        targets = {
            str(value)
            for value in (context_json.get("evidence_targets") or [])
        }
        specific_methods = (methods - ADDITIVE_METHODS) - {"other"}
        specific_targets = targets - {"other"}

        if (
            evidence_source == "tag"
            and "race" in methods
            and _race_day_only(context, activity_id)
        ):
            context.writer.set_review_status(
                item["id"],
                "resolved",
                note="policy: race-day tag is context, not a race method",
            )
            context.count("closed")
            continue

        if (
            evidence_source == "tag"
            and _is_projection(context, activity_id)
            and (specific_methods or specific_targets)
        ):
            write_tag_refinement(
                context.writer,
                activity_id,
                methods=specific_methods
                | _additive_tag_methods(context, activity_id),
                targets=specific_targets,
            )
            context.writer.set_review_status(
                item["id"],
                "resolved",
                note="accepted tag evidence",
            )
            context.count("accepted")
            continue

        context.writer.set_review_status(
            item["id"],
            "resolved",
            note=_policy_note(
                evidence_source, provenance, specific_methods, specific_targets
            ),
        )
        context.count("closed")

    context.order_counts(_COUNT_ORDER)


def _items(context: TaskContext):
    rows = context.writer.review_items(
        category=WORKOUT_CLASSIFICATION,
        status="open",
    )
    scope = context.scope
    selected = []
    for row in rows:
        if scope.entity_id is not None and row["activity_id"] != scope.entity_id:
            continue
        day = (
            date.fromisoformat(row["local_date"])
            if row["local_date"]
            else None
        )
        if scope.start is not None and (day is None or day < scope.start):
            continue
        if scope.end is not None and (day is None or day > scope.end):
            continue
        selected.append(row)
    if scope.limit is not None:
        return selected[: scope.limit]
    return selected


def _context(item) -> dict:
    try:
        value = json.loads(item["context_json"] or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _policy_note(
    evidence_source: str,
    provenance: str,
    specific_methods: set[str],
    specific_targets: set[str],
) -> str:
    if evidence_source == "comment":
        return "policy: comment only fills an empty classification"
    if provenance in ("manual", "input", "none"):
        return "policy: stored set wins"
    if not specific_methods and not specific_targets:
        return "policy: generic or additive evidence does not override"
    return "policy: evidence does not refine a classifier set"


def _is_projection(context: TaskContext, activity_id: str) -> bool:
    """Whether the stored set is a classifier/backfill derivation.

    The historical ``workout_classification_v1`` wrote its classifier output
    as ``source='backfill'``; treat that as a projection too. Additive
    ``drills``/``strides`` tag rows do not turn a projection into an input. A
    set that equals the sheet proposal is sheet-derived and stays an input.
    """
    method_rows = context.connection.execute(
        """
        SELECT method, source, is_manual
        FROM activity_workout_methods WHERE activity_id = ?
        """,
        (activity_id,),
    ).fetchall()
    target_rows = context.connection.execute(
        """
        SELECT target, source, is_manual
        FROM activity_workout_targets WHERE activity_id = ?
        """,
        (activity_id,),
    ).fetchall()

    if not method_rows and not target_rows:
        return False
    if any(
        row["is_manual"] for row in list(method_rows) + list(target_rows)
    ):
        return False

    for row in method_rows:
        if row["source"] in ("classifier", "backfill"):
            continue
        if row["source"] == "tag" and row["method"] in ADDITIVE_METHODS:
            continue
        return False

    for row in target_rows:
        if row["source"] not in ("classifier", "backfill"):
            return False

    sheet, _, _, _ = sheet_proposal(context.connection, activity_id)
    if sheet is None or sheet.empty:
        return True

    methods, targets = _stored_sets(context, activity_id)
    return not (
        methods == sheet.methods and targets == sheet.targets
    )


def _stored_sets(
    context: TaskContext,
    activity_id: str,
) -> tuple[set[str], set[str]]:
    methods = {
        row["method"]
        for row in context.connection.execute(
            "SELECT method FROM activity_workout_methods WHERE activity_id = ?",
            (activity_id,),
        )
    }
    targets = {
        row["target"]
        for row in context.connection.execute(
            "SELECT target FROM activity_workout_targets WHERE activity_id = ?",
            (activity_id,),
        )
    }
    return methods, targets


def _additive_tag_methods(
    context: TaskContext,
    activity_id: str,
) -> set[str]:
    return {
        row["method"]
        for row in context.connection.execute(
            """
            SELECT method FROM activity_workout_methods
            WHERE activity_id = ? AND source = 'tag' AND is_manual = 0
            """,
            (activity_id,),
        )
        if row["method"] in ADDITIVE_METHODS
    }


def _race_day_only(context: TaskContext, activity_id: str) -> bool:
    tags = {
        normalize_tag(row["tag"])
        for row in context.connection.execute(
            "SELECT tag FROM activity_tags WHERE activity_id = ?",
            (activity_id,),
        )
    }
    return bool(tags & _RACE_DAY_TAGS) and not bool(tags & _RACE_TAGS)
