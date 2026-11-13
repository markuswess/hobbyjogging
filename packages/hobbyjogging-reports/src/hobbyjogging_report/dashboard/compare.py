"""Data for the dashboard Compare tab: year/month reports plus the chart."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from ..analysis import (
    RUN_TYPES,
    compare_year_ewma,
    compare_year_planned_ewma,
    pace_hr_points,
    STEADY_BAND_LABEL,
    vo2max_measurements,
)
from ..charts import (
    plot_compare,
    plot_compare_pace_hr,
    plot_compare_vo2max,
)
from ..command_support import activity_start, resting_hr_lookup
from ..compare import compare_report
from ..html import markdown_to_html
from ..review import exclude_review
from .reports import _months_before

NO_CHART = '<p class="muted">No activities to compare.</p>'
NO_PACE_HR = (
    '<p class="muted">No runs with pace and heart rate to compare.</p>'
)
NO_VO2MAX = '<p class="muted">No Garmin VO2max readings to compare.</p>'


@dataclass(frozen=True)
class CompareSection:
    """Rendered compare cards for the dashboard."""

    volume_html: str
    time_html: str
    efficiency_html: str
    vo2max_html: str
    pace_hr_html: str
    years_report_html: str
    months_report_html: str


def build_compare_section(
    source: DataSource,
    *,
    today: date,
    window: int,
    include_review: bool = False,
) -> CompareSection:
    """Build the year comparison chart and the two compare reports."""
    start = activity_start(source, today)
    activities, _ = exclude_review(
        source.activities(start, today),
        include_review=include_review,
    )

    baseline = resting_hr_lookup(source, start, today)
    events = source.events(start, today + timedelta(days=366))
    pace_hr = pace_hr_points(
        activities,
        start,
        today,
        resting_hr_baseline=baseline,
        intervals_by_id={
            activity.id: source.activity_intervals(activity.id)
            for activity in activities
            if activity.type in RUN_TYPES
        },
    )
    vo2max = vo2max_measurements(activities, start, today)

    def chart(metric: str) -> str:
        series = compare_year_ewma(
            activities,
            metric,
            window,
            today=today,
            resting_hr=baseline,
        )

        if not series:
            return NO_CHART

        return plot_compare(
            series,
            "",
            metric=metric,
            window=window,
            today=today,
            title=(
                f"Year comparison — steady efficiency "
                f"({STEADY_BAND_LABEL}), {window}-day EWMA"
                if metric == "efficiency"
                else f"Year comparison — {metric}, {window}-day EWMA"
            ),
            planned_series=compare_year_planned_ewma(
                activities,
                events,
                metric,
                window,
                today=today,
            ),
            as_html=True,
        )

    return CompareSection(
        volume_html=chart("volume"),
        time_html=chart("time"),
        efficiency_html=chart("efficiency"),
        vo2max_html=(
            plot_compare_vo2max(vo2max, "", as_html=True)
            if vo2max
            else NO_VO2MAX
        ),
        pace_hr_html=(
            plot_compare_pace_hr(pace_hr, "", as_html=True)
            if pace_hr
            else NO_PACE_HR
        ),
        years_report_html=markdown_to_html(
            compare_report(
                "years",
                None,
                today,
                source,
                include_review=include_review,
            ),
            demote=1,
        ),
        months_report_html=markdown_to_html(
            compare_report(
                "months",
                _months_before(today, 11),
                today,
                source,
                include_review=include_review,
            ),
            demote=1,
        ),
    )
