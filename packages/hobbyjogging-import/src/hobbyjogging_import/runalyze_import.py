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
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from hobbyjogging_core import TrainingWriter
from hobbyjogging_core.sports import NO_DISTANCE_SPORTS

from .matching import ActivityMatcher, MatchCandidate
from .runalyze import RunalyzeApi, RunalyzeClient

SOURCE = "runalyze"
DISTANCE_TOLERANCE_RATIO = 0.05
DISTANCE_TOLERANCE_M = 100.0
DISTANCE_KM_TO_M = 1000.0


@dataclass
class RunalyzeEnrichSummary:
    """Results of one enrichment run."""

    run_id: int | None = None
    dry_run: bool = False
    activities_seen: int = 0
    matched: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    detail_fetches: int = 0
    comments_filled: int = 0
    comments_kept: int = 0
    activities_tagged: int = 0
    tags_written: int = 0
    unmatched_rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


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
        output: str | Path | None = None,
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

            matched = self._match_all(activities, summary)

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
                    "success",
                    records_seen=summary.activities_seen,
                    records_imported=summary.matched,
                    records_skipped=(
                        summary.unmatched
                        + summary.ambiguous
                    ),
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

    # -- matching -----------------------------------------------------------

    def _match_all(
        self,
        activities: list[dict],
        summary: RunalyzeEnrichSummary,
    ) -> dict[str, _Matched]:
        matched: dict[str, _Matched] = {}

        for activity in activities:
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

            detail = self.client.get(f"activity/{external_id}")
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
        f"  matched: {summary.matched}",
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


def _payload_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
