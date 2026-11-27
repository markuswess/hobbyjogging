"""Classifier and sheet proposals shared by the classification tasks.

The reports classifier proposes a set from the activity name/RPE/intervals;
the historical sheet proposes a set from its ``Trainigstyp`` code. Both the
backfill and the review-queue sync use these helpers, so they cannot drift.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from hobbyjogging_core.classify import (
    LT1_WORDS,
    RACE_WORDS,
    SUBT_WORDS,
    TEMPO_WORDS,
    classify,
)
from hobbyjogging_core.model import Activity
from hobbyjogging_core.sports import RUN_SPORTS
from hobbyjogging_core.workouts import (
    ADDITIVE_METHODS,
    classification_for_category,
)
from hobbyjogging_import.quality import (
    WORKOUT_CLASSIFICATION,
    review_fingerprint,
)
from hobbyjogging_import.runalyze_types import classification_for_payload
from hobbyjogging_import.sheet_codes import classification_for_sheet_code
from hobbyjogging_import.tag_lexicon import workout_meanings

from .context import TaskContext

# A sheet run with no training code and a low average HR is an easy run.
EASY_MAX_HR = 140


@dataclass
class Proposal:
    """One source's proposed method/target sets."""

    methods: set[str] = field(default_factory=set)
    targets: set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not self.methods and not self.targets


@dataclass
class Conflict:
    """A proposal that disagrees with what is stored or with another source."""

    activity_id: str
    local_date: str
    name: str
    classifier: Proposal
    sheet: Proposal
    sheet_code: str
    evidence: Proposal | None = None
    evidence_source: str = ""
    stored: Proposal | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "activity_id": self.activity_id,
            "local_date": self.local_date,
            "name": self.name,
            "classifier_methods": sorted(self.classifier.methods),
            "classifier_targets": sorted(self.classifier.targets),
            "sheet_code": self.sheet_code,
            "sheet_methods": sorted(self.sheet.methods),
            "sheet_targets": sorted(self.sheet.targets),
        }
        if self.evidence is not None:
            payload["evidence_source"] = self.evidence_source
            payload["evidence_methods"] = sorted(self.evidence.methods)
            payload["evidence_targets"] = sorted(self.evidence.targets)
            payload["stored_methods"] = (
                sorted(self.stored.methods) if self.stored else []
            )
            payload["stored_targets"] = (
                sorted(self.stored.targets) if self.stored else []
            )
        return payload

    def lines(self) -> list[str]:
        lines = [
            f"  {self.local_date} {self.name or '-'} [{self.activity_id}]",
            f"    classifier: methods={sorted(self.classifier.methods)} "
            f"targets={sorted(self.classifier.targets)}",
            f"    sheet ({self.sheet_code or '-'}): "
            f"methods={sorted(self.sheet.methods)} "
            f"targets={sorted(self.sheet.targets)}",
        ]
        if self.evidence is not None:
            lines.append(
                f"    {self.evidence_source or 'evidence'}: "
                f"methods={sorted(self.evidence.methods)} "
                f"targets={sorted(self.evidence.targets)}"
            )
        if self.stored is not None:
            lines.append(
                f"    stored: methods={sorted(self.stored.methods)} "
                f"targets={sorted(self.stored.targets)}"
            )
        return lines


def classifier_proposal(
    activity: Activity,
    intervals: list | None = None,
) -> Proposal:
    """Propose sets from the heuristic classifier, never from stored values."""
    category = classify(activity, intervals, use_stored=False)
    methods, targets = classification_for_category(
        category.group,
        category.kind,
        category.detail,
    )
    return Proposal(methods, targets)


CLASSIFIER_SOURCE = "classifier"


def stored_provenance(
    connection: sqlite3.Connection,
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
    if all(row["source"] == CLASSIFIER_SOURCE for row in rows):
        return "classifier"
    return "input"


def write_tag_refinement(
    writer,
    activity_id: str,
    *,
    methods: set[str],
    targets: set[str],
) -> None:
    """Replace the derivations of a set with tag evidence.

    ``classifier`` and the historical ``backfill`` source are both
    projections; a specific tag replaces their contribution.
    """
    for source in (CLASSIFIER_SOURCE, "backfill"):
        if methods:
            writer.replace_activity_workout_methods(
                activity_id,
                [],
                source=source,
            )
        if targets:
            writer.replace_activity_workout_targets(
                activity_id,
                [],
                source=source,
            )
    if methods:
        writer.replace_activity_workout_methods(
            activity_id,
            sorted(methods),
            source="tag",
        )
    if targets:
        writer.replace_activity_workout_targets(
            activity_id,
            sorted(targets),
            source="tag",
        )


def sheet_proposal(
    connection: sqlite3.Connection,
    activity_id: str,
) -> tuple[Proposal | None, int | None, set[str], str]:
    """Return the sheet's proposal, its record id, its tags, and its code."""
    row = connection.execute(
        """
        SELECT sr.id, sr.payload_json
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE als.activity_id = ?
          AND sr.source = 'sheet'
          AND sr.record_type = 'activity'
        ORDER BY sr.id
        LIMIT 1
        """,
        (activity_id,),
    ).fetchone()

    if row is None:
        return None, None, set(), ""

    try:
        values = json.loads(row["payload_json"] or "{}").get("values") or {}
    except (TypeError, ValueError):
        values = {}

    code = str(values.get("Trainigstyp") or "")
    methods, targets, tags = classification_for_sheet_code(code)
    return Proposal(methods, targets), row["id"], tags, code


def runalyze_proposal(
    connection: sqlite3.Connection,
    activity_id: str,
) -> Proposal | None:
    """Return Runalyze's type proposal for one linked activity, if any."""
    row = connection.execute(
        """
        SELECT sr.payload_json
        FROM activity_sources als
        JOIN source_records sr ON sr.id = als.source_record_id
        WHERE als.activity_id = ?
          AND sr.source = 'runalyze'
          AND sr.record_type = 'activity'
        ORDER BY sr.id DESC
        LIMIT 1
        """,
        (activity_id,),
    ).fetchone()
    if row is None:
        return None

    try:
        payload = json.loads(row["payload_json"] or "{}")
    except (TypeError, ValueError):
        return None

    methods, targets = classification_for_payload(payload)
    if not methods and not targets:
        return None
    return Proposal(methods, targets)


_METHOD_PRIORITY = (
    "race",
    "intervals",
    "fartlek",
    "progression",
    "long_run",
    "continuous",
)
_TARGET_PRIORITY = (
    "lt1",
    "subthreshold",
    "threshold",
    "marathon",
    "vo2max",
    "speed",
    "base",
    "recovery",
    "other",
)
_LONG_WORDS = ("longjog", "long run", "longrun")
_RECOVERY_WORDS = ("regeneration", "recovery", "regenerativ")
_PROGRESSION_WORDS = ("progressiv", "progression")
_FARTLEK_WORDS = ("fartlek", "fahrtspiel", "wechseltempo")
_MARATHON_WORDS = ("marathontempo", "marathon pace", "marathon-pace")
_INTERVAL_TEXT = re.compile(
    r"\b\d+\s*[x×]\s*\d+\s*(?:m|km|min|minuten|minute|s|sek|sekunden)\b"
    r"|\b\d+(?:\s*-\s*\d+){2,}\s*(?:min|minuten|km|m)\b"
    r"|\b(?:intervalle?|intervals?|serien?|wiederholungen?|wdh)\b",
    re.IGNORECASE,
)


def tag_proposal(tags: list[str] | None) -> Proposal | None:
    """Propose a set from the mapped workout tags, or ``None``.

    The method and target priorities mirror the classifier's content-first
    rule: race and intervals beat a long run, LT1 beats subT, and a quality
    target beats base/recovery. ``strides`` and ``drills`` are additive unless
    the session is a race; a drills-only tag still proposes the additive
    method so a drills session is visible.
    """
    meanings = workout_meanings(tags or [])
    if not meanings:
        return None

    methods: set[str] = set()
    targets: set[str] = set()
    for meaning in meanings:
        methods |= meaning.methods
        targets |= meaning.targets

    if "race" in methods:
        return Proposal({"race"}, targets or {"other"})

    method = _select(methods, _METHOD_PRIORITY)
    additive = methods & ADDITIVE_METHODS
    if method is None:
        return Proposal(additive, set()) if additive else None

    selected = {method} | additive
    target = _select(targets, _TARGET_PRIORITY)
    return Proposal(selected, {target} if target else set())


def description_proposal(description: str | None) -> Proposal | None:
    """Propose a set from an explicit description, or ``None``.

    Only explicit target words and structured interval patterns count. A
    generic note such as "easy run" stays without a proposal; the classifier
    already uses RPE/intensity for that.
    """
    text = str(description or "").lower()
    if not text:
        return None

    if any(word in text for word in LT1_WORDS):
        return Proposal({"intervals"}, {"lt1"})
    if any(word in text for word in SUBT_WORDS):
        return Proposal({"intervals"}, {"subthreshold"})
    if any(word in text for word in _MARATHON_WORDS):
        return Proposal({"continuous"}, {"marathon"})
    if any(word in text for word in TEMPO_WORDS):
        return Proposal({"continuous"}, {"threshold"})
    if any(word in text for word in RACE_WORDS):
        return Proposal({"race"}, {"other"})
    if any(word in text for word in _LONG_WORDS):
        return Proposal({"long_run"}, {"base"})
    if any(word in text for word in _FARTLEK_WORDS):
        return Proposal({"fartlek"}, set())
    if any(word in text for word in _PROGRESSION_WORDS):
        return Proposal({"progression"}, {"base"})
    if any(word in text for word in _RECOVERY_WORDS):
        return Proposal({"continuous"}, {"recovery"})
    if _INTERVAL_TEXT.search(text):
        return Proposal({"intervals"}, {"other"})
    return None


def evidence_proposal(
    activity: Activity,
) -> tuple[Proposal | None, str]:
    """Return the tag/comment proposal and its source label.

    Tags are deliberate athlete input, so they win over a description; a
    description is the fallback when there is no mapped workout tag. Only run
    sports use the running vocabulary; a swim or ride tag stays context.
    """
    if activity.type not in RUN_SPORTS:
        return None, ""

    tags = tag_proposal(activity.tags)
    if tags is not None and not tags.empty:
        return tags, "tag"

    comment = description_proposal(activity.description)
    if comment is not None and not comment.empty:
        return comment, "comment"

    return None, ""


def _select(values: set[str], priority: tuple[str, ...]) -> str | None:
    for value in priority:
        if value in values:
            return value
    return sorted(values)[0] if values else None


def disagrees(classifier: Proposal, sheet: Proposal) -> bool:
    """Whether the two proposals disagree on a set both of them fill."""
    methods_conflict = (
        bool(classifier.methods)
        and bool(sheet.methods)
        and classifier.methods != sheet.methods
    )
    targets_conflict = (
        bool(classifier.targets)
        and bool(sheet.targets)
        and classifier.targets != sheet.targets
    )
    return methods_conflict or targets_conflict


def evidence_conflicts(stored: Proposal, evidence: Proposal) -> bool:
    """Whether tag/comment evidence claims something the stored set lacks.

    Evidence is sparse: a tag names one method and perhaps one target. It
    only conflicts when it names a value the stored classification does not
    contain, so an extra ``strides`` or ``drills`` method or a missing target
    stays quiet.
    """
    return bool(
        evidence.methods - stored.methods - ADDITIVE_METHODS
    ) or bool(evidence.targets - stored.targets)


def conflict_from(
    activity: Activity,
    classifier: Proposal,
    sheet: Proposal,
    sheet_code: str,
) -> Conflict:
    """Build the review payload for one disagreement."""
    return Conflict(
        activity_id=activity.id,
        local_date=activity.date.isoformat(),
        name=activity.name or "",
        classifier=classifier,
        sheet=sheet,
        sheet_code=sheet_code,
    )


def evidence_conflict_from(
    activity: Activity,
    *,
    evidence: Proposal,
    evidence_source: str,
    stored: Proposal,
    classifier: Proposal,
    sheet: Proposal | None,
    sheet_code: str,
) -> Conflict:
    """Build the review payload for evidence that disagrees with the store."""
    return Conflict(
        activity_id=activity.id,
        local_date=activity.date.isoformat(),
        name=activity.name or "",
        classifier=classifier,
        sheet=sheet or Proposal(),
        sheet_code=sheet_code,
        evidence=evidence,
        evidence_source=evidence_source,
        stored=stored,
    )


def fingerprint(conflict: Conflict) -> str:
    """Stable identity for a disagreement; a changed proposal is a new item.

    An evidence item is about the evidence and the stored set, so a change in
    the classifier or sheet does not reopen a decision about it.
    """
    if conflict.evidence is not None:
        return review_fingerprint(
            [
                WORKOUT_CLASSIFICATION,
                conflict.activity_id,
                conflict.evidence_source,
                sorted(conflict.evidence.methods),
                sorted(conflict.evidence.targets),
                sorted(conflict.stored.methods) if conflict.stored else [],
                sorted(conflict.stored.targets) if conflict.stored else [],
            ]
        )

    return review_fingerprint(
        [
            WORKOUT_CLASSIFICATION,
            conflict.activity_id,
            sorted(conflict.classifier.methods),
            sorted(conflict.classifier.targets),
            conflict.sheet_code,
            sorted(conflict.sheet.methods),
            sorted(conflict.sheet.targets),
        ]
    )


def is_easy_default(activity: Activity, sheet: Proposal | None) -> bool:
    """Whether an unproposed sheet run is an easy run by default."""
    return (
        sheet is not None
        and activity.type in RUN_SPORTS
        and activity.avg_hr is not None
        and activity.avg_hr < EASY_MAX_HR
    )


def scoped_activities(context: TaskContext) -> list[Activity]:
    """Return the in-scope activities in canonical order."""
    start, end = _date_bounds(context)
    if start is None or end is None:
        return []

    activities = context.repository.activities(start, end)
    if context.scope.entity_id is not None:
        activities = [
            activity
            for activity in activities
            if activity.id == context.scope.entity_id
        ]
    if context.scope.limit is not None:
        activities = activities[: context.scope.limit]
    return activities


def _date_bounds(context: TaskContext) -> tuple[date | None, date | None]:
    scope = context.scope

    if scope.entity_id is not None:
        row = context.connection.execute(
            """
            SELECT local_date FROM activities
            WHERE id = ? AND excluded_at IS NULL
            """,
            (scope.entity_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown or excluded activity: {scope.entity_id}")
        day = date.fromisoformat(row["local_date"])
        return day, day

    start, end = scope.start, scope.end
    if start is None or end is None:
        row = context.connection.execute(
            """
            SELECT MIN(local_date), MAX(local_date) FROM activities
            WHERE excluded_at IS NULL
            """
        ).fetchone()
        if row[0] is None:
            return None, None
        start = start or date.fromisoformat(row[0])
        end = end or date.fromisoformat(row[1])

    return start, end
