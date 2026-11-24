"""Plotly chart builders shared by the CLI and the dashboard.

The builders are split by chart family; this module keeps the import path
used by the CLI and the dashboard.
"""

from __future__ import annotations

from ..defaults import PACE_HR_SPEED_RANGE
from .common import PACE_HR_SYMBOLS, PB_COLORS, _axis_ceiling, compare_color
from .volume import plot_volume
from .time import plot_time
from .subt import plot_subt
from .load import plot_load
from .vo2max import plot_vo2max_methods
from .pace_hr import plot_compare_pace_hr, plot_pace_hr
from .races import plot_pb_progressions, plot_races
from .gear import plot_devices, plot_equipment, plot_thresholds
from .compare import plot_compare, plot_compare_vo2max
from .recovery import plot_recovery
from .overview import plot_overview

__all__ = [
    "PACE_HR_SPEED_RANGE",
    "PACE_HR_SYMBOLS",
    "PB_COLORS",
    "_axis_ceiling",
    "compare_color",
    "plot_volume",
    "plot_time",
    "plot_subt",
    "plot_load",
    "plot_vo2max_methods",
    "plot_compare_pace_hr",
    "plot_pace_hr",
    "plot_pb_progressions",
    "plot_races",
    "plot_devices",
    "plot_equipment",
    "plot_thresholds",
    "plot_compare",
    "plot_compare_vo2max",
    "plot_recovery",
    "plot_overview",
]
