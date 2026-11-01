"""Canonical, source-agnostic training model.

Adapters translate raw payloads from APIs, files, or the local database into
these types. Analysis, charts, and reports depend only on this model.
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Equipment:
    """A piece of equipment used for training, usually a pair of shoes."""

    id: str
    type: str  # canonical: "shoe", "bike", "other"
    name: str
    brand: str = ""
    model: str = ""
    acquired_on: date | None = None
    retired_on: date | None = None
    target_distance_m: float | None = None
    notes: str = ""


@dataclass
class ActivityEquipment:
    """Link between an activity and a piece of equipment."""

    activity_id: str
    equipment_id: str
    role: str = "primary"  # "primary", "secondary"
    source: str = "manual"
    is_manual: bool = False


@dataclass
class Activity:
    id: str
    date: date
    started_at_utc: str = ""  # ISO timestamp, used for same-day ordering
    type: str = ""  # canonical: "run", "trail_run", "ride", ...
    name: str = ""
    description: str = ""
    duration_s: float = 0
    distance_m: float = 0
    avg_hr: float | None = None
    training_load: float | None = None
    rpe: float | None = None
    feel: int | None = None  # 1 = strong, 2 = good, 3 = normal, 4 = poor, 5 = weak
    intensity: float | None = None  # fraction of threshold (ICU intensity)
    pace_zone_times: list[float] = field(default_factory=list)
    hr_zone_times: list[float] = field(default_factory=list)
    equipment: list[Equipment] = field(default_factory=list)


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
