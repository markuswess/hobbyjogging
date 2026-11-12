"""Data for the dashboard Analysis tab: volume, time, and load charts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from ..analysis import (
    RESTING_HR_WINDOW_DAYS,
    RUN_TYPES,
    average_warmup_days,
    distance_averages,
    load_metrics,
    pace_hr_points,
    resting_hr_baselines,
    rpe_metrics,
    time_averages,
    week_bounds,
    weekly_run_distance,
    weekly_time_by_zone,
    zone_time_averages,
)
from ..charts import plot_load, plot_pace_hr, plot_time, plot_volume
from ..model import AverageWindows
from ..review import exclude_review

ZONE_COUNT = 4
NO_VOLUME = '<p class="muted">No running volume in this window.</p>'
NO_TIME = '<p class="muted">No running time in this window.</p>'
NO_LOAD = '<p class="muted">No training load in this window.</p>'
NO_PACE_HR = (
    '<p class="muted">No runs with pace and heart rate in this window.</p>'
)


@dataclass(frozen=True)
class AnalysisSection:
    """Rendered analysis cards for the dashboard."""

    volume_html: str
    time_html: str
    load_html: str
    pace_hr_html: str


def build_analysis_section(
    source: DataSource,
    *,
    start: date,
    end: date,
    include_review: bool = False,
) -> AnalysisSection:
    """Build the volume, time, and load charts."""
    windows = AverageWindows()
    warmup_days = average_warmup_days(windows)
    activities, _ = exclude_review(
        source.activities(start - timedelta(days=warmup_days), end),
        include_review=include_review,
    )
    display = [
        activity
        for activity in activities
        if start <= activity.date <= end
    ]
    week_start, week_end = week_bounds(start, end)
    runs = [
        activity for activity in display if activity.type in RUN_TYPES
    ]

    weekly_distance = weekly_run_distance(display)
    distance_points = distance_averages(
        activities,
        week_start,
        week_end,
        windows=windows,
        warmup_days=warmup_days,
    )
    volume_html = (
        plot_volume(
            weekly_distance,
            "",
            distance_points=distance_points,
            as_html=True,
        )
        if any(activity.distance_m for activity in runs)
        else NO_VOLUME
    )

    weeks = weekly_time_by_zone(
        display,
        week_start,
        week_end,
        zone_count=ZONE_COUNT,
    )
    time_points = time_averages(
        activities,
        week_start,
        week_end,
        windows=windows,
        warmup_days=warmup_days,
    )
    hard_points = time_averages(
        activities,
        week_start,
        week_end,
        windows=windows,
        warmup_days=warmup_days,
        zones=(3, 4),
    )
    time_html = (
        plot_time(
            weeks,
            "",
            time_points=time_points,
            hard_points=hard_points,
            zone_points=zone_time_averages(
                activities,
                week_start,
                week_end,
                window_days=windows.base,
                warmup_days=warmup_days,
                zone_count=ZONE_COUNT,
            ),
            zone_window_days=windows.base,
            windows=windows,
            as_html=True,
        )
        if any((activity.duration_s or 0) for activity in runs)
        else NO_TIME
    )

    load_points = load_metrics(
        activities,
        start,
        end,
        windows=windows,
        warmup_days=warmup_days,
    )
    load_html = (
        plot_load(
            load_points,
            "",
            windows=windows,
            rpe_points=rpe_metrics(
                activities,
                start,
                end,
                windows=windows,
                warmup_days=warmup_days,
            ),
            as_html=True,
        )
        if any(point.load > 0 for point in load_points)
        else NO_LOAD
    )

    baseline = resting_hr_baselines(
        source.wellness(
            start - timedelta(days=RESTING_HR_WINDOW_DAYS),
            end,
        )
    )
    points = pace_hr_points(
        display,
        start,
        end,
        resting_hr_baseline=baseline,
    )
    pace_hr_html = (
        plot_pace_hr(points, "", as_html=True)
        if points
        else NO_PACE_HR
    )

    return AnalysisSection(
        volume_html=volume_html,
        time_html=time_html,
        load_html=load_html,
        pace_hr_html=pace_hr_html,
    )
