"""Report-specific derived types.

Canonical source-agnostic types live in :mod:`hobbyjogging_core.model`.
"""

from dataclasses import dataclass
from datetime import date


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


@dataclass(frozen=True)
class AverageWindows:
    """EWMA time constants, in days, for the load chart."""

    base: int = 182
    fitness: int = 42
    fatigue: int = 7


@dataclass
class LoadPoint:
    """Daily training load plus its smoothed averages."""

    date: date
    load: float
    base: float
    fitness: float
    fatigue: float
    projected: bool = False


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
