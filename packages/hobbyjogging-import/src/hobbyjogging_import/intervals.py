"""Intervals.icu importer."""

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from hobbyjogging_core import EventZoneTime, TrainingWriter
from hobbyjogging_core.db.writer import CONFLICT_FIELDS
from hobbyjogging_core.model import Interval
from hobbyjogging_core.sports import canonical_sport

from .client import IntervalsApi, IntervalsClient
from .event_zones import current_zone_times, event_zone_data
from .matching import ActivityMatcher, MatchCandidate, linked_activity
from .quality import (
    record_ambiguous_match,
    record_field_conflicts,
    record_quality_findings,
    resolve_agreed_field_conflicts,
)

SOURCE = "intervals"


@dataclass
class ImportSummary:
    run_id: int
    plan_end: date | None = None
    activities_seen: int = 0
    activities_imported: int = 0
    activities_skipped: int = 0
    wellness_seen: int = 0
    wellness_imported: int = 0
    events_seen: int = 0
    events_imported: int = 0
    events_removed: int = 0
    events_revived: int = 0
    intervals_imported: int = 0
    ambiguous_matches: list[tuple[str, list[MatchCandidate]]] = field(
        default_factory=list
    )
    review_recorded: int = 0

    @property
    def records_seen(self) -> int:
        return self.activities_seen + self.wellness_seen + self.events_seen

    @property
    def records_imported(self) -> int:
        return self.activities_imported + self.wellness_imported + self.events_imported


@dataclass
class EventSyncSummary:
    """Results of reconciling planned events with the Intervals calendar."""

    run_id: int | None = None
    dry_run: bool = False
    start: date | None = None
    end: date | None = None
    fetched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    revived: int = 0
    skipped: int = 0


class IntervalsImporter:
    """Import activities, wellness, events, and intervals from Intervals.icu."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        client: IntervalsApi | None = None,
    ):
        self.connection = connection
        self.client = client or IntervalsClient()
        self.writer = TrainingWriter(connection)
        self.matcher = ActivityMatcher(connection)

    def sync_events(
        self,
        start: date,
        end: date,
        *,
        dry_run: bool = False,
        plan_days: int | None = None,
    ) -> EventSyncSummary:
        """Reconcile planned events with the current Intervals calendar.

        Intervals is authoritative for events. Existing fields are replaced
        (including NULLs), events that disappeared in the window are
        soft-excluded, and reappearing events are revived. Events from other
        sources are never touched.
        """
        if start > end:
            raise ValueError("start must not be after end")

        summary = EventSyncSummary(
            dry_run=dry_run,
            start=start,
            end=end,
        )

        if not dry_run:
            summary.run_id = self.writer.start_import_run(
                SOURCE,
                {
                    "events_sync": True,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "plan_days": plan_days,
                },
            )

        try:
            events = list(self.client.events(start, end) or [])
            summary.fetched = len(events)

            if dry_run:
                counts = self._sync_event_payloads(
                    events,
                    start,
                    end,
                    None,
                    dry_run=True,
                )
            else:
                with self.connection:
                    counts = self._sync_event_payloads(
                        events,
                        start,
                        end,
                        summary.run_id,
                    )

            summary.new = counts.new
            summary.updated = counts.updated
            summary.unchanged = counts.unchanged
            summary.removed = counts.removed
            summary.revived = counts.revived
            summary.skipped = counts.skipped

            if summary.run_id is not None:
                self.writer.finish_import_run(
                    summary.run_id,
                    "success",
                    records_seen=summary.fetched,
                    records_imported=(
                        summary.new + summary.updated + summary.revived
                    ),
                    records_skipped=(
                        summary.unchanged + summary.skipped
                    ),
                )
            return summary

        except Exception as exc:
            if summary.run_id is not None:
                self.connection.rollback()
                self.writer.finish_import_run(
                    summary.run_id,
                    "failed",
                    records_seen=summary.fetched,
                    records_imported=(
                        summary.new + summary.updated + summary.revived
                    ),
                    records_skipped=(
                        summary.unchanged + summary.skipped
                    ),
                    error=str(exc),
                )
            raise

    def import_range(
        self,
        start: date,
        end: date,
        *,
        include_intervals: bool = True,
        plan_end: date | None = None,
    ) -> ImportSummary:
        """Import activities/wellness through ``end`` and events through
        ``plan_end``.

        Planned workouts live in the calendar ahead of today, so they use a
        separate horizon. ``plan_end`` defaults to ``end`` and is clamped to
        at least ``end`` so the event range always contains the activity
        range.
        """
        if plan_end is None or plan_end < end:
            plan_end = end

        summary = ImportSummary(
            plan_end=plan_end,
            run_id=self.writer.start_import_run(
                SOURCE,
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "plan_end": plan_end.isoformat(),
                    "include_intervals": include_intervals,
                },
            ),
        )

        try:
            activities = list(self.client.activities(start, end) or [])
            wellness = list(self.client.wellness(start, end) or [])
            events = list(self.client.events(start, plan_end) or [])
            interval_payloads = self._fetch_intervals(activities, include_intervals)

            summary.activities_seen = len(activities)
            summary.wellness_seen = len(wellness)
            summary.events_seen = len(events)

            with self.connection:
                for raw in activities:
                    interval_count = self._import_activity(
                        raw,
                        summary,
                        interval_payloads.get(_activity_external_id(raw)),
                    )
                    if interval_count is None:
                        summary.activities_skipped += 1
                    else:
                        summary.activities_imported += 1
                        summary.intervals_imported += interval_count

                for raw in wellness:
                    if self._import_wellness(raw, summary.run_id):
                        summary.wellness_imported += 1

                event_summary = self._sync_event_payloads(
                    events,
                    start,
                    plan_end,
                    summary.run_id,
                )
                summary.events_imported = (
                    event_summary.new
                    + event_summary.updated
                    + event_summary.unchanged
                    + event_summary.revived
                )
                summary.events_removed = event_summary.removed
                summary.events_revived = event_summary.revived

            self.writer.finish_import_run(
                summary.run_id,
                "success",
                records_seen=summary.records_seen,
                records_imported=summary.records_imported,
                records_skipped=summary.activities_skipped,
            )
            return summary

        except Exception as exc:
            self.connection.rollback()
            self.writer.finish_import_run(
                summary.run_id,
                "failed",
                records_seen=summary.records_seen,
                records_imported=summary.records_imported,
                records_skipped=summary.activities_skipped,
                error=str(exc),
            )
            raise

    def import_activity(
        self,
        external_id: str,
        *,
        force: bool = False,
        include_intervals: bool = False,
    ) -> ImportSummary:
        """Re-import one Intervals activity by its external id.

        ``force=True`` lets Intervals take ownership of non-manual fields
        even when another source currently owns them. This is the human
        trust decision used by triage; a normal range import never sets it.
        """
        summary = ImportSummary(
            run_id=self.writer.start_import_run(
                SOURCE,
                {
                    "activity": external_id,
                    "force": force,
                    "include_intervals": include_intervals,
                },
            )
        )

        try:
            raw = self.client.activity(external_id)
            interval_payload = (
                list(raw.get("icu_intervals") or [])
                if include_intervals
                else None
            )
            summary.activities_seen = 1

            with self.connection:
                interval_count = self._import_activity(
                    raw,
                    summary,
                    interval_payload,
                    force=force,
                )

            if interval_count is None:
                summary.activities_skipped += 1
            else:
                summary.activities_imported += 1
                summary.intervals_imported += interval_count

            self.writer.finish_import_run(
                summary.run_id,
                "success",
                records_seen=summary.records_seen,
                records_imported=summary.records_imported,
                records_skipped=summary.activities_skipped,
            )
            return summary

        except Exception as exc:
            self.connection.rollback()
            self.writer.finish_import_run(
                summary.run_id,
                "failed",
                records_seen=summary.records_seen,
                records_imported=summary.records_imported,
                records_skipped=summary.activities_skipped,
                error=str(exc),
            )
            raise

    def _fetch_intervals(
        self,
        activities: list[dict],
        include_intervals: bool,
    ) -> dict[str, list[dict] | None]:
        if not include_intervals:
            return {}

        result: dict[str, list[dict] | None] = {}
        for raw in activities:
            external_id = _activity_external_id(raw)
            if external_id is None:
                continue
            if self.writer.is_source_record_excluded(
                source=SOURCE,
                record_type="activity",
                external_id=external_id,
            ):
                continue
            result[external_id] = list(
                self.client.activity_intervals(external_id) or []
            )
        return result

    def _import_activity(
        self,
        raw: dict,
        summary: ImportSummary,
        interval_payload: list[dict] | None,
        *,
        force: bool = False,
    ) -> int | None:
        external_id = _activity_external_id(raw)
        if external_id is None:
            return None
        if external_id in {id for id, _ in summary.ambiguous_matches}:
            return None
        if self.writer.is_source_record_excluded(
            source=SOURCE,
            record_type="activity",
            external_id=external_id,
        ):
            return None

        payload = _payload_json(raw)
        source_record_id = self.writer.upsert_source_record(
            source=SOURCE,
            record_type="activity",
            external_id=external_id,
            checksum=_checksum(payload),
            payload_json=payload,
            import_run_id=summary.run_id,
        )
        activity_id, match_method, confidence = self._resolve_activity(
            raw,
            summary,
            external_id,
            source_record_id,
        )
        if activity_id is None:
            return None

        values = _activity_values(raw)
        conflicts = self.writer.upsert_activity(
            activity_id,
            values,
            source=SOURCE,
            source_record_id=source_record_id,
            force=force,
        )
        summary.review_recorded += record_field_conflicts(
            self.writer,
            activity_id=activity_id,
            source_record_id=source_record_id,
            import_run_id=summary.run_id,
            conflicts=conflicts,
        )
        resolve_agreed_field_conflicts(
            self.writer,
            activity_id=activity_id,
            fields=(
                (set(values) & CONFLICT_FIELDS)
                - {conflict.field_name for conflict in conflicts}
            ),
        )
        self.writer.link_activity_source(
            activity_id,
            source_record_id,
            match_method=match_method,
            confidence=confidence,
        )
        self.writer.set_activity_zone_times(
            activity_id,
            "pace",
            _number_list(raw.get("pace_zone_times")),
        )
        self.writer.set_activity_zone_times(
            activity_id,
            "hr",
            _number_list(raw.get("icu_hr_zone_times")),
        )

        summary.review_recorded += record_quality_findings(
            self.writer,
            activity_id=activity_id,
            source_record_id=source_record_id,
            import_run_id=summary.run_id,
            sport=str(values.get("sport") or ""),
            duration_s=float(values.get("duration_s") or 0),
            elapsed_s=float(values.get("elapsed_s") or 0),
            distance_m=float(values.get("distance_m") or 0),
            moving_s=(
                float(values["moving_s"])
                if values.get("moving_s") is not None
                else None
            ),
        )

        if interval_payload is None:
            return 0

        interval_payload_json = _payload_json(interval_payload)
        interval_source_id = self.writer.upsert_source_record(
            source=SOURCE,
            record_type="intervals",
            external_id=external_id,
            checksum=_checksum(interval_payload_json),
            payload_json=interval_payload_json,
            import_run_id=summary.run_id,
        )
        intervals = [_to_interval(item) for item in interval_payload]
        self.writer.replace_activity_intervals(
            activity_id,
            intervals,
            source_record_id=interval_source_id,
        )
        return len(intervals)

    def _resolve_activity(
        self,
        raw: dict,
        summary: ImportSummary,
        external_id: str,
        source_record_id: int,
    ) -> tuple[str | None, str, float | None]:
        existing_link = linked_activity(self.connection, source_record_id)

        if existing_link is not None:
            activity_id = existing_link["activity_id"]
            if self.writer.is_activity_excluded(activity_id):
                return None
            return (
                activity_id,
                existing_link["match_method"] or "external_id",
                existing_link["confidence"],
            )

        matches = self.matcher.find(
            started_at_utc=str(raw.get("start_date") or ""),
            source=SOURCE,
            elapsed_s=_float(raw.get("elapsed_time")) or 0.0,
            duration_s=_float(raw.get("moving_time")) or 0.0,
        )

        if len(matches) > 1:
            summary.ambiguous_matches.append((external_id, matches))
            summary.review_recorded += record_ambiguous_match(
                self.writer,
                source_record_id=source_record_id,
                external_id=external_id,
                candidates=matches,
                import_run_id=summary.run_id,
            )
            return None, "", None

        if matches:
            match = matches[0]
            return match.activity_id, match.match_method, match.confidence

        return _stable_id("activity", external_id), "created", None

    def _import_wellness(self, raw: dict, run_id: int) -> bool:
        value = raw.get("id") or raw.get("date")
        local_date = _date_prefix(value)
        if local_date is None:
            return False

        payload = _payload_json(raw)
        source_record_id = self.writer.upsert_source_record(
            source=SOURCE,
            record_type="wellness",
            external_id=local_date,
            checksum=_checksum(payload),
            payload_json=payload,
            import_run_id=run_id,
        )
        self.writer.upsert_wellness(
            local_date=local_date,
            source_record_id=source_record_id,
            hrv=_float(raw.get("hrv")),
            resting_hr=_float(raw.get("restingHR")),
            sleep_s=_float(raw.get("sleepSecs")),
        )
        return True

    def _sync_event_payloads(
        self,
        events: list[dict],
        start: date,
        end: date,
        run_id: int | None,
        *,
        dry_run: bool = False,
    ) -> EventSyncSummary:
        summary = EventSyncSummary(
            dry_run=dry_run,
            start=start,
            end=end,
            fetched=len(events),
        )

        rows = self.connection.execute(
            """
            SELECT e.id, e.local_date, e.name, e.type, e.description,
                   e.duration_s, e.distance_m, e.training_load,
                   e.zone_kind, e.excluded_at, sr.external_id
            FROM events e
            JOIN source_records sr ON sr.id = e.source_record_id
            WHERE sr.source = ? AND sr.record_type = 'event'
              AND e.local_date BETWEEN ? AND ?
            """,
            (SOURCE, start.isoformat(), end.isoformat()),
        ).fetchall()
        existing = {
            str(row["external_id"]): row
            for row in rows
        }
        existing_zones = current_zone_times(
            self.connection,
            [row["id"] for row in rows],
        )

        fetched_ids: set[str] = set()

        for raw in events:
            external_id = _event_external_id(raw)
            fetched_ids.add(external_id)
            values = _event_values(raw)
            if values is None:
                summary.skipped += 1
                continue

            kind, zones = event_zone_data(raw, str(values["type"]))
            row = existing.get(external_id)
            if row is None:
                summary.new += 1
            elif row["excluded_at"]:
                summary.revived += 1
            elif _event_changed(
                row,
                values,
                kind=kind,
                zones=zones,
                existing_zones=existing_zones.get(row["id"], {}),
            ):
                summary.updated += 1
            else:
                summary.unchanged += 1

            if dry_run:
                continue

            payload = _payload_json(raw)
            source_record_id = self.writer.upsert_source_record(
                source=SOURCE,
                record_type="event",
                external_id=external_id,
                checksum=_checksum(payload),
                payload_json=payload,
                import_run_id=run_id,
            )
            self.writer.upsert_event(
                event_id=values["event_id"],
                local_date=values["local_date"],
                name=values["name"],
                type=values["type"],
                description=values["description"],
                duration_s=values["duration_s"],
                distance_m=values["distance_m"],
                training_load=values["training_load"],
                source_record_id=source_record_id,
            )
            self.writer.set_event_zone_times(
                values["event_id"],
                kind,
                zones,
            )

        for external_id, row in existing.items():
            if external_id in fetched_ids or row["excluded_at"]:
                continue
            if dry_run:
                summary.removed += 1
            elif self.writer.exclude_event(row["id"]):
                summary.removed += 1

        return summary


def _activity_external_id(raw: dict) -> str | None:
    value = raw.get("id")
    return str(value) if value is not None else None


def _event_external_id(raw: dict) -> str:
    value = raw.get("id")
    if value is not None:
        return str(value)
    return _checksum(_payload_json(raw))


def _event_values(raw: dict) -> dict[str, object] | None:
    local_date = _date_prefix(
        raw.get("start_date_local") or raw.get("date")
    )
    if local_date is None:
        return None

    external_id = _event_external_id(raw)
    duration = _float(raw.get("moving_time"))
    if duration is None:
        duration = _float(raw.get("duration"))

    return {
        "event_id": _stable_id("event", external_id),
        "local_date": local_date,
        "name": str(raw.get("name") or ""),
        "type": canonical_sport(raw.get("type")),
        "description": str(raw.get("description") or ""),
        "duration_s": duration,
        "distance_m": _float(raw.get("distance")),
        "training_load": _float(raw.get("icu_training_load")),
    }


def _event_changed(
    row,
    values: dict[str, object],
    *,
    kind: str,
    zones: list[EventZoneTime],
    existing_zones: dict[str, float],
) -> bool:
    return (
        row["local_date"] != values["local_date"]
        or row["name"] != values["name"]
        or row["type"] != values["type"]
        or row["description"] != values["description"]
        or row["duration_s"] != values["duration_s"]
        or row["distance_m"] != values["distance_m"]
        or row["training_load"] != values["training_load"]
        or row["zone_kind"] != kind
        or existing_zones
        != {zone.zone_label: float(zone.seconds) for zone in zones}
    )


def _activity_values(raw: dict) -> dict[str, object]:
    local_date = _date_prefix(
        raw.get("start_date_local") or raw.get("start_date")
    )
    if local_date is None:
        raise ValueError(f"Activity has no usable date: {raw.get('id')}")

    values: dict[str, object] = {
        "local_date": local_date,
        "sport": canonical_sport(raw.get("type")),
        "name": str(raw.get("name") or ""),
        "description": str(raw.get("description") or ""),
        # Garmin records timer/recording time. Intervals' recording time is
        # the equivalent; moving_time is only a fallback for old payloads.
        "duration_s": (
            _float(raw.get("icu_recording_time"))
            or _float(raw.get("moving_time"))
            or 0.0
        ),
        "elapsed_s": _float(raw.get("elapsed_time")) or 0.0,
        "distance_m": _float(raw.get("distance")) or 0.0,
    }

    optional = {
        "started_at_utc": raw.get("start_date"),
        "tz_offset_min": _tz_offset_min(raw),
        "sub_sport": raw.get("sub_type"),
        "moving_s": _float(raw.get("moving_time")),
        "avg_hr": _float(raw.get("average_heartrate")),
        "training_load": _float(raw.get("icu_training_load")),
        "rpe": _float(raw.get("icu_rpe")),
        "feel": _int(raw.get("feel")),
        "intensity": _fraction(raw.get("icu_intensity")),
    }
    values.update(
        {
            key: value
            for key, value in optional.items()
            if value is not None
        }
    )
    return values


def _to_interval(raw: dict) -> Interval:
    return Interval(
        group_id=raw.get("group_id"),
        type=str(raw.get("type") or ""),
        start_time=str(raw.get("start_time") or ""),
        duration_s=_float(raw.get("moving_time")) or 0.0,
        distance_m=_float(raw.get("distance")) or 0.0,
        avg_hr=_float(raw.get("average_heartrate")),
        max_hr=_float(raw.get("max_heartrate")),
    )


def _stable_id(kind: str, external_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"hobbyjogging:intervals:{kind}:{external_id}",
        )
    )


def _payload_json(raw: object) -> str:
    return json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _date_prefix(value: object) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    text = value[:10]
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _fraction(value: object) -> float | None:
    number = _float(value)
    if number is None:
        return None
    return number / 100 if number > 1 else number


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _int(value: object) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def _number_list(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    return [float(item) for item in value if item is not None]


def _tz_offset_min(raw: dict) -> int | None:
    start = raw.get("start_date")
    local = raw.get("start_date_local")
    if not isinstance(start, str) or not isinstance(local, str):
        return None

    try:
        utc = datetime.fromisoformat(start.replace("Z", "+00:00"))
        local_time = datetime.fromisoformat(local)
    except ValueError:
        return None

    if utc.tzinfo is not None:
        utc = utc.astimezone(timezone.utc).replace(tzinfo=None)
    if local_time.tzinfo is not None:
        local_time = local_time.replace(tzinfo=None)

    return int((local_time - utc).total_seconds() / 60)
