"""Data for the dashboard NSA tab: the subT/LT1 chart and report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.datasource import DataSource

from ..analysis import (
    activity_sort_key,
    is_lt1_activity,
    is_subt_activity,
    subt_session_point,
)
from ..charts import plot_subt
from ..html import markdown_to_html
from ..review import exclude_review
from ..subt_report import subt_report

NO_SUBT = '<p class="muted">No subT or LT1 sessions in this window.</p>'


@dataclass(frozen=True)
class NsaSection:
    """Rendered NSA cards for the dashboard."""

    subt_html: str
    subt_report_html: str


def subt_points(source: DataSource, activities):
    """Return one point per subT/LT1 session with work-interval data."""
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


def build_nsa_section(
    source: DataSource,
    *,
    start: date,
    end: date,
    include_review: bool = False,
) -> NsaSection:
    """Build the subT chart and the subT report."""
    activities, _ = exclude_review(
        source.activities(start, end),
        include_review=include_review,
    )
    points = subt_points(source, activities)

    return NsaSection(
        subt_html=(
            plot_subt(points, "", as_html=True) if points else NO_SUBT
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
