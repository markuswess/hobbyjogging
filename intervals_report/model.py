"""Source-agnostic data model.

Adapters (e.g. ``sources/intervals_api.py``) translate raw payloads into
these types. Analysis, charts and reports should depend only on this model,
so the underlying data source can be swapped later (API -> local database)
without touching downstream code.
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Activity:
    id: str
    date: date
    type: str = ""  # canonical: "run", "trail_run", "ride", ...
    name: str = ""
    description: str = ""
    duration_s: float = 0
    distance_m: float = 0
    avg_hr: float | None = None
    training_load: float | None = None
    rpe: float | None = None
    intensity: float | None = None  # fraction of threshold (ICU intensity)
    pace_zone_times: list[float] = field(default_factory=list)
    hr_zone_times: list[float] = field(default_factory=list)


@dataclass
class WellnessDay:
    date: date
    hrv: float | None = None
    resting_hr: float | None = None
    sleep_s: float | None = None


@dataclass
class Event:
    date: date
    name: str = ""
    type: str = ""
    description: str = ""
    duration_s: float | None = None
    distance_m: float | None = None


@dataclass
class Interval:
    group_id: str | None = None
    type: str = ""
    start_time: str = ""
    duration_s: float = 0
    distance_m: float = 0
    avg_hr: float | None = None
    max_hr: float | None = None


@dataclass
class SubtPoint:
    """Aggregated work pace, HR, and pace range for a group or session."""

    date: date
    category: str  # "short" | "medium" | "long" | "lt1"
    pace_s_per_km: float
    count: int = 1
    avg_hr: float | None = None
    max_hr: float | None = None
    avg_rep_s: float = 0
    fastest_pace_s_per_km: float | None = None
    slowest_pace_s_per_km: float | None = None
