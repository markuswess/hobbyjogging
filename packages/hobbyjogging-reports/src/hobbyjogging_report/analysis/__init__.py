"""Source-agnostic analysis, re-exported from domain modules.

Functions take model objects (see ``hobbyjogging_core.model``) and return
plain Python structures. They never touch the API, a database, or plotting.
"""

from .averages import (
    AVERAGE_WARMUP_FACTOR,
    DEFAULT_AVERAGE_WINDOWS,
    average_warmup_days,
)
from .compare import COMPARE_MODES, compare_periods
from .common import (
    CATEGORY_LONG,
    CATEGORY_MEDIUM,
    CATEGORY_SHORT,
    DEFAULT_ZONE_COUNT,
    LT1_WORDS,
    RUN_TYPES,
    SUBT_CATEGORIES,
    SUBT_CATEGORY_ORDER,
    activity_sort_key,
    classify_interval,
    event_zone_seconds,
    event_zone_time,
    is_lt1_activity,
    is_subt_activity,
    pace_s_per_km,
    week_bounds,
    week_end,
    week_start,
    work_intervals,
)
from .load import (
    daily_run_distance,
    daily_training_load,
    distance_averages,
    load_metrics,
    weekly_run_distance,
)
from .planned import (
    daily_planned_distance,
    daily_planned_load,
    daily_planned_time,
    planned_workout_dates,
    weekly_planned_distance,
    weekly_planned_time,
)
from .recovery import recovery_trends
from .subt import (
    subt_blocks,
    subt_report_blocks,
    subt_report_summary,
    subt_session_point,
    subt_work_points,
)
from .zones import (
    daily_planned_zone_time,
    daily_run_time,
    daily_zone_time,
    time_averages,
    weekly_planned_time_by_zone,
    weekly_time_by_zone,
    zone_time_averages,
)

__all__ = [
    "AVERAGE_WARMUP_FACTOR",
    "CATEGORY_LONG",
    "CATEGORY_MEDIUM",
    "CATEGORY_SHORT",
    "COMPARE_MODES",
    "DEFAULT_AVERAGE_WINDOWS",
    "DEFAULT_ZONE_COUNT",
    "LT1_WORDS",
    "RUN_TYPES",
    "SUBT_CATEGORIES",
    "SUBT_CATEGORY_ORDER",
    "activity_sort_key",
    "average_warmup_days",
    "classify_interval",
    "compare_periods",
    "daily_planned_distance",
    "daily_planned_load",
    "daily_planned_time",
    "daily_planned_zone_time",
    "daily_run_distance",
    "daily_run_time",
    "daily_training_load",
    "daily_zone_time",
    "distance_averages",
    "event_zone_seconds",
    "event_zone_time",
    "is_lt1_activity",
    "is_subt_activity",
    "load_metrics",
    "pace_s_per_km",
    "planned_workout_dates",
    "recovery_trends",
    "subt_blocks",
    "subt_report_blocks",
    "subt_report_summary",
    "subt_session_point",
    "subt_work_points",
    "time_averages",
    "week_bounds",
    "week_end",
    "week_start",
    "weekly_planned_distance",
    "weekly_planned_time",
    "weekly_planned_time_by_zone",
    "weekly_run_distance",
    "weekly_time_by_zone",
    "work_intervals",
    "zone_time_averages",
]
