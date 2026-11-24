"""Derive workout sets for activities that have none.

Classification is a stored derived value: importers write the received facts,
this recompute derives the sets, and ``workout_classification_queue`` records
the disagreements for triage. It only fills gaps — an activity that already
has sets from any source is never touched, so manual decisions and the
one-time backfill are safe.
"""

from __future__ import annotations

from hobbyjogging_core.sources_config import load_sources
from hobbyjogging_core.sports import RUN_SPORTS

from ..context import TaskContext
from ..registry import task
from ..workouts import (
    classifier_proposal,
    disagrees,
    is_easy_default,
    runalyze_proposal,
    scoped_activities,
    sheet_proposal,
)

SOURCE = "classifier"

_COUNT_ORDER = (
    "activities",
    "derived",
    "from_runalyze_type",
    "conflict",
    "no_proposal",
    "already_classified",
)


@task(
    "workout_sets_current",
    kind="recompute",
    description=(
        "Derive workout methods/targets for activities that have none."
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

        if activity.quality is not None:
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

        if not classifier_has and not sheet_has:
            if (
                runalyze is not None
                and not runalyze.empty
                and activity.type in RUN_SPORTS
            ):
                methods, targets = runalyze.methods, runalyze.targets
                proposal_source = "runalyze"
                context.count("from_runalyze_type")
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
            proposal_source = SOURCE
        else:
            assert sheet is not None
            if disagrees(classifier, sheet):
                # The queue task turns this into a review item.
                context.count("conflict")
                continue
            methods = classifier.methods | sheet.methods
            targets = classifier.targets | sheet.targets
            proposal_source = SOURCE

        context.writer.replace_activity_workout_methods(
            activity.id,
            sorted(methods),
            source=proposal_source,
        )
        context.writer.replace_activity_workout_targets(
            activity.id,
            sorted(targets),
            source=proposal_source,
        )
        context.count("derived")

    context.order_counts(_COUNT_ORDER)

    if context.counts.get("conflict"):
        context.note(
            f"{context.counts['conflict']} disagreements left for "
            "workout_classification_queue"
        )
