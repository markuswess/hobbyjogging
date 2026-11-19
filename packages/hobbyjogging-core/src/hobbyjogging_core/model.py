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
class Route:
    """A named loop or course, independent of the activity that ran it."""

    id: str
    name: str = ""
    external_ref: str = ""
    distance_m: float | None = None
    source: str = ""
    notes: str = ""


@dataclass
class ActivityRoute:
    """Link between an activity and a route it covered."""

    activity_id: str
    route_id: str
    source: str = "manual"
    is_manual: bool = False


@dataclass
class ActivityEquipment:
    """Link between an activity and a piece of equipment."""

    activity_id: str
    equipment_id: str
    role: str = "primary"  # "primary", "secondary"
    source: str = "manual"
    is_manual: bool = False


@dataclass
class ActivitySocial:
    """Social text attached to an activity by one source."""

    activity_id: str
    source: str
    title: str = ""
    description: str = ""
    external_id: str = ""
    url: str = ""
    is_manual: bool = False


@dataclass
class Activity:
    id: str
    date: date
    started_at_utc: str = ""  # ISO timestamp, used for same-day ordering
    type: str = ""  # canonical: "run", "trail_run", "ride", ...
    sub_sport: str = ""
    name: str = ""
    description: str = ""
    duration_s: float = 0
    elapsed_s: float = 0
    moving_s: float | None = None
    distance_m: float = 0
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
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
    routes: list[Route] = field(default_factory=list)
    device_id: str = ""
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
    weight_kg: float | None = None
    sleep_score: float | None = None
    sleep_quality: float | None = None
    spo2: float | None = None
    steps: int | None = None
    floors_climbed: int | None = None
    ctl: float | None = None
    atl: float | None = None


@dataclass(frozen=True)
class EventZoneTime:
    """One planned zone bucket for an event (label + planned seconds)."""

    zone_label: str
    seconds: float = 0
    zone_index: int | None = None


@dataclass
class Event:
    date: date
    id: str = ""  # canonical event id, stable across imports
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
class EventActivityLink:
    """A planned event and the activity that ran it."""

    event_id: str
    activity_id: str
    match_method: str = "auto"
    confidence: float | None = None
    is_manual: bool = False


@dataclass
class TrainingPeriod:
    """A dated span: a season, a plan, an illness, a trip or a recovery."""

    id: str
    kind: str
    label: str = ""
    start_date: date | None = None
    end_date: date | None = None
    source: str = ""
    notes: str = ""


@dataclass
class Device:
    """A recording device: the watch, computer or sensor behind an activity."""

    id: str
    manufacturer: str = ""
    product: str = ""
    serial_number: str = ""
    name: str = ""
    acquired_on: date | None = None
    retired_on: date | None = None
    notes: str = ""


@dataclass
class RaceResult:
    """Official race metadata, kept apart from the measured GPS values."""

    activity_id: str
    date: date | None = None
    name: str = ""
    official_distance_m: float | None = None
    official_time_s: float | None = None
    officially_measured: bool | None = None
    place_total: int | None = None
    place_gender: int | None = None
    place_ageclass: int | None = None
    participants_total: int | None = None
    participants_gender: int | None = None
    participants_ageclass: int | None = None
    priority_level: str = ""
    status: str = "completed"
    notes: str = ""
    event_id: str | None = None
    source: str = "manual"


@dataclass
class AthleteThreshold:
    """One dated snapshot of the athlete's threshold settings."""

    effective_from: date
    sport: str = ""
    max_hr: float | None = None
    lthr: float | None = None
    threshold_pace_mps: float | None = None
    source: str = ""


@dataclass
class ZoneConfig:
    """One set of zone boundaries, shared by the activities of its era."""

    id: str
    kind: str
    boundaries: list[float]
    source: str = ""


@dataclass
class ActivityWeather:
    """The weather recorded for one activity, in metric units."""

    temp_c: float | None = None
    feels_like_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_ms: float | None = None
    wind_degree: float | None = None
    wind_gust_ms: float | None = None
    wind_chill_c: float | None = None
    heat_index_c: float | None = None
    pressure_hpa: float | None = None
    uv_index: float | None = None
    clouds_pct: float | None = None
    condition: str = ""
    is_night: bool | None = None
    source: str = ""


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
