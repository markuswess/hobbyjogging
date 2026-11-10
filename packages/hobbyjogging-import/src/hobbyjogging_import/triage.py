"""Interactive review queue walk (`hobbyjogging-import review triage`).

One open review item at a time, each decision written immediately:

    #1 warn quality/open  2019-01-30  Run  (no timing data: duration is 0 s)
      activity 5d459fa1  fit:2019-01-30_18-02-00.fit
      (i)nspect  (o)pen  (ci) Intervals  (cg) Garmin  (e)nter valid time
      (d)elete  (r)esolve  (x)ignore  (n)ote  (s)kip  (h)elp  (q)uit > _
"""

from __future__ import annotations

import json
import re
import webbrowser
from typing import Callable

from hobbyjogging_core import TrainingWriter
from hobbyjogging_core.sports import (
    RIDE_SPORTS,
    RUN_SPORTS,
    WALK_SPORTS,
    normalize_token,
)
from hobbyjogging_core.workouts import (
    WORKOUT_METHODS,
    WORKOUT_TARGETS,
    canonical_method,
    canonical_target,
)

from .causes import UNCLASSIFIED, item_cause, item_context
from .clipboard import copy_text
from .editing import apply_manual_edit
from .links import (
    GARMIN_URL,
    INTERVALS_URL,
    garmin_manifest_index,
    garmin_url,
    intervals_activity_id,
    intervals_url,
)
from .quality import CONFLICT, WORKOUT_CLASSIFICATION, refresh_activity_quality
from .review_cli import _format_summary_line
from .values import (
    format_distance_m,
    format_duration_s,
    format_field,
    format_pace,
    format_speed,
    parse_distance_m,
    parse_duration_s,
    parse_sport,
)

KEYS_HELP = """\
keys:
  (i)nspect        full item detail
  (v) pick value   field conflict: choose which source value stands
  (k) classify     workout classification: pick, merge, edit manually, or leave unclassified
  (t)rust Intervals  force re-import and take ownership of changed fields
  (o)pen           open all available activity links
  (ci)             copy the Intervals activity URL
  (cg)             copy the Garmin Connect activity URL
  (e)nter value    manually edit duration/distance/sport, then re-check
  (d)elete         durably exclude the activity (soft delete)
  (r)esolve        mark handled (activity returns to reports)
  (x)ignore        mark accepted as-is (activity stays in reports)
  (n)ote           attach a note to the next r/x/d action
  1-9              ambiguous match: link to that candidate
  (s)kip / Enter   next item, leave it open
  (h)elp           this text
  (q)uit           stop and print a summary"""

def _format_sets(methods, targets) -> str:
    return (
        f"methods={', '.join(methods) or '-'} "
        f"targets={', '.join(targets) or '-'}"
    )


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


def _activity_metrics(
    sport: object,
    duration_s: object,
    distance_m: object,
) -> str:
    """One line of sport, duration, distance, and pace/speed."""
    parts = []
    if sport:
        parts.append(str(sport))
    if duration_s is not None:
        parts.append(format_duration_s(duration_s))
    if distance_m:
        parts.append(format_distance_m(distance_m))

    pace = _pace_label(sport, duration_s, distance_m)
    if pace:
        parts.append(pace)
    return " · ".join(parts)


def _pace_label(
    sport: object,
    duration_s: object,
    distance_m: object,
) -> str:
    if not duration_s or not distance_m:
        return ""
    if sport in RIDE_SPORTS:
        return format_speed(duration_s, distance_m)
    if sport in RUN_SPORTS or sport in WALK_SPORTS:
        return format_pace(duration_s, distance_m)
    return ""


def _one_line(text: object, limit: int = 120) -> str:
    """Collapse whitespace and truncate a description to one line."""
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


DEFAULT_FIELD = {
    "zero_duration": "duration_s",
    "zero_distance": "distance_m",
    "implied_pace": "sport",
}

_FIELD_LABELS = {
    "duration_s": "duration",
    "distance_m": "distance",
    "sport": "sport",
}

_VALUE_PROMPTS = {
    "duration_s": (
        "value (46:20, 1:02:03, or seconds): ",
        parse_duration_s,
    ),
    "distance_m": (
        "value (8.2km, 8200m, or plain km): ",
        parse_distance_m,
    ),
    "sport": (
        "value (e.g. trail_running or mtb_ride): ",
        parse_sport,
    ),
}


class AbortEdit(ValueError):
    """Raised when the user aborts value entry in the triage edit flow."""


class TriageRunner:
    """Walks open review items and applies per-item decisions."""

    def __init__(
        self,
        writer: TrainingWriter,
        *,
        read: Callable[[str], str] = input,
        print: Callable = print,
        open_url: Callable[[str], bool] = webbrowser.open,
        copy: Callable[[str], str | None] = copy_text,
        reimport: Callable[[str], object] | None = None,
    ):
        self.writer = writer
        self.read = read
        self.print = print
        self.open_url = open_url
        self.copy = copy
        self.reimport = reimport or self._default_reimport
        self.counters: dict[str, int] = {}
        self.pending_note = ""
        self._garmin_index = None
        self._garmin_urls: dict[str, str | None] = {}

    def run(
        self,
        *,
        limit: int | None = None,
        category: str | None = None,
        severity: str | None = None,
        activity_id: str | None = None,
        cause: str | None = None,
    ) -> dict[str, int]:
        """Walk the open queue. Returns the decision counters."""
        items = self._queue_items(
            category=category,
            severity=severity,
            activity_id=activity_id,
            cause=cause,
        )
        if limit is not None:
            items = items[:limit]

        if not items:
            self.print("No open review items to triage.")
            return self.counters

        try:
            self._walk(items)
        except KeyboardInterrupt:
            self.print("")
            self.print("Interrupted.")

        self._summary()
        return self.counters

    # -- queue walking ------------------------------------------------------

    def _queue_items(
        self,
        *,
        category: str | None,
        severity: str | None,
        activity_id: str | None,
        cause: str | None = None,
    ) -> list:
        items = self.writer.review_items(
            status="open",
            category=category,
            severity=severity,
        )
        if activity_id is not None:
            items = [
                item for item in items if item["activity_id"] == activity_id
            ]
        if cause is not None:
            items = [
                item
                for item in items
                if item["category"] == CONFLICT
                and (item_cause(item) or UNCLASSIFIED) == cause
            ]
        return items

    def _walk(self, items: list) -> None:
        total = len(items)

        for position, queued in enumerate(items, start=1):
            item = self.writer.review_item(queued["id"])
            if item is None or item["status"] != "open":
                continue

            self._show_header(item, position, total)
            keep_working = True
            while keep_working:
                keep_working = not self._dispatch(item)

    def _show_header(self, item, position: int, total: int) -> None:
        self.print("")
        self.print(f"Review {position}/{total}")
        self.print(_format_summary_line(item))

        activity_id = item["activity_id"]
        if activity_id:
            self.print(f"  activity {activity_id}")
            for line in self._activity_header_lines(activity_id):
                self.print(line)
        else:
            candidates = self._candidates(item)
            if candidates:
                names = ", ".join(
                    candidate[0] for candidate in candidates
                )
                self.print(f"  candidates: {names}")
            else:
                self.print("  record-level item (no activity linked yet)")

        cause = item_cause(item)
        if cause:
            note = item_context(item).get("cause_note")
            self.print(
                f"  cause {cause}" + (f": {note}" if note else "")
            )

        if self.pending_note:
            self.print(f"  note pending: {self.pending_note}")
        self.print("  " + self._keys_line(item) + " >")

    def _keys_line(self, item) -> str:
        keys = []
        if item["category"] == CONFLICT:
            keys.append("(v) pick value")
        if item["category"] == WORKOUT_CLASSIFICATION:
            keys.append("(k) classify")
        if self._candidates(item):
            keys.append(f"(1-{len(self._candidates(item))}) choose")
        keys.extend(["(i)nspect", "(o)pen"])
        if self._intervals_url(item):
            keys.append("(ci) Intervals")
        if self._garmin_url(item):
            keys.append("(cg) Garmin")
        if item["activity_id"] and self._intervals_url(item):
            keys.append("(t)rust Intervals")
        keys.extend(
            [
                "(e)nter value",
                "(d)elete",
                "(r)esolve",
                "(x)ignore",
                "(n)ote",
                "(s)kip",
                "(h)elp",
                "(q)uit",
            ]
        )
        return "  ".join(keys)

    # -- dispatch -----------------------------------------------------------

    def _dispatch(self, item) -> bool:
        """Handle one keypress. True = consume the item, move on."""
        try:
            answer = self.read("")
        except EOFError:
            answer = "s"

        answer = answer.strip().lower()

        if answer in ("s", "skip", ""):
            self._count("skipped")
            return True

        if answer in ("x", "ignore"):
            self._close(item, "ignored", note="triage: ignored")
            return True

        if answer in ("r", "f"):
            self._close(item, "resolved", note="triage: resolved")
            return True

        if answer == "d":
            return self._delete(item)

        if answer == "i":
            self._inspect(item)
            return False

        if answer == "v":
            return self._pick_value(item)

        if answer == "k":
            return self._classify_workout(item)

        if answer == "t":
            return self._force_intervals(item)

        if answer == "o":
            self._open(item)
            return False

        if answer == "ci":
            self._copy_url(item, "intervals")
            return False

        if answer == "cg":
            self._copy_url(item, "garmin")
            return False

        if answer == "c":
            self.print("  use ci (Intervals) or cg (Garmin)")
            return False

        if answer == "e":
            return self._edit(item)

        if answer == "n":
            self._ask_note()
            return False

        if answer == "h":
            self.print(KEYS_HELP)
            return False

        if answer == "q":
            raise KeyboardInterrupt

        candidates = self._candidates(item)
        if answer.isdigit() and candidates:
            index = int(answer)
            if 1 <= index <= len(candidates):
                self._link_candidate(item, index - 1)
                return True
            self.print(f"  candidate {index} out of range")
            return False

        self.print("  unknown key — (h) for help, Enter to skip")
        return False

    # -- actions ------------------------------------------------------------

    def _close(self, item, status: str, *, note: str) -> None:
        self.writer.set_review_status(
            item["id"],
            status,
            note=self.pending_note or note,
        )
        self.writer.connection.commit()
        self.pending_note = ""
        self._count("resolved" if status == "resolved" else "ignored")
        self.print(f"  #{item['id']} {status}")

    def _pick_value(self, item) -> bool:
        """Field conflict: choose which source's value stands.

        Either choice takes manual ownership of the field so no future
        reimport can re-open the same disagreement.
        """
        if item["category"] != CONFLICT:
            self.print("  this item is not a field conflict")
            return False

        try:
            context = json.loads(item["context_json"] or "{}")
        except ValueError:
            context = {}
        field = context.get("field")
        current = context.get("current") or {}
        incoming = context.get("incoming") or {}
        if not field:
            self.print("  no field in this conflict item")
            return False

        self.print(f"  field {field} — which value stands?")
        self.print(
            f"    1) {current.get('source', '?')}: "
            f"{format_field(field, current.get('value'))}  "
            "(current, already canonical)"
        )
        self.print(
            f"    2) {incoming.get('source', '?')}: "
            f"{format_field(field, incoming.get('value'))}"
        )
        try:
            answer = self.read("  pick (1/2, blank=cancel): ").strip()
        except EOFError:
            return False

        if answer == "1":
            self._apply_conflict_choice(
                item,
                field,
                current.get("value"),
                "picked current value",
            )
            return True

        if answer == "2":
            self._apply_conflict_choice(
                item,
                field,
                incoming.get("value"),
                "picked incoming value",
            )
            return True

        self.print("  cancelled")
        return False

    def _apply_conflict_choice(
        self,
        item,
        field: str,
        value: object,
        note: str,
    ) -> None:
        try:
            application = apply_manual_edit(
                self.writer,
                activity_id=item["activity_id"],
                field=field,
                value=value,
                resolve_item_id=item["id"],
                note=f"triage: {note}",
            )
        except ValueError as exc:
            self.print(f"  error: {exc}")
            return

        self.writer.connection.commit()
        self._count("picked_value")
        self.print(f"  {application.describe()}")
        self.print(f"  resolved #{item['id']}")
        if not application.okay:
            self.print(
                f"  quality: still flagged — {application.describe_findings()}"
            )

    def _classify_workout(self, item) -> bool:
        """Workout classification: pick a proposal, merge, or type a set.

        The decision is written as manual methods/targets, so no reimport or
        backfill can overwrite it.
        """
        if item["category"] != WORKOUT_CLASSIFICATION:
            self.print("  this item is not a workout classification")
            return False

        context = item_context(item)
        classifier_methods = list(context.get("classifier_methods") or [])
        classifier_targets = list(context.get("classifier_targets") or [])
        sheet_methods = list(context.get("sheet_methods") or [])
        sheet_targets = list(context.get("sheet_targets") or [])
        code = context.get("sheet_code") or "-"

        self.print(
            "  classifier: "
            + _format_sets(classifier_methods, classifier_targets)
        )
        self.print(
            f"  sheet ({code}): "
            + _format_sets(sheet_methods, sheet_targets)
        )
        self.print(
            "  1) classifier  2) sheet  (m)erge  (n)one  "
            "(3) manual  (blank=cancel)"
        )

        try:
            answer = self.read("  pick: ").strip().lower()
        except EOFError:
            return False

        if answer == "1":
            methods, targets, label = (
                classifier_methods,
                classifier_targets,
                "classifier",
            )
        elif answer == "2":
            methods, targets, label = sheet_methods, sheet_targets, "sheet"
        elif answer == "m":
            methods = sorted(set(classifier_methods) | set(sheet_methods))
            targets = sorted(set(classifier_targets) | set(sheet_targets))
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

        self.writer.replace_activity_workout_methods(
            item["activity_id"],
            methods,
            source="manual",
            is_manual=True,
        )
        self.writer.replace_activity_workout_targets(
            item["activity_id"],
            targets,
            source="manual",
            is_manual=True,
        )
        self.writer.set_review_status(
            item["id"],
            "resolved",
            note=self.pending_note or f"triage: classification {label}",
        )
        self.writer.connection.commit()
        self.pending_note = ""
        self._count("classified")
        self.print(f"  {label}: " + _format_sets(methods, targets))
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

    def _delete(self, item) -> bool:
        activity_id = item["activity_id"]

        if not activity_id:
            candidates = self._candidates(item)
            if not candidates:
                self.print("  nothing to delete for this item")
                return False

            try:
                answer = self.read(
                    f"  exclude candidate (1-{len(candidates)}, "
                    "blank=cancel): "
                ).strip()
            except EOFError:
                return False

            if not answer.isdigit() or not (
                1 <= int(answer) <= len(candidates)
            ):
                self.print("  cancelled")
                return False

            activity_id = candidates[int(answer) - 1][0]

        if not self._confirm(
            f'  delete "{activity_id}"? (hidden from reports, reimports '
            "skip it) [y/N]: "
        ):
            self.print("  cancelled")
            return False

        resolved = self.writer.exclude_activity(
            activity_id,
            resolve_note=self.pending_note or "triage: excluded",
        )
        self.writer.connection.commit()
        self.pending_note = ""
        self._count("excluded")
        self.print(f"  excluded {activity_id}")
        self.print(f"  review items resolved: {resolved}")
        return True

    def _confirm(self, prompt: str) -> bool:
        try:
            answer = self.read(prompt).strip().lower()
        except EOFError:
            return False
        return answer in ("y", "yes")

    def _inspect(self, item) -> None:
        activity_id = item["activity_id"]
        if activity_id:
            for line in self._activity_lines(activity_id):
                if line:
                    self.print(line)
            for source in self._activity_sources(activity_id):
                self.print(
                    f"  source {source['source']}: "
                    f"{(source['external_id'] or '')[:40]}"
                    + (f"  ({source['raw_path']})" if source["raw_path"] else "")
                )
        else:
            for line in self._candidate_lines(item):
                self.print(line)

        self.print(f"  detail: {item['detail']}")
        try:
            context = json.loads(item["context_json"] or "{}")
        except ValueError:
            context = {}
        if context:
            self.print("  context:")
            self.print(
                json.dumps(context, indent=2, ensure_ascii=False)
            )

    def _activity_header_lines(self, activity_id: str) -> list[str]:
        row = self.writer.connection.execute(
            """
            SELECT sport, description, duration_s, distance_m
            FROM activities WHERE id = ?
            """,
            (activity_id,),
        ).fetchone()
        if row is None:
            return ["  (missing from database)"]

        lines = []
        metrics = _activity_metrics(
            row["sport"],
            row["duration_s"],
            row["distance_m"],
        )
        if metrics:
            lines.append(f"  {metrics}")

        description = _one_line(row["description"])
        if description:
            lines.append(f"  description: {description}")

        return lines

    def _activity_lines(self, activity_id: str) -> list[str]:
        row = self.writer.connection.execute(
            """
            SELECT local_date, sport, name, description,
                   duration_s, elapsed_s, distance_m, excluded_at
            FROM activities WHERE id = ?
            """,
            (activity_id,),
        ).fetchone()
        if row is None:
            return [f"  activity {activity_id} (missing from database)"]

        pace = _pace_label(
            row["sport"],
            row["duration_s"],
            row["distance_m"],
        )
        distance = format_distance_m(row["distance_m"])
        if pace:
            distance = f"{distance}   {pace}"

        lines = [
            f"  sport: {row['sport'] or '-'}   "
            f"date: {row['local_date'] or '-'}",
        ]
        if row["name"]:
            lines.append(f"  name: {row['name']}")
        lines.append(
            f"  duration: {format_duration_s(row['duration_s'])}   "
            f"elapsed: {format_duration_s(row['elapsed_s'])}"
        )
        lines.append(f"  distance: {distance}")

        description = _one_line(row["description"], limit=200)
        if description:
            lines.append(f"  description: {description}")

        if row["excluded_at"]:
            lines.append("  [excluded]")
        return lines

    def _activity_sources(self, activity_id: str) -> list:
        return self.writer.connection.execute(
            """
            SELECT sr.source, sr.external_id, sr.record_type, sr.raw_path
            FROM activity_sources als
            JOIN source_records sr ON sr.id = als.source_record_id
            WHERE als.activity_id = ?
            ORDER BY als.is_primary DESC, sr.source
            """,
            (activity_id,),
        ).fetchall()

    def _open(self, item) -> None:
        urls = [
            url
            for url in (
                self._intervals_url(item),
                self._garmin_url(item),
            )
            if url
        ]
        if not urls:
            self.print("  no web link available")
            return

        for url in urls:
            self.open_url(url)
            self.print(f"  opened {url}")
        self._count("opened")

    def _copy_url(self, item, kind: str) -> None:
        if kind == "intervals":
            url = self._intervals_url(item)
            label = "Intervals"
        else:
            url = self._garmin_url(item)
            label = "Garmin"

        if url is None:
            self.print(f"  no {label} activity linked to this item")
            return

        tool = self.copy(url)
        self._count("copied")
        self.print(f"  copied {url}" + (f" (via {tool})" if tool else ""))

    def _intervals_url(self, item) -> str | None:
        return intervals_url(self.writer.connection, item)

    def _garmin_url(self, item) -> str | None:
        activity_id = item["activity_id"]
        if not activity_id:
            return None

        if activity_id not in self._garmin_urls:
            if self._garmin_index is None:
                self._garmin_index = garmin_manifest_index(
                    self.writer.connection
                )
            self._garmin_urls[activity_id] = garmin_url(
                self.writer.connection,
                item,
                index=self._garmin_index,
            )
        return self._garmin_urls[activity_id]

    def _default_reimport(self, activity_id: str):
        external_id = intervals_activity_id(
            self.writer.connection,
            activity_id,
        )
        if external_id is None:
            raise ValueError("no Intervals activity linked")

        from .intervals import IntervalsImporter

        return IntervalsImporter(self.writer.connection).import_activity(
            external_id,
            force=True,
        )

    def _force_intervals(self, item) -> bool:
        """Re-import the linked Intervals activity and take field ownership."""
        activity_id = item["activity_id"]
        if not activity_id:
            self.print("  no activity linked to this item")
            return False

        external_id = intervals_activity_id(
            self.writer.connection,
            activity_id,
        )
        if external_id is None:
            self.print("  no Intervals activity linked to this item")
            return False

        if not self._confirm(
            f"  re-import {external_id} from Intervals and take ownership "
            "of its changed fields? [y/N]: "
        ):
            self.print("  cancelled")
            return False

        before = self._field_sources(activity_id)
        try:
            summary = self.reimport(activity_id)
        except Exception as exc:
            self.print(f"  re-import failed: {exc}")
            return False

        if getattr(summary, "activities_imported", 1) == 0:
            self.print("  Intervals did not import an activity")
            return False

        after = self._field_sources(activity_id)
        changed = []
        owned = 0
        for field in sorted(after):
            old_entry = before.get(field)
            new_entry = after[field]
            old_value = _decode_field_value(old_entry)
            new_value = _decode_field_value(new_entry)
            if old_value != new_value:
                changed.append(
                    (field, old_value, new_value, new_entry[0])
                )
            if old_entry is None or old_entry[0] != new_entry[0]:
                owned += 1

        resolved, remaining = self._resolve_intervals_conflicts(activity_id)
        findings = refresh_activity_quality(
            self.writer,
            activity_id=activity_id,
            resolve_note=self.pending_note or "triage: Intervals re-import",
        )
        self.writer.connection.commit()
        self.pending_note = ""
        self._count("reimported")

        self.print(
            f"  re-imported {external_id}; "
            f"{len(changed)} field(s) changed, "
            f"{owned} ownership transfer(s)"
        )
        for field, old_value, new_value, source in changed:
            self.print(
                f"    {field}: {format_field(field, old_value)} → "
                f"{format_field(field, new_value)} ({source})"
            )

        if resolved:
            self.print(f"  resolved {resolved} field conflict(s)")
        if remaining:
            self.print(f"  {remaining} field conflict(s) still open")
        if findings:
            self.print(
                "  quality: still flagged — "
                + "; ".join(
                    f"{finding.rule}: {finding.detail}"
                    for finding in findings
                )
            )
        else:
            self.print("  quality: ok")
        return True

    def _field_sources(self, activity_id: str) -> dict:
        rows = self.writer.connection.execute(
            """
            SELECT field_name, source, value_json, is_manual
            FROM activity_field_sources
            WHERE activity_id = ?
            """,
            (activity_id,),
        ).fetchall()
        return {
            row["field_name"]: (
                row["source"],
                row["value_json"],
                row["is_manual"],
            )
            for row in rows
        }

    def _resolve_intervals_conflicts(
        self,
        activity_id: str,
    ) -> tuple[int, int]:
        """Resolve conflicts on fields Intervals now owns."""
        intervals_fields = {
            row["field_name"]
            for row in self.writer.connection.execute(
                """
                SELECT field_name FROM activity_field_sources
                WHERE activity_id = ? AND source = 'intervals'
                """,
                (activity_id,),
            )
        }

        resolved = 0
        remaining = 0
        for conflict in self.writer.review_items(
            category=CONFLICT,
            status="open",
        ):
            if conflict["activity_id"] != activity_id:
                continue

            try:
                context = json.loads(conflict["context_json"] or "{}")
            except ValueError:
                context = {}

            if context.get("field") not in intervals_fields:
                remaining += 1
                continue

            self.writer.set_review_status(
                conflict["id"],
                "resolved",
                note=self.pending_note or "triage: Intervals re-import",
            )
            resolved += 1
        return resolved, remaining

    def _ask_note(self) -> None:
        try:
            note = self.read("  note: ").strip()
        except EOFError:
            return
        if not note:
            return
        self.pending_note = note
        self.print("  note will be attached to the next r/x/d action")

    # -- edit flow ----------------------------------------------------------

    def _edit(self, item) -> bool:
        if not item["activity_id"]:
            self.print(
                "  this item has no linked activity — use 1-9 to link a "
                "candidate first, then re-import"
            )
            return False

        field = self._read_field(item)
        if field is None:
            self.print("  cancelled")
            return False

        prompt, parse = _VALUE_PROMPTS[field]
        try:
            value = self._read_value(prompt, parse)
        except AbortEdit:
            self.print("  cancelled")
            return False

        activity_id = item["activity_id"]
        try:
            application = apply_manual_edit(
                self.writer,
                activity_id=activity_id,
                field=field,
                value=value,
                resolve_item_id=item["id"],
            )
        except ValueError as exc:
            self.print(f"  error: {exc}")
            return False

        self.writer.connection.commit()
        self._count("edited")
        self.print(f"  {application.describe()}")
        self.print(f"  resolved #{item['id']}")
        if application.okay:
            self.print("  quality: ok")
        else:
            self.print(
                f"  quality: still flagged — {application.describe_findings()}"
            )
        return True

    def _read_field(self, item) -> str | None:
        default = "duration_s"
        try:
            context = json.loads(item["context_json"] or "{}")
        except ValueError:
            context = {}
        default = DEFAULT_FIELD.get(context.get("rule"), "duration_s")

        for _ in range(3):
            try:
                raw = self.read(
                    f"  field [{_FIELD_LABELS[default]}] "
                    "(duration/distance/sport; Ctrl-D or blank-value cancels): "
                ).strip().lower()
            except EOFError:
                return None

            if not raw:
                return default

            field = {
                "duration": "duration_s",
                "distance": "distance_m",
                "sport": "sport",
            }.get(raw)

            if field is not None:
                return field
            self.print(f"  unknown field {raw!r}")

        return None

    def _read_value(self, prompt, parse) -> object:
        for _ in range(3):
            try:
                raw = self.read(f"  {prompt}")
            except EOFError:
                raise AbortEdit("aborted")

            raw = raw.strip()
            if not raw:
                raise AbortEdit("aborted")

            try:
                return parse(raw)
            except ValueError as exc:
                self.print(f"  {exc} — try again (blank cancels)")

        raise AbortEdit("value entry failed repeatedly")

    # -- ambiguous matches --------------------------------------------------

    def _link_candidate(self, item, index: int) -> None:
        candidate = self._candidates(item)[index]
        activity_id = candidate[0]
        try:
            self.writer.resolve_review_match(
                item["id"],
                activity_id,
                note=self.pending_note or "triage: linked candidate",
            )
        except ValueError as exc:
            self.print(f"  error: {exc}")
            return

        self.writer.connection.commit()
        self.pending_note = ""
        self._count("linked")
        self.print(f"  linked record → {activity_id}")
        self.print(
            "  re-run the importer for this record to apply its field values"
        )

    def _candidates(self, item) -> list[tuple[str, dict]]:
        try:
            context = json.loads(item["context_json"] or "{}")
        except ValueError:
            return []

        result = []
        for candidate in context.get("candidates") or []:
            activity_id = candidate.get("activity_id")
            if activity_id:
                result.append((activity_id, candidate))
        return result

    def _candidate_lines(self, item) -> list[str]:
        lines = []
        for index, (activity_id, candidate) in enumerate(
            self._candidates(item), start=1
        ):
            row = self.writer.connection.execute(
                "SELECT local_date, sport FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
            summary = (
                f"{row['local_date']} {row['sport']}" if row else "(missing)"
            )
            lines.append(
                f"  {index}) {activity_id[:12]}  {summary}  "
                f"({candidate.get('match_method', '-')}, "
                f"{candidate.get('confidence', '-')})"
            )
        return lines

    def _count(self, label: str) -> None:
        self.counters[label] = self.counters.get(label, 0) + 1

    def _summary(self) -> None:
        remaining = len(
            self._queue_items(
                category=None,
                severity=None,
                activity_id=None,
            )
        )
        parts = [
            f"{count} {label}"
            for label, count in sorted(self.counters.items())
        ]
        self.print("")
        self.print(
            "Triage summary: "
            + (", ".join(parts) if parts else "nothing to do")
        )
        self.print(f"Review items left open: {remaining}")


def _decode_field_value(entry) -> object:
    """Decode a stored ``value_json`` tuple from ``_field_sources``."""
    if entry is None:
        return None
    try:
        return json.loads(entry[1])
    except (TypeError, ValueError):
        return entry[1]
