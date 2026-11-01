"""Intervals.icu importer."""

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from hobbyjogging_core import TrainingWriter
from hobbyjogging_core.model import Interval

from .client import IntervalsApi, IntervalsClient

SOURCE = "intervals"

_TYPE_ALIASES = {
    "run": "run",
    "trailrun": "trail_run",
}


@dataclass
class ImportSummary:
    run_id: int
    activities_seen: int = 0
    activities_imported: int = 0
    activities_skipped: int = 0
    wellness_seen: int = 0
    wellness_imported: int = 0
    events_seen: int = 0
    events_imported: int = 0
    intervals_imported: int = 0

    @property
    def records_seen(self) -> int:
        return self.activities_seen + self.wellness_seen + self.events_seen

    @property
    def records_imported(self) -> int:
        return self.activities_imported + self.wellness_imported + self.events_imported


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

    def import_range(
        self,
        start: date,
        end: date,
        *,
        include_intervals: bool = True,
    ) -> ImportSummary:
        summary = ImportSummary(
            run_id=self.writer.start_import_run(
                SOURCE,
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "include_intervals": include_intervals,
                },
            )
        )

        try:
            activities = list(self.client.activities(start, end) or [])
            wellness = list(self.client.wellness(start, end) or [])
            events = list(self.client.events(start, end) or [])
            interval_payloads = self._fetch_intervals(activities, include_intervals)

            summary.activities_seen = len(activities)
            summary.wellness_seen = len(wellness)
            summary.events_seen = len(events)

            with self.connection:
                for raw in activities:
                    interval_count = self._import_activity(
                        raw,
                        summary.run_id,
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

                for raw in events:
                    if self._import_event(raw, summary.run_id):
                        summary.events_imported += 1

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
            result[external_id] = list(
                self.client.activity_intervals(external_id) or []
            )
        return result

    def _import_activity(
        self,
        raw: dict,
        run_id: int,
        interval_payload: list[dict] | None,
    ) -> int | None:
        external_id = _activity_external_id(raw)
        if external_id is None:
            return None

        payload = _payload_json(raw)
        source_record_id = self.writer.upsert_source_record(
            source=SOURCE,
            record_type="activity",
            external_id=external_id,
            checksum=_checksum(payload),
            payload_json=payload,
            import_run_id=run_id,
        )
        activity_id = _stable_id("activity", external_id)
        self.writer.upsert_activity(
            activity_id,
            _activity_values(raw),
            source=SOURCE,
            source_record_id=source_record_id,
        )
        self.writer.link_activity_source(
            activity_id,
            source_record_id,
            match_method="external_id",
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

        if interval_payload is None:
            return 0

        interval_payload_json = _payload_json(interval_payload)
        interval_source_id = self.writer.upsert_source_record(
            source=SOURCE,
            record_type="intervals",
            external_id=external_id,
            checksum=_checksum(interval_payload_json),
            payload_json=interval_payload_json,
            import_run_id=run_id,
        )
        intervals = [_to_interval(item) for item in interval_payload]
        self.writer.replace_activity_intervals(
            activity_id,
            intervals,
            source_record_id=interval_source_id,
        )
        return len(intervals)

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

    def _import_event(self, raw: dict, run_id: int) -> bool:
        value = raw.get("start_date_local") or raw.get("date")
        local_date = _date_prefix(value)
        if local_date is None:
            return False

        payload = _payload_json(raw)
        external_id = str(raw.get("id") or _checksum(payload))
        source_record_id = self.writer.upsert_source_record(
            source=SOURCE,
            record_type="event",
            external_id=external_id,
            checksum=_checksum(payload),
            payload_json=payload,
            import_run_id=run_id,
        )
        self.writer.upsert_event(
            event_id=_stable_id("event", external_id),
            local_date=local_date,
            name=str(raw.get("name") or ""),
            type=_norm_type(raw.get("type")),
            description=str(raw.get("description") or ""),
            duration_s=_float(raw.get("duration")),
            distance_m=_float(raw.get("distance")),
            source_record_id=source_record_id,
        )
        return True


def _activity_external_id(raw: dict) -> str | None:
    value = raw.get("id")
    return str(value) if value is not None else None


def _activity_values(raw: dict) -> dict[str, object]:
    local_date = _date_prefix(
        raw.get("start_date_local") or raw.get("start_date")
    )
    if local_date is None:
        raise ValueError(f"Activity has no usable date: {raw.get('id')}")

    values: dict[str, object] = {
        "local_date": local_date,
        "sport": _norm_type(raw.get("type")),
        "name": str(raw.get("name") or ""),
        "description": str(raw.get("description") or ""),
        "duration_s": _float(raw.get("moving_time")) or 0.0,
        "distance_m": _float(raw.get("distance")) or 0.0,
    }

    optional = {
        "started_at_utc": raw.get("start_date"),
        "tz_offset_min": _tz_offset_min(raw),
        "sub_sport": raw.get("sub_type"),
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


def _norm_type(value: object) -> str:
    text = str(value or "").lower()
    return _TYPE_ALIASES.get(text, text)


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
