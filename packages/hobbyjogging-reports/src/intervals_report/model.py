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
