"""Interactive review queue walk (`hobbyjogging-import review triage`).

One open review item at a time, each decision written immediately:

    #1 warn quality/open  2019-01-30  Run  (no timing data: duration is 0 s)
      activity 5d459fa1  fit:2019-01-30_18-02-00.fit
      (i)nspect  (o)pen  (c)opy URL  (e)nter valid time  (d)elete
      (r)esolve  (x)ignore  (n)ote  (s)kip  (h)elp  (q)uit > _
"""

from __future__ import annotations

import json
import webbrowser
from typing import Callable

from hobbyjogging_core import TrainingWriter

from .clipboard import copy_text
from .editing import apply_manual_edit
from .review_cli import _format_summary_line
from .values import parse_distance_m, parse_duration_s, parse_sport

INTERVALS_URL = "https://intervals.icu/activities/{}"

KEYS_HELP = """\
keys:
  (i)nspect        full item detail
  (o)pen           open the Intervals activity in a browser
  (c)opy URL       copy the Intervals activity URL to the clipboard
  (e)nter value    manually edit duration/distance/sport, then re-check
  (d)elete         durably exclude the activity (soft delete)
  (r)esolve        mark handled (activity returns to reports)
  (x)ignore        mark accepted as-is (activity stays in reports)
  (n)ote           attach a note to the next r/x/d action
  1-9              ambiguous match: link to that candidate
  (s)kip / Enter   next item, leave it open
  (h)elp           this text
  (q)uit           stop and print a summary"""

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
    ):
        self.writer = writer
        self.read = read
        self.print = print
        self.open_url = open_url
        self.copy = copy
        self.counters: dict[str, int] = {}
        self.pending_note = ""

    def run(
        self,
        *,
        limit: int | None = None,
        category: str | None = None,
        severity: str | None = None,
        activity_id: str | None = None,
    ) -> dict[str, int]:
        """Walk the open queue. Returns the decision counters."""
        items = self._queue_items(
            category=category,
            severity=severity,
            activity_id=activity_id,
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
        else:
            candidates = self._candidates(item)
            if candidates:
                names = ", ".join(
                    candidate[0] for candidate in candidates
                )
                self.print(f"  candidates: {names}")
            else:
                self.print("  record-level item (no activity linked yet)")

        if self.pending_note:
            self.print(f"  note pending: {self.pending_note}")
        self.print("  " + self._keys_line(item) + " >")

    def _keys_line(self, item) -> str:
        keys = []
        if self._candidates(item):
            keys.append(f"(1-{len(self._candidates(item))}) choose")
        keys.extend(
            [
                "(i)nspect",
                "(o)pen",
                "(c)opy URL",
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

        if answer == "o":
            self._open(item)
            return False

        if answer == "c":
            self._copy_url(item)
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

    def _activity_lines(self, activity_id: str) -> list[str]:
        from .values import format_distance_m, format_duration_s

        row = self.writer.connection.execute(
            """
            SELECT local_date, sport, duration_s, elapsed_s, distance_m,
                   excluded_at
            FROM activities WHERE id = ?
            """,
            (activity_id,),
        ).fetchone()
        if row is None:
            return [f"  activity {activity_id} (missing from database)"]

        return [
            f"  sport: {row['sport'] or '-'}   "
            f"date: {row['local_date'] or '-'}",
            f"  duration: {format_duration_s(row['duration_s'])}   "
            f"elapsed: {format_duration_s(row['elapsed_s'])}",
            f"  distance: {format_distance_m(row['distance_m'])}",
            "  [excluded]" if row["excluded_at"] else "",
        ]

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
        url = self._intervals_url(item)
        if url is None:
            self.print("  no Intervals activity linked to this item")
            return
        self.open_url(url)
        self._count("opened")
        self.print(f"  opened {url}")

    def _copy_url(self, item) -> None:
        url = self._intervals_url(item)
        if url is None:
            self.print("  no Intervals activity linked to this item")
            return
        tool = self.copy(url)
        self._count("copied")
        self.print(f"  copied {url}" + (f" (via {tool})" if tool else ""))

    def _intervals_url(self, item) -> str | None:
        if item["record_source"] == "intervals" and item["external_id"]:
            return INTERVALS_URL.format(item["external_id"])

        activity_id = item["activity_id"]
        if not activity_id:
            return None

        row = self.writer.connection.execute(
            """
            SELECT sr.external_id
            FROM activity_sources als
            JOIN source_records sr ON sr.id = als.source_record_id
            WHERE als.activity_id = ? AND sr.source = 'intervals'
            ORDER BY als.is_primary DESC, sr.id
            LIMIT 1
            """,
            (activity_id,),
        ).fetchone()
        if row is None:
            return None
        return INTERVALS_URL.format(row["external_id"])

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
