"""The `(k)` workout-classification action for the interactive triage walk.

Kept beside `triage.py` rather than inside it: the classifier/sheet/evidence
decision, the manual set prompt and the edit-log write are one cohesive unit,
and moving them here keeps the runner's dispatch file focused.

`WorkoutClassificationTriage` is a mixin for `TriageRunner`; it uses the
runner's ``writer``, ``read``, ``print``, ``_count`` and ``pending_note``.
"""

from __future__ import annotations

import re
from typing import Callable

from hobbyjogging_core.sports import normalize_token
from hobbyjogging_core.workouts import (
    WORKOUT_METHODS,
    WORKOUT_TARGETS,
    canonical_method,
    canonical_target,
)

from .causes import item_context
from .history import record_changes
from .quality import WORKOUT_CLASSIFICATION


def _format_sets(methods, targets) -> str:
    return (
        f"methods={', '.join(methods) or '-'} "
        f"targets={', '.join(targets) or '-'}"
    )


def _stored_workout_values(
    writer,
    activity_id: str,
    table: str,
    column: str,
) -> list[str]:
    """Read one stored workout set across every source."""
    rows = writer.connection.execute(
        f"SELECT DISTINCT {column} FROM {table} WHERE activity_id = ?",
        (activity_id,),
    )
    return sorted(row[0] for row in rows)


def _parse_workout_tokens(
    text: str,
    allowed: dict[str, str],
    canonical: Callable[[object], str],
    kind: str,
) -> list[str]:
    """Parse comma/space-separated workout tokens, rejecting typos.

    Aliases are accepted through the canonical parser; values outside the
    vocabulary raise ``ValueError`` instead of silently becoming "other".
    """
    tokens: list[str] = []
    for raw in re.split(r"[,\s]+", text.strip()):
        if not raw:
            continue

        token = canonical(raw)
        if token == "other" and normalize_token(raw) != "other":
            direct = normalize_token(raw)
            if direct in allowed:
                token = direct
            else:
                raise ValueError(
                    f"unknown {kind} {raw!r}; choose from "
                    + ", ".join(allowed)
                )

        if token not in tokens:
            tokens.append(token)
    return tokens


class WorkoutClassificationTriage:
    """The `(k)` decision: pick, merge, evidence, keep stored or type a set."""

    def _classify_workout(self, item) -> bool:
        """Workout classification: pick a proposal, merge, or type a set.

        The decision is written as manual methods/targets, so no reimport or
        backfill can overwrite it. A classified activity's tag/comment
        evidence is offered as another choice; "kept stored" resolves the item
        without writing anything.
        """
        if item["category"] != WORKOUT_CLASSIFICATION:
            self.print("  this item is not a workout classification")
            return False

        context = item_context(item)
        classifier_methods = list(context.get("classifier_methods") or [])
        classifier_targets = list(context.get("classifier_targets") or [])
        sheet_methods = list(context.get("sheet_methods") or [])
        sheet_targets = list(context.get("sheet_targets") or [])
        evidence_methods = list(context.get("evidence_methods") or [])
        evidence_targets = list(context.get("evidence_targets") or [])
        evidence_source = context.get("evidence_source") or "evidence"
        stored_methods = list(context.get("stored_methods") or [])
        stored_targets = list(context.get("stored_targets") or [])
        code = context.get("sheet_code") or "-"

        has_classifier = bool(classifier_methods or classifier_targets)
        has_sheet = bool(sheet_methods or sheet_targets)
        has_evidence = bool(evidence_methods or evidence_targets)
        has_stored = bool(stored_methods or stored_targets)

        if has_classifier:
            self.print(
                "  classifier: "
                + _format_sets(classifier_methods, classifier_targets)
            )
        if has_sheet:
            self.print(
                f"  sheet ({code}): "
                + _format_sets(sheet_methods, sheet_targets)
            )
        if has_evidence:
            self.print(
                f"  {evidence_source} evidence: "
                + _format_sets(evidence_methods, evidence_targets)
            )
        if has_stored:
            self.print(
                "  stored: "
                + _format_sets(stored_methods, stored_targets)
            )

        choices = []
        if has_classifier:
            choices.append("1) classifier")
        if has_sheet:
            choices.append("2) sheet")
        if has_evidence:
            choices.append(f"4) {evidence_source} evidence")
        if has_stored:
            choices.append("(s) kept stored")
        if choices:
            self.print("  " + "  ".join(choices))
        self.print("  (m)erge  (n)one  (3) manual  (blank=cancel)")

        try:
            answer = self.read("  pick: ").strip().lower()
        except EOFError:
            return False

        if answer == "s":
            if not has_stored:
                self.print("  no stored classification to keep")
                return False
            self.writer.set_review_status(
                item["id"],
                "resolved",
                note=self.pending_note or "triage: kept stored",
            )
            self.writer.connection.commit()
            self.pending_note = ""
            self._count("classified")
            self.print(
                "  kept stored: "
                + _format_sets(stored_methods, stored_targets)
            )
            self.print(f"  resolved #{item['id']}")
            return True

        if answer == "1" and has_classifier:
            methods, targets, label = (
                classifier_methods,
                classifier_targets,
                "classifier",
            )
        elif answer == "2" and has_sheet:
            methods, targets, label = sheet_methods, sheet_targets, "sheet"
        elif answer == "4" and has_evidence:
            methods, targets = evidence_methods, evidence_targets
            label = f"{evidence_source} evidence"
        elif answer == "m":
            methods = sorted(
                set(classifier_methods)
                | set(sheet_methods)
                | set(evidence_methods)
            )
            targets = sorted(
                set(classifier_targets)
                | set(sheet_targets)
                | set(evidence_targets)
            )
            label = "merged"
        elif answer == "3":
            manual = self._manual_workout_sets()
            if manual is None:
                return False
            methods, targets = manual
            label = "manual"
        elif answer == "n":
            methods, targets, label = [], [], "left unclassified"
        else:
            self.print("  cancelled")
            return False

        old_methods = _stored_workout_values(
            self.writer,
            item["activity_id"],
            "activity_workout_methods",
            "method",
        )
        old_targets = _stored_workout_values(
            self.writer,
            item["activity_id"],
            "activity_workout_targets",
            "target",
        )

        self.writer.set_manual_activity_workout_methods(
            item["activity_id"],
            methods,
        )
        self.writer.set_manual_activity_workout_targets(
            item["activity_id"],
            targets,
        )
        written_methods = _stored_workout_values(
            self.writer,
            item["activity_id"],
            "activity_workout_methods",
            "method",
        )
        written_targets = _stored_workout_values(
            self.writer,
            item["activity_id"],
            "activity_workout_targets",
            "target",
        )

        note = self.pending_note or f"triage: classification {label}"
        record_changes(
            self.writer,
            entity_kind="activity",
            entity_id=item["activity_id"],
            old={"methods": old_methods, "targets": old_targets},
            new={"methods": written_methods, "targets": written_targets},
            source="triage",
            note=note,
        )
        self.writer.set_review_status(
            item["id"],
            "resolved",
            note=note,
        )
        self.writer.connection.commit()
        self.pending_note = ""
        self._count("classified")
        self.print(
            f"  {label}: " + _format_sets(written_methods, written_targets)
        )
        self.print(f"  resolved #{item['id']}")
        return True

    def _manual_workout_sets(
        self,
    ) -> tuple[list[str], list[str]] | None:
        """Read a hand-entered method/target set for one session."""
        self.print("  methods: " + ", ".join(WORKOUT_METHODS))
        self.print("  targets: " + ", ".join(WORKOUT_TARGETS))
        try:
            methods_text = self.read(
                "  methods (comma/space separated, blank=none): "
            )
            targets_text = self.read(
                "  targets (comma/space separated, blank=none): "
            )
        except EOFError:
            return None

        try:
            methods = _parse_workout_tokens(
                methods_text,
                WORKOUT_METHODS,
                canonical_method,
                "method",
            )
            targets = _parse_workout_tokens(
                targets_text,
                WORKOUT_TARGETS,
                canonical_target,
                "target",
            )
        except ValueError as exc:
            self.print(f"  {exc}")
            return None
        return methods, targets
