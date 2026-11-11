"""Data for the dashboard Compare tab: year/month reports plus the chart."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.datasource import DataSource

from ..analysis import compare_year_ewma
from ..charts import plot_compare
from ..command_support import activity_start
from ..compare import compare_report
from ..html import markdown_to_html
from ..review import exclude_review
from .reports import _months_before

NO_CHART = '<p class="muted">No activities to compare.</p>'


@dataclass(frozen=True)
class CompareSection:
    """Rendered compare cards for the dashboard."""

    chart_html: str
    years_report_html: str
    months_report_html: str


def build_compare_section(
    source: DataSource,
    *,
    today: date,
    metric: str,
    window: int,
    include_review: bool = False,
) -> CompareSection:
    """Build the year comparison chart and the two compare reports."""
    start = activity_start(source, today)
    activities, _ = exclude_review(
        source.activities(start, today),
        include_review=include_review,
    )
    series = compare_year_ewma(
        activities,
        metric,
        window,
        today=today,
    )

    return CompareSection(
        chart_html=(
            plot_compare(
                series,
                "",
                metric=metric,
                window=window,
                today=today,
                title=f"Year comparison — {metric}, {window}-day EWMA",
                as_html=True,
            )
            if series
            else NO_CHART
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
