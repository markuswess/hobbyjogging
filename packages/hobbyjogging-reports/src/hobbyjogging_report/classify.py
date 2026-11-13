"""Workout categorization for display.

The heuristic itself lives in :mod:`hobbyjogging_core.classify`; this module
keeps the report-facing aggregation (category stats and their ordering) and
re-exports the classifier so existing imports keep working.
"""

from dataclasses import dataclass

from hobbyjogging_core.classify import (
    CROSS_TRAINING,
    UNKNOWN,
    Category,
    classify,
)
from hobbyjogging_core.model import Activity, Interval

from .analysis.common import RUN_TYPES
from .analysis.efficiency import (
    STEADY_DURATION_BAND,
    excess_beats,
    is_steady_run,
)

GROUP_ORDER = {
    "quality": 0,
    "non-quality": 1,
    "cross-training": 2,
    "unknown": 3,
}


@dataclass
class CategoryStat:
    """Aggregated training volume for one category."""

    category: Category
    sessions: int = 0
    time_s: float = 0
    load: float = 0
    time_share: float = 0
    load_share: float = 0
    distance_m: float = 0
    excess_beats: float = 0

    @property
    def path(self) -> str:
        return self.category.path

    @property
    def efficiency(self) -> float | None:
        if self.excess_beats <= 0 or self.distance_m <= 0:
            return None
        return self.distance_m / self.excess_beats


def category_breakdown(
    activities: list[Activity],
    intervals_by_id: dict[str, list[Interval]] | None = None,
    *,
    resting_hr_baseline=None,
    steady_duration_band: tuple[float, float] = STEADY_DURATION_BAND,
) -> list[CategoryStat]:
    """Aggregate activities by category, grouped and sorted by time.

    ``intervals_by_id`` is optional; when provided it refines subT rep
    lengths. Without it, subT sessions collapse into ``intervals/subt``.
    """
    intervals_by_id = intervals_by_id or {}
    stats: dict[str, CategoryStat] = {}

    for activity in activities:
        category = classify(activity, intervals_by_id.get(activity.id))
        stat = stats.get(category.path)

        if stat is None:
            stat = stats[category.path] = CategoryStat(category)

        stat.sessions += 1
        stat.time_s += activity.duration_s or 0
        stat.load += activity.training_load or 0

        if activity.type in RUN_TYPES and is_steady_run(
            activity,
            duration_band=steady_duration_band,
            intervals=intervals_by_id.get(activity.id, []),
        ):
            beats = excess_beats(
                activity.duration_s,
                activity.avg_hr,
                (
                    resting_hr_baseline(activity.date)
                    if resting_hr_baseline is not None
                    else None
                ),
            )

            if beats is not None and activity.distance_m:
                stat.distance_m += activity.distance_m
                stat.excess_beats += beats

    total_time = sum(stat.time_s for stat in stats.values())
    total_load = sum(stat.load for stat in stats.values())

    for stat in stats.values():
        stat.time_share = stat.time_s / total_time if total_time else 0
        stat.load_share = stat.load / total_load if total_load else 0

    return sorted(
        stats.values(),
        key=lambda stat: (
            GROUP_ORDER.get(stat.category.group, len(GROUP_ORDER)),
            -stat.time_s,
        ),
    )
