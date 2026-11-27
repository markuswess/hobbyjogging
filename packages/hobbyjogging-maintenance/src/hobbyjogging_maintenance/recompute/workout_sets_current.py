"""Re-derive classifier-sourced workout sets and fill the remaining gaps.

Classification is a stored derived value: importers write the received facts,
this recompute derives the sets, and ``workout_classification_queue`` records
the remaining classifier/sheet disagreements. A manually set field is never
touched. A classifier or historical backfill projection is re-derived from the
current name, RPE, intensity and work reps; a specific tag refines it in
place. A sheet or Runalyze-type set is an input and keeps its run method;
drills and strides are additive and are unioned into any non-manual set.
"""

from __future__ import annotations

from hobbyjogging_core.sources_config import load_sources
from hobbyjogging_core.sports import RUN_SPORTS
from hobbyjogging_core.workouts import ADDITIVE_METHODS

from ..context import TaskContext
from ..registry import task
from ..workouts import (
    CLASSIFIER_SOURCE,
    classifier_proposal,
    disagrees,
    evidence_proposal,
    is_easy_default,
    runalyze_proposal,
    scoped_activities,
    sheet_proposal,
    stored_provenance,
    write_tag_refinement,
)

_COUNT_ORDER = (
    "activities",
    "derived",
    "reclassified",
    "refined",
    "additive",
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

        provenance = stored_provenance(context.connection, activity.id)
        if provenance == "manual":
            context.count("already_classified")
            continue

        evidence, evidence_source = evidence_proposal(
            activity,
            context.connection,
        )
        additive = (
            evidence.methods & ADDITIVE_METHODS
            if evidence is not None and not evidence.empty
            else set()
        )

        if provenance == "classifier":
            # A specific tag refines a classifier projection in place; an
            # additive-only tag is unioned below. Comments only fill empty.
            if (
                evidence_source == "tag"
                and evidence is not None
                and not evidence.empty
            ):
                specific = (
                    evidence.methods - ADDITIVE_METHODS
                ) - {"other"}
                specific_targets = evidence.targets - {"other"}
                if specific or specific_targets:
                    _refine_from_tag(
                        context,
                        activity,
                        methods=specific | additive,
                        targets=specific_targets,
                    )
                    context.count("refined")
                    continue

            intervals = context.repository.activity_intervals(activity.id)
            classifier = classifier_proposal(activity, intervals)
            if classifier.empty:
                # The name, RPE and reps no longer justify the stored set;
                # keep it rather than clearing a decision on weak evidence.
                context.count("stale_no_evidence")
                if _add_additive(context, activity, additive):
                    context.count("additive")
                continue

            if _same(activity, classifier.methods, classifier.targets):
                if _add_additive(context, activity, additive):
                    context.count("additive")
                else:
                    context.count("unchanged")
                continue

            _write(
                context,
                activity.id,
                classifier.methods,
                classifier.targets,
                CLASSIFIER_SOURCE,
            )
            if _add_additive(context, activity, additive):
                context.count("additive")
            context.count("reclassified")
            continue

        if provenance == "input":
            # Sheet, Runalyze, backfill and tag sets are inputs. A tag does
            # not replace them; drills and strides are additive exceptions.
            if _add_additive(context, activity, additive):
                context.count("additive")
            else:
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
                    proposal_source = CLASSIFIER_SOURCE
                else:
                    context.count("no_proposal")
                    continue
        elif classifier_has and not sheet_has:
            methods, targets = classifier.methods, classifier.targets
            proposal_source = CLASSIFIER_SOURCE
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

        _write(
            context,
            activity.id,
            set(methods),
            targets,
            proposal_source,
        )
        if _add_additive(context, activity, additive):
            context.count("additive")
        context.count("derived")

    context.order_counts(_COUNT_ORDER)

    if context.counts.get("conflict"):
        context.note(
            f"{context.counts['conflict']} disagreements left for "
            "workout_classification_queue"
        )


def _refine_from_tag(
    context: TaskContext,
    activity,
    *,
    methods: set[str],
    targets: set[str],
) -> None:
    """Replace the classifier-owned parts of a set with tag evidence."""
    write_tag_refinement(
        context.writer,
        activity.id,
        methods=methods,
        targets=targets,
    )


def _add_additive(
    context: TaskContext,
    activity,
    methods: set[str],
) -> bool:
    """Union drills/strides into a non-manual set, preserving tag rows."""
    missing = set(methods) - set(activity.workout_methods)
    if not missing:
        return False

    existing = {
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
        sorted(existing | missing),
        source="tag",
    )
    return True


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
