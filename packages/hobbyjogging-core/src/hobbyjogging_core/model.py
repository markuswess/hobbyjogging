"""Canonical, source-agnostic training model.

Adapters translate raw payloads from APIs, files, or the local database into
these types. Analysis, charts, and reports depend only on this model.
"""

from dataclasses import dataclass, field
from datetime import date

from .workouts import is_quality


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
    elapsed_s: float = 0
    moving_s: float | None = None
    distance_m: float = 0
    avg_hr: float | None = None
    training_load: float | None = None
    rpe: float | None = None
    feel: int | None = None  # 1 = strong, 2 = good, 3 = normal, 4 = poor, 5 = weak
    intensity: float | None = None  # fraction of threshold (ICU intensity)
    vo2max_garmin: float | None = None
    vo2max_runalyze: float | None = None
    workout_methods: list[str] = field(default_factory=list)
    workout_targets: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    pace_zone_times: list[float] = field(default_factory=list)
    hr_zone_times: list[float] = field(default_factory=list)
    equipment: list[Equipment] = field(default_factory=list)
    needs_review: bool = False  # open review items exist for this activity

    @property
    def vo2max(self) -> float | None:
        """Best available VO2max: Garmin's value, else Runalyze's estimate."""
        return (
            self.vo2max_garmin
            if self.vo2max_garmin is not None
            else self.vo2max_runalyze
        )

    @property
    def quality(self) -> bool | None:
        """Whether the session is quality, non-quality, or unknown."""
        return is_quality(self.workout_methods, self.workout_targets)


@dataclass
class WellnessDay:
    date: date
    hrv: float | None = None
    resting_hr: float | None = None
    sleep_s: float | None = None


@dataclass(frozen=True)
class EventZoneTime:
    """One planned zone bucket for an event (label + planned seconds)."""

    zone_label: str
    seconds: float = 0
    zone_index: int | None = None


@dataclass
class Event:
    date: date
    name: str = ""
    type: str = ""
    description: str = ""
    duration_s: float | None = None
    distance_m: float | None = None
    training_load: float | None = None
    zone_kind: str = ""
    zone_times: list[EventZoneTime] = field(default_factory=list)
    workout_methods: list[str] = field(default_factory=list)
    workout_targets: list[str] = field(default_factory=list)

    @property
    def quality(self) -> bool | None:
        """Whether the planned session is quality, non-quality, or unknown."""
        return is_quality(self.workout_methods, self.workout_targets)


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
class Lap:
    index: int
    start_time_utc: str = ""
    duration_s: float = 0
    distance_m: float = 0
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None


@dataclass
class ReviewItem:
    """One entry in the import review queue.

    Read-only view: the queue is written by importers, triage, and the
    maintenance tasks, never by report code.
    """

    id: int
    category: str
    severity: str = "warn"
    status: str = "open"
    detail: str = ""
    reported_at: str = ""
    activity_id: str | None = None
    activity_date: date | None = None
    activity_name: str = ""
    sport: str = ""
    source: str = ""
    external_id: str = ""
    context: dict[str, object] = field(default_factory=dict)
