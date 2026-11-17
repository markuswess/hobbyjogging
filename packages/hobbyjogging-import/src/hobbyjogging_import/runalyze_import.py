"""Runalyze enrichment: comments and tags into the canonical database.

Phase 2 imports the fields Runalyze holds that the canonical record has no
better source for:

- the activity ``note`` fills ``activities.description`` only when it is blank;
- the activity ``tags`` replace Runalyze's own tag set in ``activity_tags``
  (manual tags survive).

Matching is temporal plus distance, since Runalyze exposes no Garmin activity
id. Timing and distance are never written, and ``name`` is never taken from
Runalyze (its title is a Garmin auto-title). Unmatched rows are reported for
the later activity phase; they are not created here.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from hobbyjogging_core import TrainingWriter
from hobbyjogging_core.sports import NO_DISTANCE_SPORTS

from .matching import ActivityMatcher, MatchCandidate
from .runalyze import RunalyzeApi, RunalyzeClient, RunalyzeRateLimitError

SOURCE = "runalyze"
DISTANCE_TOLERANCE_RATIO = 0.05
DISTANCE_TOLERANCE_M = 100.0
DISTANCE_KM_TO_M = 1000.0
WAIT_BUFFER_S = 5.0
DEFAULT_WAIT_S = 300.0


@dataclass
class RunalyzeEnrichSummary:
    """Results of one enrichment run."""

    run_id: int | None = None
    dry_run: bool = False
    activities_seen: int = 0
    processed: int = 0
    not_processed: int = 0
    matched: int = 0
    already_enriched: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    detail_fetches: int = 0
    comments_filled: int = 0
    comments_kept: int = 0
    activities_tagged: int = 0
    tags_written: int = 0
    unmatched_rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stopped_reason: str = ""
    stopped_retry_after_s: int | None = None


@dataclass
class _Matched:
    activity_id: str
    confidence: float | None
    external_id: str
    note: str = ""
    tags: set[str] = field(default_factory=set)


class RunalyzeEnricher:
    """Enrich matched activities with Runalyze comments and tags."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        client: RunalyzeApi | None = None,
    ):
        self.connection = connection
        self.client = client or RunalyzeClient()
        self.writer = TrainingWriter(connection)
        self.matcher = ActivityMatcher(connection)

    def enrich(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        per_page: int = 100,
        dry_run: bool = False,
        refresh: bool = False,
        wait: bool = False,
        output: str | Path | None = None,
    ) -> RunalyzeEnrichSummary:
        """Enrich comments/tags, optionally across rate-limit windows.

        ``wait`` sleeps until the reset after a 429 and resumes with the rows
        that are still unprocessed; it needs the stored-detail skip, so it
        cannot be combined with ``refresh`` or ``dry_run``.
        """
        if wait and dry_run:
            raise ValueError("wait cannot be combined with dry_run")
        if wait and refresh:
            raise ValueError("wait cannot be combined with refresh")

        if wait:
            return self._enrich_until_complete(
                start=start,
                end=end,
                limit=limit,
                per_page=per_page,
                output=output,
            )

        return self._enrich_once(
            start=start,
            end=end,
            limit=limit,
            per_page=per_page,
            dry_run=dry_run,
            refresh=refresh,
            output=output,
        )

    def _enrich_once(
        self,
        *,
        start: date | None,
        end: date | None,
        limit: int | None,
        per_page: int,
        dry_run: bool,
        refresh: bool,
        output: str | Path | None,
    ) -> RunalyzeEnrichSummary:
        summary = RunalyzeEnrichSummary(dry_run=dry_run)

        if not dry_run:
            summary.run_id = self.writer.start_import_run(
                SOURCE,
                {
                    "enrich": True,
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                    "limit": limit,
                    "refresh": refresh,
                },
            )

        try:
            activities = self.client.activities(
                start,
                end,
                per_page=per_page,
            )
            if limit is not None:
                activities = activities[:limit]
            summary.activities_seen = len(activities)

            stored = self._stored_details()
            matched = self._match_all(
                activities,
                summary,
                stored=stored,
                refresh=refresh,
            )
            summary.not_processed = max(
                0,
                summary.activities_seen - summary.processed,
            )

            if not dry_run:
                with self.connection:
                    self._write(matched, summary)
            else:
                self._count_without_writing(matched, summary)

            if output is not None:
                _write_unmatched(Path(output), summary.unmatched_rows)

            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "partial" if summary.stopped_reason else "success",
                    records_seen=summary.activities_seen,
                    records_imported=summary.matched,
                    records_skipped=(
                        summary.unmatched
                        + summary.ambiguous
                        + summary.already_enriched
                        + summary.not_processed
                    ),
                    error=summary.stopped_reason or None,
                )
            return summary

        except Exception as exc:
            self.connection.rollback()
            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "failed",
                    records_seen=summary.activities_seen,
                    records_imported=summary.matched,
                    records_skipped=(
                        summary.unmatched
                        + summary.ambiguous
                    ),
                    error=str(exc),
                )
            raise

    def _enrich_until_complete(
        self,
        *,
        start: date | None,
        end: date | None,
        limit: int | None,
        per_page: int,
        output: str | Path | None,
    ) -> RunalyzeEnrichSummary:
        """Repeat the range across windows until everything is done."""
        aggregate = RunalyzeEnrichSummary(dry_run=False)

        while True:
            try:
                summary = self._enrich_once(
                    start=start,
                    end=end,
                    limit=limit,
                    per_page=per_page,
                    dry_run=False,
                    refresh=False,
                    output=output,
                )
            except RunalyzeRateLimitError as exc:
                delay = _wait_seconds(exc.retry_after_s)
                print(
                    "  rate limit before the range; "
                    f"sleeping {delay:.0f}s",
                    flush=True,
                )
                time.sleep(delay)
                continue

            aggregate.activities_seen = summary.activities_seen
            aggregate.processed = summary.processed
            aggregate.not_processed = summary.not_processed
            aggregate.unmatched = summary.unmatched
            aggregate.ambiguous = summary.ambiguous
            aggregate.already_enriched = summary.already_enriched
            aggregate.unmatched_rows = summary.unmatched_rows
            aggregate.run_id = summary.run_id
            aggregate.matched += summary.matched
            aggregate.detail_fetches += summary.detail_fetches
            aggregate.comments_filled += summary.comments_filled
            aggregate.comments_kept += summary.comments_kept
            aggregate.activities_tagged += summary.activities_tagged
            aggregate.tags_written += summary.tags_written
            aggregate.errors.extend(
                error
                for error in summary.errors
                if not error.startswith("Runalyze rate limit")
            )

            if not summary.stopped_reason:
                aggregate.stopped_reason = ""
                aggregate.stopped_retry_after_s = None
                return aggregate

            delay = _wait_seconds(summary.stopped_retry_after_s)
            print(
                f"  rate limit: {summary.not_processed} not processed; "
                f"sleeping {delay:.0f}s",
                flush=True,
            )
            time.sleep(delay)

    # -- matching -----------------------------------------------------------

    def _match_all(
        self,
        activities: list[dict],
        summary: RunalyzeEnrichSummary,
        *,
        stored: dict[str, tuple[dict, str | None]],
        refresh: bool,
    ) -> dict[str, _Matched]:
        matched: dict[str, _Matched] = {}

        for activity in activities:
            summary.processed += 1
            if not isinstance(activity, dict):
                continue

            activity_id, reason, confidence = self._match(activity)
            external_id = str(activity.get("id") or "")

            if activity_id is None:
                if reason == "ambiguous_match":
                    summary.ambiguous += 1
                else:
                    summary.unmatched += 1

                summary.unmatched_rows.append(
                    _unmatched_row(activity, reason)
                )
                continue

            if not refresh and self._already_enriched(
                stored,
                external_id,
                activity.get("edited_at"),
                activity_id,
            ):
                summary.already_enriched += 1
                continue

            try:
                detail = self.client.get(f"activity/{external_id}")
            except RunalyzeRateLimitError as exc:
                summary.stopped_reason = str(exc)
                summary.stopped_retry_after_s = exc.retry_after_s
                summary.errors.append(str(exc))
                break

            summary.detail_fetches += 1

            if not detail.ok or not isinstance(detail.payload, dict):
                summary.errors.append(
                    f"{external_id}: detail request failed "
                    f"(HTTP {detail.status})"
                )
                continue

            payload = detail.payload
            note = str(payload.get("note") or "").strip()
            tags = _tag_names(payload.get("tags"))

            summary.matched += 1
            entry = matched.get(activity_id)
            if entry is None:
                entry = _Matched(
                    activity_id=activity_id,
                    confidence=confidence,
                    external_id=external_id,
                )
                matched[activity_id] = entry
            if note and not entry.note:
                entry.note = note
            entry.tags |= tags

            if not summary.dry_run:
                self._record_source(activity_id, external_id, payload, summary)

        return matched

    def _match(
        self,
        activity: dict,
    ) -> tuple[str | None, str, float | None]:
        started_at = _start_utc(activity)
        if started_at is None:
            return None, "no_start", None

        duration = _number(activity.get("duration")) or 0.0
        elapsed = _number(activity.get("elapsed_time")) or duration
        if duration <= 0 and elapsed <= 0:
            return None, "no_duration", None

        matches = self.matcher.find(
            started_at_utc=started_at,
            source=SOURCE,
            elapsed_s=elapsed,
            duration_s=duration,
        )
        if not matches:
            return None, "no_temporal_match", None

        distance_m = _distance_m(activity)
        viable = [
            match
            for match in matches
            if self._distance_ok(distance_m, match)
        ]

        if not viable:
            return None, "distance_mismatch", None
        if len(viable) > 1:
            return None, "ambiguous_match", None

        match = viable[0]
        return match.activity_id, "", match.confidence

    def _already_enriched(
        self,
        stored: dict[str, tuple[dict, str | None]],
        external_id: str,
        edited_at: object,
        activity_id: str,
    ) -> bool:
        """True when the stored detail is current and linked to this activity.

        A re-run after a rate-limit stop then skips the rows already processed
        instead of restarting at the first activity.
        """
        entry = stored.get(external_id)
        if entry is None:
            return False

        payload, linked_activity = entry
        if linked_activity != activity_id:
            return False

        current = _edited_at(edited_at)
        if current is None:
            return False
        return _edited_at(payload.get("edited_at")) == current

    def _stored_details(self) -> dict[str, tuple[dict, str | None]]:
        rows = self.connection.execute(
            """
            SELECT sr.external_id, sr.payload_json, als.activity_id
            FROM source_records sr
            LEFT JOIN activity_sources als
                ON als.source_record_id = sr.id
            WHERE sr.source = ? AND sr.record_type = 'activity'
            """,
            (SOURCE,),
        ).fetchall()

        stored: dict[str, tuple[dict, str | None]] = {}
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue

            external_id = str(row["external_id"])
            linked = row["activity_id"]
            entry = stored.get(external_id)
            if entry is None or (entry[1] is None and linked is not None):
                stored[external_id] = (payload, linked)

        return stored

    def _distance_ok(
        self,
        runalyze_distance_m: float | None,
        match: MatchCandidate,
    ) -> bool:
        if runalyze_distance_m is None:
            return True

        row = self.connection.execute(
            "SELECT sport, distance_m FROM activities WHERE id = ?",
            (match.activity_id,),
        ).fetchone()
        if row is None:
            return False
        if row["sport"] in NO_DISTANCE_SPORTS:
            return True

        stored_distance_m = row["distance_m"] or 0.0
        if stored_distance_m <= 0:
            return True

        tolerance = max(
            DISTANCE_TOLERANCE_M,
            DISTANCE_TOLERANCE_RATIO
            * max(runalyze_distance_m, stored_distance_m),
        )
        return (
            abs(runalyze_distance_m - stored_distance_m) <= tolerance
        )

    # -- writing ------------------------------------------------------------

    def _record_source(
        self,
        activity_id: str,
        external_id: str,
        payload: dict,
        summary: RunalyzeEnrichSummary,
    ) -> None:
        payload_json = _payload_json(payload)
        source_record_id = self.writer.upsert_source_record(
            source=SOURCE,
            record_type="activity",
            external_id=external_id,
            checksum=_checksum(payload_json),
            payload_json=payload_json,
            import_run_id=summary.run_id,
        )
        self.writer.link_activity_source(
            activity_id,
            source_record_id,
            match_method="temporal_distance",
        )

    def _count_without_writing(
        self,
        matched: dict[str, _Matched],
        summary: RunalyzeEnrichSummary,
    ) -> None:
        for entry in matched.values():
            self._apply_one(entry, summary, dry_run=True)

    def _write(
        self,
        matched: dict[str, _Matched],
        summary: RunalyzeEnrichSummary,
    ) -> None:
        for entry in matched.values():
            self._apply_one(entry, summary, dry_run=False)

    def _apply_one(
        self,
        entry: _Matched,
        summary: RunalyzeEnrichSummary,
        *,
        dry_run: bool,
    ) -> None:
        row = self.connection.execute(
            "SELECT description FROM activities WHERE id = ?",
            (entry.activity_id,),
        ).fetchone()
        if row is None:
            return

        current = str(row["description"] or "")
        if entry.note:
            if current.strip():
                summary.comments_kept += 1
            else:
                summary.comments_filled += 1
                if not dry_run:
                    self.writer.upsert_activity(
                        entry.activity_id,
                        {"description": entry.note},
                        source=SOURCE,
                        source_record_id=_source_id(
                            self.connection,
                            entry.external_id,
                        ),
                    )

        existing = {
            tag["tag"]
            for tag in self.connection.execute(
                """
                SELECT tag FROM activity_tags
                WHERE activity_id = ? AND source = ? AND is_manual = 0
                """,
                (entry.activity_id, SOURCE),
            )
        }
        if existing == entry.tags:
            return

        summary.activities_tagged += 1
        summary.tags_written += len(entry.tags)
        if not dry_run:
            self.writer.replace_activity_tags(
                entry.activity_id,
                sorted(entry.tags),
                source=SOURCE,
                source_record_id=_source_id(
                    self.connection,
                    entry.external_id,
                ),
            )


def format_enrich_summary(summary: RunalyzeEnrichSummary) -> str:
    label = "Runalyze enrich dry run" if summary.dry_run else "Runalyze enrich"
    lines = [
        f"{label}: {summary.activities_seen} activities",
        f"  processed: {summary.processed}",
        f"  not processed: {summary.not_processed}",
        f"  matched: {summary.matched}",
        f"  already enriched: {summary.already_enriched}",
        f"  unmatched: {summary.unmatched}",
        f"  ambiguous: {summary.ambiguous}",
        f"  comments filled: {summary.comments_filled}",
        f"  comments kept (not blank): {summary.comments_kept}",
        f"  activities tagged: {summary.activities_tagged} "
        f"({summary.tags_written} tags)",
        f"  detail requests: {summary.detail_fetches}",
    ]

    for error in summary.errors:
        lines.append(f"  error: {error}")

    if summary.stopped_reason:
        lines.append(f"  stopped: {summary.stopped_reason}")

    if not summary.dry_run:
        lines.append(f"Import run: {summary.run_id}")

    return "\n".join(lines)


def _unmatched_row(activity: dict, reason: str) -> dict:
    return {
        "id": activity.get("id"),
        "date_time": activity.get("date_time"),
        "sport": activity.get("sport_id") or activity.get("sport"),
        "distance_km": activity.get("distance"),
        "duration_s": activity.get("duration"),
        "reason": reason,
    }


def _write_unmatched(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"unmatched": rows}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def _source_id(connection: sqlite3.Connection, external_id: str) -> int | None:
    row = connection.execute(
        """
        SELECT id FROM source_records
        WHERE source = ? AND record_type = 'activity' AND external_id = ?
        """,
        (SOURCE, external_id),
    ).fetchone()
    return row["id"] if row is not None else None


def _start_utc(activity: dict) -> str | None:
    raw = str(activity.get("date_time") or "").strip()
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if moment.tzinfo is None:
        offset = _number(activity.get("timezone_offset"))
        if offset is not None:
            moment = moment.replace(
                tzinfo=timezone(timedelta(minutes=offset))
            )
        else:
            moment = moment.replace(tzinfo=timezone.utc)

    return (
        moment.astimezone(timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _distance_m(activity: dict) -> float | None:
    value = _number(activity.get("distance"))
    if value is None:
        return None
    return value * DISTANCE_KM_TO_M


def _tag_names(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    names = set()
    for tag in value:
        if not isinstance(tag, dict):
            continue
        name = str(tag.get("tag") or "").strip()
        if name:
            names.add(name)
    return names


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _edited_at(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _wait_seconds(retry_after_s: int | None) -> float:
    if retry_after_s is None:
        return DEFAULT_WAIT_S + WAIT_BUFFER_S
    return max(1.0, float(retry_after_s)) + WAIT_BUFFER_S


def _payload_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
