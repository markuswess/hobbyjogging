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
