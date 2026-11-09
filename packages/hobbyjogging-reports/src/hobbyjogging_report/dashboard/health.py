"""Data-health summary for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.model import Activity

from ..analysis import RUN_TYPES


@dataclass(frozen=True)
class DataHealth:
    start: date
    end: date
    activities: int
    review_hidden: int
    review_flagged: list[Activity]
    runs_without_pace_zones: int
    runs_without_distance: int
    runs_without_hr: int
    activities_without_load: int

    @property
    def missing_total(self) -> int:
        return (
            self.runs_without_pace_zones
            + self.runs_without_distance
            + self.runs_without_hr
            + self.activities_without_load
        )

    @property
    def is_ok(self) -> bool:
        return self.review_hidden == 0 and self.missing_total == 0


def collect_health(
    raw_activities: list[Activity],
    display_activities: list[Activity],
    *,
    start: date,
    end: date,
    include_review: bool,
) -> DataHealth:
    """Build health counts from the raw and review-filtered window."""
    review_flagged = [
        activity for activity in raw_activities if activity.needs_review
    ]
    runs = [
        activity
        for activity in display_activities
        if activity.type in RUN_TYPES
    ]

    return DataHealth(
        start=start,
        end=end,
        activities=len(display_activities),
        review_hidden=0 if include_review else len(review_flagged),
        review_flagged=review_flagged,
        runs_without_pace_zones=sum(
            1 for activity in runs if not activity.pace_zone_times
        ),
        runs_without_distance=sum(
            1 for activity in runs if not activity.distance_m
        ),
        runs_without_hr=sum(
            1 for activity in runs if activity.avg_hr is None
        ),
        activities_without_load=sum(
            1
            for activity in display_activities
            if activity.training_load is None
        ),
    )


def banner(
    health: DataHealth,
    *,
    root: str = "",
    include_review: bool = False,
) -> str:
    """Render the compact banner shown on every page."""
    parts = []

    if health.review_hidden:
        parts.append(
            f"{health.review_hidden} activities with open review items "
            "are hidden"
        )
    elif health.review_flagged and include_review:
        parts.append(
            f"{len(health.review_flagged)} activities with open review "
            "items are included"
        )

    missing = []

    if health.runs_without_pace_zones:
        missing.append(
            f"{health.runs_without_pace_zones} runs without pace zones"
        )
    if health.activities_without_load:
        missing.append(
            f"{health.activities_without_load} without load"
        )
    if health.runs_without_hr:
        missing.append(f"{health.runs_without_hr} runs without HR")
    if health.runs_without_distance:
        missing.append(
            f"{health.runs_without_distance} runs without distance"
        )

    if missing:
        parts.append("missing data: " + ", ".join(missing))

    if not parts:
        return (
            '<div class="banner ok">Data health OK for this window.</div>'
        )

    severity = "bad" if health.review_hidden else "warn"
    details = f' <a href="{root}health.html">Details</a>'

    return (
        f'<div class="banner {severity}">'
        + " · ".join(parts)
        + details
        + "</div>"
    )
