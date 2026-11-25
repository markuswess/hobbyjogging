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
from hobbyjogging_core.sports import RUN_SPORTS

from .create_activity import create_activity
from .derive import derive_values
from .matching import MatchPolicy, decide_match
from .metrics import derive_metrics
from .quality import AMBIGUOUS_MATCH, review_fingerprint
from .runalyze import RunalyzeApi, RunalyzeClient, RunalyzeRateLimitError
from .runalyze_types import classification_for_payload

SOURCE = "runalyze"
DISTANCE_KM_TO_M = 1000.0
WAIT_BUFFER_S = 5.0
DEFAULT_WAIT_S = 300.0

# A row the temporal matcher rejects can still be the same session: Runalyze
# may start or stop recording seconds away from the device, and its distance
# comes from the same track. Only a near-identical twin counts as the same
# session — everything else is a review item, never a guess.
EXACT_DURATION_S = 2.0
EXACT_DISTANCE_M = 10.0
EXACT_MATCH_METHOD = "exact_twin"

# A sheet-only activity that mirrors a device row on the same day is a
# duplicate of that session, so it must never be the enrichment target.
DEVICE_SOURCES = ("fit", "intervals")
SAME_SESSION_DURATION_RATIO = 0.05


@dataclass
class RunalyzeEnrichSummary:
    """Results of one enrichment run."""

    run_id: int | None = None
    dry_run: bool = False
    activities_seen: int = 0
    processed: int = 0
    not_processed: int = 0
    matched: int = 0
    refreshed: int = 0
    already_enriched: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    created: int = 0
    ignored: int = 0
    reviews_recorded: int = 0
    already_reviewed: int = 0
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


@dataclass
class _Outcome:
    """What one Runalyze row resolves to: an activity or a review item."""

    activity_id: str | None = None
    reason: str = ""
    confidence: float | None = None
    match_method: str = "temporal_distance"
    candidates: list[dict] = field(default_factory=list)
    suggested_activity_id: str | None = None

    @property
    def reviewed(self) -> bool:
        return self.activity_id is None


@dataclass
class _Review:
    external_id: str
    outcome: _Outcome
    payload: dict


@dataclass(frozen=True)
class _Stored:
    """One stored activity detail and its link, as the skip rule sees it."""

    payload: dict
    activity_id: str | None
    fetched_at: str | None



class RunalyzeEnricher:
    """Enrich matched activities with Runalyze comments and tags."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        client: RunalyzeApi | None = None,
        *,
        create: str = "review",
        workout_type: bool = True,
        trimp: bool = True,
    ):
        if create not in ("create", "review", "ignore"):
            raise ValueError("create must be 'create', 'review' or 'ignore'")
        self.connection = connection
        self.client = client or RunalyzeClient()
        self.writer = TrainingWriter(connection)
        self.create = create
        self.workout_type = workout_type
        self.trimp = trimp

    def enrich(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        per_page: int = 100,
        dry_run: bool = False,
        refresh: bool = False,
        refresh_before: str | None = None,
        wait: bool = False,
        output: str | Path | None = None,
        ids: list[str] | None = None,
    ) -> RunalyzeEnrichSummary:
        """Enrich comments/tags, optionally across rate-limit windows.

        ``wait`` sleeps until the reset after a 429 and resumes with the rows
        that are still unprocessed; it needs the stored-detail skip, so it
        cannot be combined with ``refresh`` or ``dry_run``.

        ``refresh_before`` is the sweep: it re-reads every detail whose stored
        payload was fetched before that moment. A refreshed row carries a
        newer ``fetched_at``, so a ``--wait`` sweep advances window by window
        and stops on its own — a bare ``refresh`` under ``wait`` would refetch
        the same prefix forever.
        """
        if wait and dry_run:
            raise ValueError("wait cannot be combined with dry_run")
        if wait and refresh:
            raise ValueError(
                "wait cannot be combined with refresh; "
                "use refresh_before for a sweep"
            )
        if refresh and refresh_before:
            raise ValueError(
                "refresh and refresh_before are exclusive"
            )
        if ids and wait:
            raise ValueError("ids cannot be combined with wait")
        if ids and refresh_before:
            raise ValueError(
                "ids cannot be combined with refresh_before"
            )

        cutoff = (
            _refresh_cutoff(refresh_before)
            if refresh_before
            else None
        )

        if ids:
            return self.enrich_ids(
                ids,
                dry_run=dry_run,
                refresh=refresh,
                output=output,
            )

        if wait:
            return self._enrich_until_complete(
                start=start,
                end=end,
                limit=limit,
                per_page=per_page,
                refresh_before=cutoff,
                output=output,
            )

        return self._enrich_once(
            start=start,
            end=end,
            limit=limit,
            per_page=per_page,
            dry_run=dry_run,
            refresh=refresh,
            refresh_before=cutoff,
            output=output,
        )

    def enrich_ids(
        self,
        ids: list[str],
        *,
        dry_run: bool = False,
        refresh: bool = False,
        output: str | Path | None = None,
    ) -> RunalyzeEnrichSummary:
        """Enrich a named set of activities without reading the collection.

        This is the repair path for details whose fetch failed (HTTP 5xx), and
        the way to re-evaluate a reviewed row after a change on the Runalyze
        side: the detail payload carries the date, duration and distance the
        matcher needs, so one request per id is enough. ``refresh`` re-applies
        a stored row instead of skipping it as already processed.
        """
        activities: list[dict] = []
        details: dict[str, dict] = {}
        errors: list[str] = []

        for external_id in ids:
            key = str(external_id)
            try:
                response = self.client.get(f"activity/{key}")
            except RunalyzeRateLimitError as exc:
                errors.append(str(exc))
                break
            if not response.ok or not isinstance(response.payload, dict):
                errors.append(
                    f"{key}: detail request failed "
                    f"(HTTP {response.status})"
                )
                continue

            payload = response.payload
            details[key] = payload
            activities.append(
                {
                    "id": payload.get("id", key),
                    "date_time": payload.get("date_time"),
                    "duration": payload.get("duration"),
                    "elapsed_time": payload.get("elapsed_time"),
                    "distance": payload.get("distance"),
                }
            )

        summary = self._enrich_once(
            start=None,
            end=None,
            limit=None,
            per_page=100,
            dry_run=dry_run,
            refresh=refresh,
            output=output,
            activities=activities,
            details=details,
        )
        summary.detail_fetches += len(details)
        summary.errors[:0] = errors
        return summary

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
        refresh_before: str | None = None,
        activities: list[dict] | None = None,
        details: dict[str, dict] | None = None,
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
                    "refresh_before": refresh_before,
                },
            )

        try:
            if activities is None:
                activities = self.client.activities(
                    start,
                    end,
                    per_page=per_page,
                )
            if limit is not None:
                activities = activities[:limit]
            summary.activities_seen = len(activities)

            stored = self._stored_details()
            matched, reviews = self._match_all(
                activities,
                summary,
                stored=stored,
                refresh=refresh,
                refresh_before=refresh_before,
                details=details,
            )
            summary.not_processed = max(
                0,
                summary.activities_seen - summary.processed,
            )

            if not dry_run:
                with self.connection:
                    self._write(matched, reviews, summary)
            else:
                self._count_without_writing(matched, reviews, summary)

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
        refresh_before: str | None = None,
        output: str | Path | None,
    ) -> RunalyzeEnrichSummary:
        """Repeat the range across windows until everything is done."""
        aggregate = RunalyzeEnrichSummary(dry_run=False)

        activities: list[dict] | None = None
        while activities is None:
            try:
                activities = self.client.activities(
                    start,
                    end,
                    per_page=per_page,
                )
            except RunalyzeRateLimitError as exc:
                delay = _wait_seconds(exc.retry_after_s)
                print(
                    "  rate limit before the range; "
                    f"sleeping {delay:.0f}s",
                    flush=True,
                )
                time.sleep(delay)

        if limit is not None:
            activities = activities[:limit]

        while True:
            summary = self._enrich_once(
                start=start,
                end=end,
                limit=limit,
                per_page=per_page,
                dry_run=False,
                refresh=False,
                refresh_before=refresh_before,
                output=output,
                activities=activities,
            )

            aggregate.activities_seen = summary.activities_seen
            aggregate.processed = summary.processed
            aggregate.not_processed = summary.not_processed
            aggregate.unmatched = summary.unmatched
            aggregate.ambiguous = summary.ambiguous
            aggregate.already_enriched = summary.already_enriched
            aggregate.refreshed += summary.refreshed
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
                f"  window: {summary.detail_fetches} details, "
                f"{summary.already_enriched} skipped, "
                f"{summary.not_processed} not processed; "
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
        stored: dict[str, _Stored],
        refresh: bool,
        refresh_before: str | None = None,
        details: dict[str, dict] | None = None,
    ) -> tuple[dict[str, _Matched], list[_Review]]:
        matched: dict[str, _Matched] = {}
        reviews: list[_Review] = []

        for activity in activities:
            summary.processed += 1
            if not isinstance(activity, dict):
                continue

            outcome = self._decide(activity)
            external_id = str(activity.get("id") or "")
            stale = (
                refresh_before is not None
                and _is_stale(stored.get(external_id), refresh_before)
            )

            if (
                not refresh
                and not stale
                and _already_processed(
                    stored,
                    external_id,
                    outcome.activity_id,
                )
            ):
                if outcome.reviewed:
                    summary.already_reviewed += 1
                else:
                    summary.already_enriched += 1
                continue


            payload = details.get(external_id) if details else None
            if payload is None:
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

            if stale:
                summary.refreshed += 1

            if outcome.reviewed:
                if not outcome.candidates and self.create == "create":
                    if not summary.dry_run:
                        source_record_id = self._store_detail(
                            external_id,
                            payload,
                            summary,
                        )
                        values = {
                            key: value
                            for key, value in derive_values(
                                SOURCE,
                                payload,
                            ).items()
                            if value not in (None, "")
                        }
                        if not self.trimp:
                            values.pop("training_load", None)
                        activity_id = create_activity(
                            self.writer,
                            source=SOURCE,
                            values=values,
                            source_record_id=source_record_id,
                        )
                        methods, targets = classification_for_payload(
                            payload
                        )
                        if self.workout_type and (methods or targets) and (
                            values.get("sport") in RUN_SPORTS
                        ):
                            self.writer.replace_activity_workout_methods(
                                activity_id,
                                sorted(methods),
                                source=SOURCE,
                            )
                            self.writer.replace_activity_workout_targets(
                                activity_id,
                                sorted(targets),
                                source=SOURCE,
                            )
                        apply_stored_enrichment(
                            self.connection,
                            source_record_id,
                        )
                    summary.created += 1
                    continue

                if not outcome.candidates and self.create == "ignore":
                    if not summary.dry_run:
                        self._store_detail(
                            external_id,
                            payload,
                            summary,
                        )
                    summary.ignored += 1
                    continue

                if outcome.reason == "several_exact":
                    summary.ambiguous += 1
                else:
                    summary.unmatched += 1
                summary.unmatched_rows.append(
                    _unmatched_row(activity, outcome)
                )
                reviews.append(_Review(external_id, outcome, payload))
                continue

            note = str(payload.get("note") or "").strip()
            tags = _tag_names(payload.get("tags"))

            summary.matched += 1
            entry = matched.get(outcome.activity_id)
            if entry is None:
                entry = _Matched(
                    activity_id=outcome.activity_id,
                    confidence=outcome.confidence,
                    external_id=external_id,
                )
                matched[outcome.activity_id] = entry
            if note and not entry.note:
                entry.note = note
            entry.tags |= tags

            if not summary.dry_run:
                self._record_source(
                    outcome.activity_id,
                    external_id,
                    payload,
                    summary,
                    match_method=outcome.match_method,
                )

        return matched, reviews

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

        decision = decide_match(
            self.connection,
            source=SOURCE,
            started_at_utc=started_at,
            elapsed_s=elapsed,
            duration_s=duration,
            distance_m=_distance_m(activity),
            local_date=_local_date(activity),
            policy=MatchPolicy(exact_twin=False),
        )
        if decision.activity_id is not None:
            return decision.activity_id, "", decision.confidence
        return None, decision.reason, None

    # -- the review path ----------------------------------------------------

    def _decide(self, activity: dict) -> _Outcome:
        """Resolve one row to an activity or to a review candidate set.

        The temporal matcher owns the normal case. When it rejects a row, a
        near-identical same-day twin is still the same session; a twin that is
        a sheet-only duplicate of a device row is not a target but the
        duplicate itself, so it becomes a review item that suggests the device
        row. Nothing is ever created from Runalyze.
        """
        activity_id, reason, confidence = self._match(activity)
        if activity_id is not None:
            return _Outcome(
                activity_id=activity_id,
                reason="matched",
                confidence=confidence,
            )

        local_date = _local_date(activity)
        duration = _number(activity.get("duration")) or 0.0
        distance_m = _distance_m(activity)

        candidates = self._day_activities(local_date)
        exact = [
            row
            for row in candidates
            if _is_exact_twin(row, duration, distance_m)
        ]
        duplicates = [
            row
            for row in exact
            if _is_sheet_duplicate(row, candidates, duration)
        ]
        viable = [row for row in exact if row not in duplicates]

        if len(viable) == 1 and not duplicates:
            return _Outcome(
                activity_id=viable[0]["id"],
                reason=EXACT_MATCH_METHOD,
                confidence=1.0,
                match_method=EXACT_MATCH_METHOD,
            )

        if len(viable) > 1:
            reason = "several_exact"
        elif duplicates:
            reason = "exact_sheet_duplicate"

        suggested = (
            _device_twin(duplicates[0], candidates)
            if duplicates
            else None
        )
        return _Outcome(
            reason=reason,
            candidates=[
                _candidate_row(row, suggested) for row in candidates
            ],
            suggested_activity_id=suggested["id"] if suggested else None,
        )

    def _day_activities(self, local_date: str | None) -> list[dict]:
        if not local_date:
            return []
        return [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT a.id, a.name, a.local_date, a.sport,
                       a.duration_s, a.distance_m,
                       (
                           SELECT group_concat(sr.source)
                           FROM activity_sources als
                           JOIN source_records sr
                               ON sr.id = als.source_record_id
                           WHERE als.activity_id = a.id
                       ) AS sources
                FROM activities a
                WHERE a.local_date = ? AND a.excluded_at IS NULL
                ORDER BY a.name = '', a.duration_s
                """,
                (local_date,),
            )
        ]


    def _stored_details(self) -> dict[str, _Stored]:
        rows = self.connection.execute(
            """
            SELECT sr.external_id, sr.payload_json, sr.fetched_at,
                   als.activity_id
            FROM source_records sr
            LEFT JOIN activity_sources als
                ON als.source_record_id = sr.id
            WHERE sr.source = ? AND sr.record_type = 'activity'
            """,
            (SOURCE,),
        ).fetchall()

        stored: dict[str, _Stored] = {}
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
            if entry is None or (
                entry.activity_id is None and linked is not None
            ):
                stored[external_id] = _Stored(
                    payload=payload,
                    activity_id=linked,
                    fetched_at=row["fetched_at"],
                )

        return stored

    # -- writing ------------------------------------------------------------

    def _record_source(
        self,
        activity_id: str,
        external_id: str,
        payload: dict,
        summary: RunalyzeEnrichSummary,
        *,
        match_method: str = "temporal_distance",
    ) -> int:
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
            match_method=match_method,
        )
        return source_record_id

    def _count_without_writing(
        self,
        matched: dict[str, _Matched],
        reviews: list[_Review],
        summary: RunalyzeEnrichSummary,
    ) -> None:
        for entry in matched.values():
            self._apply_one(entry, summary, dry_run=True)
        summary.reviews_recorded += len(reviews)

    def _write(
        self,
        matched: dict[str, _Matched],
        reviews: list[_Review],
        summary: RunalyzeEnrichSummary,
    ) -> None:
        for entry in matched.values():
            self._apply_one(entry, summary, dry_run=False)
        for review in reviews:
            self._record_review(review, summary)

    def _store_detail(
        self,
        external_id: str,
        payload: dict,
        summary: RunalyzeEnrichSummary,
    ) -> int:
        payload_json = _payload_json(payload)
        return self.writer.upsert_source_record(
            source=SOURCE,
            record_type="activity",
            external_id=external_id,
            checksum=_checksum(payload_json),
            payload_json=payload_json,
            import_run_id=summary.run_id,
        )

    def _record_review(
        self,
        review: _Review,
        summary: RunalyzeEnrichSummary,
    ) -> None:
        """Store the detail unlinked and open one review item for the row.

        The detail is kept so a resolution can apply its note and tags without
        another API call, and the record stays unlinked until a human picks an
        activity.
        """
        source_record_id = self._store_detail(
            review.external_id,
            review.payload,
            summary,
        )

        outcome = review.outcome
        fingerprint = review_fingerprint(
            [
                AMBIGUOUS_MATCH,
                review.external_id,
                sorted(
                    candidate["activity_id"]
                    for candidate in outcome.candidates
                ),
            ]
        )

        for item in self.writer.review_items(
            category=AMBIGUOUS_MATCH,
            status="open",
        ):
            context = _context(item)
            if context.get("external_id") != review.external_id:
                continue
            if item["fingerprint"] == fingerprint:
                continue
            self.writer.set_review_status(
                item["id"],
                "resolved",
                note="superseded: candidates changed",
            )

        _, created = self.writer.record_review_item(
            category=AMBIGUOUS_MATCH,
            detail=(
                f"runalyze {outcome.reason}: "
                f"{len(outcome.candidates)} same-day candidates"
            ),
            context={
                "external_id": review.external_id,
                "reason": outcome.reason,
                "suggested_activity_id": outcome.suggested_activity_id,
                "candidates": outcome.candidates,
            },
            severity="warn",
            fingerprint=fingerprint,
            source_record_id=source_record_id,
            import_run_id=summary.run_id,
        )
        summary.reviews_recorded += int(created)

    def _apply_one(
        self,
        entry: _Matched,
        summary: RunalyzeEnrichSummary,
        *,
        dry_run: bool,
    ) -> None:
        _apply_enrichment(
            self.connection,
            self.writer,
            entry,
            summary,
            dry_run=dry_run,
        )


def apply_stored_enrichment(
    connection: sqlite3.Connection,
    source_record_id: int,
) -> tuple[int, int, int]:
    """Apply a stored Runalyze detail to the activity it is linked to.

    Used when triage resolves a match: the detail is already stored, so its
    note and tags land without re-running the matcher, which would reject the
    row again for distance. Returns (comments filled, comments kept, tags).
    """
    row = connection.execute(
        """
        SELECT sr.external_id, sr.payload_json, als.activity_id
        FROM source_records sr
        LEFT JOIN activity_sources als ON als.source_record_id = sr.id
        WHERE sr.id = ? AND sr.source = ?
        """,
        (source_record_id, SOURCE),
    ).fetchone()
    if row is None or row["activity_id"] is None:
        return (0, 0, 0)

    payload = json.loads(row["payload_json"] or "{}")
    entry = _Matched(
        activity_id=row["activity_id"],
        confidence=None,
        external_id=str(row["external_id"]),
        note=str(payload.get("note") or "").strip(),
        tags=set(_tag_names(payload.get("tags"))),
    )
    summary = RunalyzeEnrichSummary()
    _apply_enrichment(
        connection,
        TrainingWriter(connection),
        entry,
        summary,
        dry_run=False,
    )
    return (
        summary.comments_filled,
        summary.comments_kept,
        summary.tags_written,
    )


def _apply_enrichment(
    connection: sqlite3.Connection,
    writer: TrainingWriter,
    entry: _Matched,
    summary: RunalyzeEnrichSummary,
    *,
    dry_run: bool,
) -> None:
    row = connection.execute(
        "SELECT description, sport FROM activities WHERE id = ?",
        (entry.activity_id,),
    ).fetchone()
    if row is None:
        return

    if not dry_run:
        _write_metrics(
            connection,
            writer,
            entry.activity_id,
            entry.external_id,
            str(row["sport"] or ""),
        )

    current = str(row["description"] or "")
    if entry.note:
        if current.strip():
            summary.comments_kept += 1
        else:
            summary.comments_filled += 1
            if not dry_run:
                writer.upsert_activity(
                    entry.activity_id,
                    {"description": entry.note},
                    source=SOURCE,
                    source_record_id=_source_id(
                        connection,
                        entry.external_id,
                    ),
                )

    existing = {
        tag["tag"]
        for tag in connection.execute(
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
        writer.replace_activity_tags(
            entry.activity_id,
            sorted(entry.tags),
            source=SOURCE,
            source_record_id=_source_id(connection, entry.external_id),
        )


def _write_metrics(
    connection: sqlite3.Connection,
    writer: TrainingWriter,
    activity_id: str,
    external_id: str,
    sport: str,
) -> None:
    """Apply a stored Runalyze detail's session metrics to its activity."""
    row = connection.execute(
        """
        SELECT id, payload_json FROM source_records
        WHERE source = ? AND record_type = 'activity' AND external_id = ?
        """,
        (SOURCE, external_id),
    ).fetchone()
    if row is None:
        return
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except ValueError:
        return
    if not isinstance(payload, dict):
        return
    writer.upsert_activity_metrics(
        activity_id,
        source=SOURCE,
        source_record_id=row["id"],
        **derive_metrics(SOURCE, payload, sport),
    )


def format_enrich_summary(summary: RunalyzeEnrichSummary) -> str:
    label = "Runalyze enrich dry run" if summary.dry_run else "Runalyze enrich"
    lines = [
        f"{label}: {summary.activities_seen} activities",
        f"  processed: {summary.processed}",
        f"  not processed: {summary.not_processed}",
        f"  matched: {summary.matched}",
        f"  created: {summary.created}",
        f"  ignored: {summary.ignored}",
        f"  refreshed: {summary.refreshed}",
        f"  already enriched: {summary.already_enriched}",
        f"  unmatched: {summary.unmatched}",
        f"  ambiguous: {summary.ambiguous}",
        f"  review items: {summary.reviews_recorded} "
        f"({summary.already_reviewed} already)",
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


def _unmatched_row(activity: dict, outcome: _Outcome) -> dict:
    return {
        "id": activity.get("id"),
        "date_time": activity.get("date_time"),
        "sport": activity.get("sport_id") or activity.get("sport"),
        "distance_km": activity.get("distance"),
        "duration_s": activity.get("duration"),
        "reason": outcome.reason,
        "suggested_activity_id": outcome.suggested_activity_id,
    }


def _already_processed(
    stored: dict[str, _Stored],
    external_id: str,
    activity_id: str | None,
) -> bool:
    """True when this row needs no API call on a re-run.

    A stored detail that is already linked is done — either the import wrote
    its note/tags or triage resolved the review and applied them. A stored
    detail with no link is the reviewed case: the open review item holds the
    decision, so re-reading it every window would starve the new rows.
    ``--refresh`` is the way to pick up edits made on the Runalyze side, and
    ``--refresh-before`` re-reads the payloads fetched before a moment.
    """
    entry = stored.get(external_id)
    if entry is None:
        return False

    if entry.activity_id is None:
        return True
    return activity_id is None or entry.activity_id == activity_id


def _is_stale(entry: _Stored | None, refresh_before: str) -> bool:
    """True when the stored payload predates the sweep cutoff.

    ``fetched_at`` is SQLite's UTC ``YYYY-MM-DD HH:MM:SS``; the cutoff is
    normalised to the same form so the comparison is a plain string one.
    """
    if entry is None or not entry.fetched_at:
        return False
    return str(entry.fetched_at) < refresh_before


def _refresh_cutoff(value: str) -> str:
    """Normalise a ``--refresh-before`` timestamp to SQLite UTC form."""
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"invalid refresh_before timestamp: {value}"
        ) from exc

    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _local_date(activity: dict) -> str | None:
    raw = str(activity.get("date_time") or "").strip()
    return raw[:10] if len(raw) >= 10 else None


def _is_exact_twin(
    row: dict,
    duration_s: float,
    distance_m: float | None,
) -> bool:
    """Same session by the strict rule: duration and distance within a hair."""
    stored_duration = row.get("duration_s")
    stored_distance = row.get("distance_m")
    if not duration_s or not stored_duration:
        return False
    if distance_m is None or stored_distance is None:
        return False
    return (
        abs(float(stored_duration) - duration_s) <= EXACT_DURATION_S
        and abs(float(stored_distance) - distance_m) <= EXACT_DISTANCE_M
    )


def _sources(row: dict) -> set[str]:
    raw = str(row.get("sources") or "")
    return {part for part in raw.split(",") if part}


def _is_sheet_duplicate(
    row: dict,
    candidates: list[dict],
    duration_s: float,
) -> bool:
    """True when a sheet-only row mirrors a device row of the same session."""
    if _sources(row) != {"sheet"}:
        return False
    for other in candidates:
        if other["id"] == row["id"]:
            continue
        if not _sources(other) & set(DEVICE_SOURCES):
            continue
        stored = other.get("duration_s")
        if not stored or not duration_s:
            continue
        if abs(float(stored) - duration_s) / duration_s <= (
            SAME_SESSION_DURATION_RATIO
        ):
            return True
    return False


def _device_twin(row: dict, candidates: list[dict]) -> dict | None:
    """The device row closest in duration to a sheet-only duplicate."""
    target = float(row.get("duration_s") or 0)
    best: dict | None = None
    best_gap = 0.0

    for other in candidates:
        if other["id"] == row["id"]:
            continue
        if not _sources(other) & set(DEVICE_SOURCES):
            continue
        gap = abs(float(other.get("duration_s") or 0) - target)
        if best is None or gap < best_gap:
            best, best_gap = other, gap

    return best


def _candidate_row(row: dict, suggested: dict | None) -> dict:
    return {
        "activity_id": row["id"],
        "name": row.get("name") or "",
        "date": row.get("local_date"),
        "sport": row.get("sport"),
        "duration_s": row.get("duration_s"),
        "distance_m": row.get("distance_m"),
        "sources": sorted(_sources(row)),
        "suggested": bool(suggested and row["id"] == suggested["id"]),
    }


def _context(item) -> dict:
    try:
        value = json.loads(item["context_json"] or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


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
