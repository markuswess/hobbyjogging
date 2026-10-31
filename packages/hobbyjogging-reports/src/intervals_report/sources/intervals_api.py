"""Intervals.icu adapter.

This module is the *only* place that knows the raw Intervals.icu field
names. Everything downstream sees the canonical model.
"""

from datetime import date

from ..api import Intervals
from ..model import Activity, Event, Interval, WellnessDay

_TYPE_ALIASES = {
    "run": "run",
    "trailrun": "trail_run",
}


def _norm_type(value: str | None) -> str:
    value = (value or "").lower()
    return _TYPE_ALIASES.get(value, value)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _fraction(value: float | None) -> float | None:
    """Normalize ICU percentages (e.g. 85) to fractions (0.85)."""
    if value is None:
        return None
    return value / 100 if value > 1 else value


def to_activity(raw: dict) -> Activity:
    return Activity(
        id=raw["id"],
        date=_parse_date(raw["start_date_local"]),
        type=_norm_type(raw.get("type")),
        name=raw.get("name") or "",
        description=raw.get("description") or "",
        duration_s=raw.get("moving_time") or 0,
        distance_m=raw.get("distance") or 0,
        avg_hr=raw.get("average_heartrate"),
        training_load=raw.get("icu_training_load"),
        rpe=raw.get("icu_rpe"),
        feel=raw.get("feel"),
        intensity=_fraction(raw.get("icu_intensity")),
        pace_zone_times=list(raw.get("pace_zone_times") or []),
        hr_zone_times=list(raw.get("icu_hr_zone_times") or []),
    )


def to_wellness(raw: dict) -> WellnessDay:
    return WellnessDay(
        date=_parse_date(raw["id"]),
        hrv=raw.get("hrv"),
        resting_hr=raw.get("restingHR"),
        sleep_s=raw.get("sleepSecs"),
    )


def to_event(raw: dict) -> Event:
    return Event(
        date=_parse_date(raw.get("start_date_local") or raw.get("date") or ""),
        name=raw.get("name") or "",
        type=_norm_type(raw.get("type")),
        description=raw.get("description") or "",
        duration_s=raw.get("duration"),
        distance_m=raw.get("distance"),
    )


def to_interval(raw: dict) -> Interval:
    return Interval(
        group_id=raw.get("group_id"),
        type=raw.get("type") or "",
        start_time=raw.get("start_time") or "",
        duration_s=raw.get("moving_time") or 0,
        distance_m=raw.get("distance") or 0,
        avg_hr=raw.get("average_heartrate"),
        max_hr=raw.get("max_heartrate"),
    )


class IntervalsSource:
    """DataSource backed by the Intervals.icu API."""

    def __init__(self, client: Intervals | None = None):
        self.client = client or Intervals()

    def activities(self, start: date, end: date) -> list[Activity]:
        return [to_activity(a) for a in self.client.activities(start, end) or []]

    def wellness(self, start: date, end: date) -> list[WellnessDay]:
        return [to_wellness(w) for w in self.client.wellness(start, end) or []]

    def events(self, start: date, end: date) -> list[Event]:
        return [to_event(e) for e in self.client.events(start, end) or []]

    def activity_intervals(self, activity_id: str) -> list[Interval]:
        return [
            to_interval(i)
            for i in self.client.get_activity_intervals(activity_id)
        ]
