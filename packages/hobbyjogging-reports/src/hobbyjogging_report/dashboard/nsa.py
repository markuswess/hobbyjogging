"""Data for the dashboard NSA tab: the subT EWMA report and chart."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from ..analysis import average_warmup_days
from ..charts import plot_subt
from ..command_support import subt_session_points
from ..html import markdown_to_html
from ..model import AverageWindows
from ..review import exclude_review
from ..subt_ewma_report import subt_ewma_markdown
from ..subt_report import subt_report

NO_SUBT = '<p class="muted">No subT or LT1 sessions in this window.</p>'


@dataclass(frozen=True)
class NsaSection:
    """Rendered NSA cards for the dashboard."""

    ewma_report_html: str
    subt_html: str
    subt_report_html: str


def build_nsa_section(
    source: DataSource,
    *,
    start: date,
    end: date,
    include_review: bool = False,
) -> NsaSection:
    """Build the subT EWMA report, the chart, and the subT report."""
    windows = AverageWindows()
    warmup_days = average_warmup_days(windows)
    activities, _ = exclude_review(
        source.activities(start - timedelta(days=warmup_days), end),
        include_review=include_review,
    )
    points = subt_session_points(source, activities)
    window_points = [
        point for point in points if start <= point.date <= end
    ]

    return NsaSection(
        ewma_report_html=markdown_to_html(
            subt_ewma_markdown(points, end, windows=windows),
            demote=1,
        ),
        subt_html=(
            plot_subt(window_points, "", as_html=True)
            if window_points
            else NO_SUBT
        ),
        subt_report_html=markdown_to_html(
            subt_report(
                start,
                end,
                "subT Report",
                source,
                include_review=include_review,
            ),
            demote=1,
        ),
    )
