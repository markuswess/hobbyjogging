"""Report-specific derived types.

Canonical source-agnostic types live in :mod:`hobbyjogging_core.model`.
"""

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.model import ActivityWeather


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
    distance_m: float = 0
    beats: float = 0  # excess heartbeats, above the resting baseline
    efficiency: float | None = None
    lowest_efficiency: float | None = None  # worst work rep
    highest_efficiency: float | None = None  # best work rep


@dataclass
class SubtBlock:
    """One category's work within a session, aggregated for a report row."""

    date: date
    activity_id: str
    activity_name: str
    category: str  # "short" | "medium" | "long" | "lt1"
    count: int
    avg_rep_s: float
    total_time_s: float
    total_distance_m: float
    pace_s_per_km: float
    fastest_pace_s_per_km: float | None = None
    slowest_pace_s_per_km: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    distance_m: float = 0
    beats: float = 0  # excess heartbeats, above the resting baseline
    efficiency: float | None = None


@dataclass
class SubtSummary:
    """Aggregated work volume for one category or a whole report."""

    category: str
    sessions: int = 0
    reps: int = 0
    total_time_s: float = 0
    total_distance_m: float = 0
    pace_s_per_km: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    efficiency: float | None = None


@dataclass(frozen=True)
class AverageWindows:
    """EWMA time constants, in days, for the load chart."""

    base: int = 182
    fitness: int = 42
    fatigue: int = 7


@dataclass
class LoadPoint:
    """Daily running load, other-sport load, and smoothed averages."""

    date: date
    load: float
    base: float
    fitness: float
    fatigue: float
    projected: bool = False
    cross_load: float = 0.0


@dataclass
class RpePoint:
    """Daily session RPE plus its smoothed averages."""

    date: date
    rpe: float | None = None
    base: float | None = None
    fitness: float | None = None
    fatigue: float | None = None


@dataclass
class DistancePoint:
    """Daily running distance plus its smoothed averages."""

    date: date
    distance_km: float
    base: float
    fitness: float
    fatigue: float
    projected: bool = False


@dataclass
class TimePoint:
    """Daily training time plus its smoothed averages."""

    date: date
    time_s: float
    base: float
    fitness: float
    fatigue: float
    projected: bool = False


@dataclass
class ZoneAveragePoint:
    """Smoothed daily time in each pace zone."""

    date: date
    zones: list[float]
    projected: bool = False


@dataclass
class RecoveryPoint:
    """Daily wellness values with calendar-window rolling averages."""

    date: date
    hrv: float | None = None
    resting_hr: float | None = None
    sleep_s: float | None = None
    hrv_avg: float | None = None
    resting_hr_avg: float | None = None
    sleep_avg: float | None = None


@dataclass
class TimeZoneWeek:
    """Weekly training seconds split by pace zone, plus unzoned time."""

    week: date
    zones: list[float]
    unzoned: float = 0.0


@dataclass(frozen=True)
class ComparePeriod:
    """Basic training totals for one year or calendar month."""

    label: str
    runs: int = 0
    cross_sessions: int = 0
    run_time_s: float = 0
    cross_time_s: float = 0
    run_distance_m: float = 0
    pace_s_per_km: float | None = None
    avg_hr: float | None = None
    efficiency: float | None = None
    vo2max_garmin: float | None = None


@dataclass(frozen=True)
class Vo2maxMeasurement:
    """One raw VO2max reading (Garmin or Runalyze) from one activity."""

    date: date
    value: float


@dataclass(frozen=True)
class Vo2maxSample:
    """One activity's effective VO2max, before daily averaging."""

    date: date
    value: float


@dataclass
class Vo2maxPoint:
    """Daily effective VO2max plus its 42- and 182-day EWMAs."""

    date: date
    value: float | None = None
    avg_42: float | None = None
    avg_182: float | None = None


@dataclass(frozen=True)
class GarminVo2maxDevice:
    """One recorder's Garmin readings and their 42-day carry-forward EWMA."""

    device_id: str
    label: str
    measurements: list[Vo2maxMeasurement]
    avg_42: list[tuple[date, float | None]]


@dataclass(frozen=True)
class Vo2maxMethods:
    """Every series the VO2max methods chart compares."""

    all_runs: list[Vo2maxPoint]
    steady: list[Vo2maxPoint]
    garmin: list[GarminVo2maxDevice]
    runalyze: list[Vo2maxMeasurement]
    runalyze_avg_42: list[tuple[date, float | None]]
    races: list[tuple[date, float]]


@dataclass(frozen=True)
class PaceHrPoint:
    """One run's average speed and average heart rate."""

    date: date
    pace_s_per_km: float
    avg_hr: float
    name: str = ""
    resting_hr: float | None = None
    distance_m: float = 0
    excess_beats: float = 0
    steady: bool = False
    category: str = ""
    weather: ActivityWeather | None = None

    @property
    def speed_m_s(self) -> float:
        """Average speed in m/s (linear pace axis)."""
        return 1000 / self.pace_s_per_km
