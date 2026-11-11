"""Data for the dashboard Analysis tab: charts plus the subT report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from ..analysis import (
    RUN_TYPES,
    activity_sort_key,
    average_warmup_days,
    distance_averages,
    is_lt1_activity,
    is_subt_activity,
    load_metrics,
    rpe_metrics,
    subt_session_point,
    time_averages,
    week_bounds,
    weekly_run_distance,
    weekly_time_by_zone,
    zone_time_averages,
)
from ..charts import plot_load, plot_subt, plot_time, plot_volume
from ..html import markdown_to_html
from ..model import AverageWindows
from ..review import exclude_review
from ..subt_report import subt_report

ZONE_COUNT = 4
NO_SUBT = '<p class="muted">No subT or LT1 sessions in this window.</p>'
NO_VOLUME = '<p class="muted">No running volume in this window.</p>'
NO_TIME = '<p class="muted">No running time in this window.</p>'
NO_LOAD = '<p class="muted">No training load in this window.</p>'


@dataclass(frozen=True)
class AnalysisSection:
    """Rendered analysis cards for the dashboard."""

    subt_html: str
    subt_report_html: str
    volume_html: str
    time_html: str
    load_html: str


def _subt_points(source: DataSource, activities):
    points = []

    for activity in sorted(activities, key=activity_sort_key):
        if is_lt1_activity(activity):
            category = "lt1"
        elif is_subt_activity(activity):
            category = None
        else:
            continue

        point = subt_session_point(
            activity,
            source.activity_intervals(activity.id),
            category=category,
        )

        if point is not None:
            points.append(point)

    return points


def build_analysis_section(
    source: DataSource,
    *,
    start: date,
    end: date,
    include_review: bool = False,
) -> AnalysisSection:
    """Build the four analysis charts and the subT report."""
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

    subt = _subt_points(source, display)
    subt_html = (
        plot_subt(subt, "", as_html=True) if subt else NO_SUBT
    )

    subt_report_html = markdown_to_html(
        subt_report(
            start,
            end,
            "subT Report",
            source,
            include_review=include_review,
        ),
        demote=1,
    )

    weekly_distance = weekly_run_distance(display)
    distance_points = distance_averages(
        activities,
        week_start,
        week_end,
        windows=windows,
        warmup_days=warmup_days,
    )
    runs = [
        activity for activity in display if activity.type in RUN_TYPES
    ]
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
    time_html = (
        plot_time(
            weeks,
            "",
            time_points=time_points,
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

    return AnalysisSection(
        subt_html=subt_html,
        subt_report_html=subt_report_html,
        volume_html=volume_html,
        time_html=time_html,
        load_html=load_html,
    )
