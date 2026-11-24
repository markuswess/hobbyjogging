"""Garmin daily wellness: resting HR, HRV, sleep, steps, SpO2, floors.

The Personal API exposes the daily user summary and an HRV summary; sleep
detail and weight are not on every account. The GDPR export is the fallback
for a missing feed, but this module only reads the API. Writes are fill-only:
an existing wellness day always wins (Intervals stays the owner where both
run), and a missing endpoint is a warning, not a failed sync.

The API addresses the user by ``ownerDisplayName`` or ``ownerId`` from an
activity summary; either works in the ``user`` query parameter.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core import TrainingWriter

from .garmin import GarminClient

SOURCE = "garmin"
RECORD_TYPE = "wellness"

_USER_SUMMARY = "/usersummary-service/usersummary/daily"
_HRV = "/hrv-service/hrv/{day}"
_WEIGHT_RANGE = "/weight-service/weight/range/{start}/{end}"


@dataclass
class GarminWellnessSummary:
    """What one wellness import saw and wrote."""

    run_id: int | None = None
    days: int = 0
    written: int = 0
    unchanged: int = 0
    no_user: bool = False
    hrv_days: int = 0
    resting_hr_days: int = 0
    sleep_days: int = 0
    steps_days: int = 0
    weight_days: int = 0
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class GarminWellnessImporter:
    """Read Garmin's daily wellness and fill empty fields."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        client: GarminClient | None = None,
    ):
        self.connection = connection
        self.client = client or GarminClient()
        self.writer = TrainingWriter(connection)

    def import_range(
        self,
        start: date,
        end: date,
    ) -> GarminWellnessSummary:
        if start > end:
            raise ValueError("start must not be after end")

        summary = GarminWellnessSummary()
        summary.run_id = self.writer.start_import_run(
            SOURCE,
            {
                "wellness": True,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )

        try:
            user = self._user(start, end)
            if user is None:
                summary.no_user = True
                self._finish(summary, "success")
                return summary

            weights = self._weights(user, start, end)

            day = start
            while day <= end:
                summary.days += 1
                payload = {}
                fields: dict[str, object] = {}

                try:
                    summary_json = self._summary(user, day)
                except RuntimeError as exc:
                    summary.errors.append(f"{day}: {exc}")
                    day += timedelta(days=1)
                    continue

                payload["summary"] = summary_json
                _fill_summary(fields, summary_json, summary)

                try:
                    hrv = self._hrv(user, day)
                except RuntimeError as exc:
                    # HRV is not exposed on every account; it must not block
                    # the resting HR and steps of the same day.
                    summary.errors.append(f"{day} hrv: {exc}")
                    hrv = None
                if hrv is not None:
                    payload["hrv"] = hrv
                    value = _hrv_value(hrv)
                    if value is not None:
                        fields["hrv"] = value
                        summary.hrv_days += 1

                weight = weights.get(day)
                if weight is not None:
                    fields["weight_kg"] = weight
                    payload["weight"] = weight
                    summary.weight_days += 1

                if not fields:
                    summary.unchanged += 1
                    day += timedelta(days=1)
                    continue

                missing = self._missing_fields(day, fields)
                if not missing:
                    summary.unchanged += 1
                else:
                    self._write(day, payload, missing, summary)
                    summary.written += 1

                day += timedelta(days=1)

            self._finish(summary, "success")
            return summary
        except Exception as exc:
            self.connection.rollback()
            self._finish(summary, "failed", error=str(exc))
            raise

    # -- reads -------------------------------------------------------------

    def _user(self, start: date, end: date) -> str | None:
        activities = self.client.list_activities(start, end)
        if not activities:
            activities = self.client.list_activities(
                end - timedelta(days=365),
                end,
            )
        for item in activities:
            value = item.get("ownerDisplayName") or item.get("ownerId")
            if value:
                return str(value)
        return None

    def _summary(self, user: str, day: date) -> dict:
        payload = self.client.get_json(
            _USER_SUMMARY,
            {"user": user, "calendarDate": day.isoformat()},
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Garmin daily summary was not a JSON object")
        return payload

    def _hrv(self, user: str, day: date) -> dict | None:
        payload = self.client.get_json(
            _HRV.format(day=day.isoformat()),
            {"user": user},
        )
        return payload if isinstance(payload, dict) else None

    def _weights(
        self,
        user: str,
        start: date,
        end: date,
    ) -> dict[date, float]:
        try:
            payload = self.client.get_json(
                _WEIGHT_RANGE.format(
                    start=start.isoformat(),
                    end=end.isoformat(),
                ),
                {"user": user},
            )
        except RuntimeError:
            return {}

        if not isinstance(payload, dict):
            return {}

        weights: dict[date, float] = {}
        for item in payload.get("dailyWeightSummaries") or []:
            if not isinstance(item, dict):
                continue
            latest = item.get("latestWeight")
            if not isinstance(latest, dict):
                continue
            grams = latest.get("weight")
            day = latest.get("calendarDate") or item.get("summaryDate")
            if isinstance(grams, (int, float)) and grams > 0 and day:
                try:
                    weights[date.fromisoformat(str(day)[:10])] = (
                        float(grams) / 1000.0
                    )
                except ValueError:
                    continue
        return weights

    # -- writes ------------------------------------------------------------

    def _missing_fields(
        self,
        day: date,
        fields: dict[str, object],
    ) -> dict[str, object]:
        """Only the fields the stored day leaves empty (fill-only)."""
        row = self.connection.execute(
            "SELECT * FROM wellness_days WHERE local_date = ?",
            (day.isoformat(),),
        ).fetchone()
        if row is None:
            return dict(fields)
        return {
            key: value
            for key, value in fields.items()
            if row[key] is None
        }

    def _write(
        self,
        day: date,
        payload: dict,
        fields: dict[str, object],
        summary: GarminWellnessSummary,
    ) -> None:
        raw = json.dumps(payload, sort_keys=True, default=str)
        record_id = self.writer.upsert_source_record(
            source=SOURCE,
            record_type=RECORD_TYPE,
            external_id=day.isoformat(),
            checksum=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            payload_json=raw,
            import_run_id=summary.run_id,
        )
        self.writer.upsert_wellness(
            local_date=day.isoformat(),
            source_record_id=record_id,
            **fields,
        )

    def _finish(
        self,
        summary: GarminWellnessSummary,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        if summary.run_id is None:
            return
        self.writer.finish_import_run(
            summary.run_id,
            status,
            records_seen=summary.days,
            records_imported=summary.written,
            records_skipped=summary.unchanged,
            error=error,
        )


def _fill_summary(
    fields: dict[str, object],
    payload: dict,
    summary: GarminWellnessSummary,
) -> None:
    resting = _number(payload.get("restingHeartRate"))
    if resting is not None:
        fields["resting_hr"] = resting
        summary.resting_hr_days += 1

    sleep = _number(payload.get("sleepingSeconds"))
    if sleep is not None and sleep > 0:
        fields["sleep_s"] = sleep
        summary.sleep_days += 1

    steps = _number(payload.get("totalSteps"))
    if steps is not None and steps >= 0:
        fields["steps"] = int(steps)
        summary.steps_days += 1

    spo2 = _number(payload.get("averageSpo2"))
    if spo2 is None:
        spo2 = _number(payload.get("latestSpo2"))
    if spo2 is not None and spo2 > 0:
        fields["spo2"] = spo2

    floors = _number(payload.get("floorsAscended"))
    if floors is not None and floors >= 0:
        fields["floors_climbed"] = int(round(floors))


def _hrv_value(payload: dict) -> float | None:
    summary = payload.get("hrvSummary")
    if not isinstance(summary, dict):
        return None
    for key in ("lastNightAvg", "weeklyAvg"):
        value = _number(summary.get(key))
        if value is not None and value > 0:
            return value
    return None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_wellness_summary(summary: GarminWellnessSummary) -> str:
    label = "Garmin wellness"
    if summary.no_user:
        return f"{label}: no activity found, so no user id to read wellness for"
    lines = [
        f"{label}: {summary.days} days, {summary.written} written, "
        f"{summary.unchanged} unchanged",
        f"  hrv: {summary.hrv_days}, resting HR: {summary.resting_hr_days}, "
        f"sleep: {summary.sleep_days}, steps: {summary.steps_days}, "
        f"weight: {summary.weight_days}",
    ]
    for error in summary.errors or []:
        lines.append(f"  warning: {error}")
    return "\n".join(lines)
