"""Re-derive classifier-sourced workout sets and fill the remaining gaps.

Classification is a stored derived value: importers write the received facts,
this recompute derives the sets, and ``workout_classification_queue`` records
the disagreements for triage. A set that is manual, sheet-, Runalyze- or
import-sourced is an input and is never touched. A set whose rows are all
``source='classifier'`` is re-derived from the current name, RPE, intensity
and work reps, so a rename cannot leave a stale classification behind.
"""

from __future__ import annotations

from hobbyjogging_core.sources_config import load_sources
from hobbyjogging_core.sports import RUN_SPORTS

from ..context import TaskContext
from ..registry import task
from ..workouts import (
    classifier_proposal,
    disagrees,
    evidence_proposal,
    is_easy_default,
    runalyze_proposal,
    scoped_activities,
    sheet_proposal,
)

SOURCE = "classifier"

_COUNT_ORDER = (
    "activities",
    "derived",
    "reclassified",
    "unchanged",
    "already_classified",
    "stale_no_evidence",
    "from_runalyze_type",
    "from_tag",
    "from_comment",
    "conflict",
    "no_proposal",
)


@task(
    "workout_sets_current",
    kind="recompute",
    description=(
        "Re-derive classifier-sourced workout sets and fill the remaining "
        "gaps."
    ),
)
def workout_sets_current(context: TaskContext) -> None:
    activities = scoped_activities(context)
    if not activities:
        context.note("No activities in scope.")
        return

    config = load_sources()
    runalyze_type = (
        config.enabled("runalyze")
        and config.capability("runalyze", "workout_type")
    )

    for activity in activities:
        context.count("activities")

        provenance = _stored_provenance(context.connection, activity.id)
        if provenance in ("manual", "input"):
            context.count("already_classified")
            continue

        intervals = context.repository.activity_intervals(activity.id)
        classifier = classifier_proposal(activity, intervals)
        sheet, _, _, _ = sheet_proposal(context.connection, activity.id)
        runalyze = (
            runalyze_proposal(context.connection, activity.id)
            if runalyze_type
            else None
        )

        classifier_has = not classifier.empty
        sheet_has = sheet is not None and not sheet.empty

        if provenance == "classifier":
            if not classifier_has:
                # The name, RPE and reps no longer justify the stored set;
                # keep it rather than clearing a decision on weak evidence.
                context.count("stale_no_evidence")
                continue

            methods, targets = classifier.methods, classifier.targets
            if _same(activity, methods, targets):
                context.count("unchanged")
                continue

            _write(context, activity.id, methods, targets, SOURCE)
            context.count("reclassified")
            continue

        # Unclassified: fill the gap from the strongest available proposal.
        if not classifier_has and not sheet_has:
            if (
                runalyze is not None
                and not runalyze.empty
                and activity.type in RUN_SPORTS
            ):
                methods, targets = runalyze.methods, runalyze.targets
                proposal_source = "runalyze"
                context.count("from_runalyze_type")
            else:
                evidence, evidence_source = evidence_proposal(activity)
                if evidence is not None and not evidence.empty:
                    methods, targets = evidence.methods, evidence.targets
                    proposal_source = evidence_source
                    context.count(
                        "from_tag"
                        if evidence_source == "tag"
                        else "from_comment"
                    )
                elif is_easy_default(activity, sheet):
                    methods, targets = {"continuous"}, {"base"}
                    proposal_source = SOURCE
                else:
                    context.count("no_proposal")
                    continue
        elif classifier_has and not sheet_has:
            methods, targets = classifier.methods, classifier.targets
            proposal_source = SOURCE
        elif sheet_has and not classifier_has:
            methods, targets = sheet.methods, sheet.targets
            proposal_source = "sheet"
        else:
            assert sheet is not None
            if disagrees(classifier, sheet):
                # The queue task turns this into a review item.
                context.count("conflict")
                continue
            methods = classifier.methods | sheet.methods
            targets = classifier.targets | sheet.targets
            # The sheet is an input; label the merged set so a later
            # re-derivation cannot overwrite its contribution.
            proposal_source = "sheet"

        _write(context, activity.id, methods, targets, proposal_source)
        context.count("derived")

    context.order_counts(_COUNT_ORDER)

    if context.counts.get("conflict"):
        context.note(
            f"{context.counts['conflict']} disagreements left for "
            "workout_classification_queue"
        )


def _stored_provenance(
    connection,
    activity_id: str,
) -> str:
    """Classify the stored sets: none, manual, input or classifier.

    ``input`` is any non-manual set that came from a source other than the
    classifier (sheet, Runalyze type, the one-time backfill, an importer).
    Mixed sources are treated as input, so a re-derivation never overwrites
    part of an imported decision.
    """
    rows = connection.execute(
        """
        SELECT source, is_manual FROM activity_workout_methods
        WHERE activity_id = ?
        UNION ALL
        SELECT source, is_manual FROM activity_workout_targets
        WHERE activity_id = ?
        """,
        (activity_id, activity_id),
    ).fetchall()

    if not rows:
        return "none"
    if any(row["is_manual"] for row in rows):
        return "manual"
    if all(row["source"] == SOURCE for row in rows):
        return "classifier"
    return "input"


def _same(activity, methods: set[str], targets: set[str]) -> bool:
    return (
        set(activity.workout_methods) == set(methods)
        and set(activity.workout_targets) == set(targets)
    )


def _write(
    context: TaskContext,
    activity_id: str,
    methods: set[str],
    targets: set[str],
    source: str,
) -> None:
    context.writer.replace_activity_workout_methods(
        activity_id,
        sorted(methods),
        source=source,
    )
    context.writer.replace_activity_workout_targets(
        activity_id,
        sorted(targets),
        source=source,
    )
