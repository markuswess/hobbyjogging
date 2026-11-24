"""Volume bar chart."""

from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go

from hobbyjogging_core.model import TrainingPeriod

from ..model import AverageWindows, DistancePoint
from ..style import SEASON_BAND_COLOR, VOLUME_Y_MIN, VOLUME_Y_STEP

from .common import (
    VOLUME_BAR_COLOR,
    WEEK_MS,
    _axis_ceiling,
    _base_layout,
    _clipped_markers,
    _crosshair,
    _fade,
    _period_bands,
    _plot_average_lines,
    _render,
    _require_data,
)


def plot_volume(
    data: list[tuple[date, float]],
    output: str,
    *,
    distance_points: list[DistancePoint] | None = None,
    planned_distance: list[tuple[date, float]] | None = None,
    windows: AverageWindows | None = None,
    distance_scale: float = 7.0,
    ylabel: str = "km / week",
    title: str = "Weekly running volume",
    periods: list[TrainingPeriod] | None = None,
    as_html: bool = False,
) -> str:
    """Weekly running volume bars with distance-average lines."""
    _require_data(data, distance_points)
    windows = windows or AverageWindows()
    weeks = [week for week, _ in data]
    actual_by_week = dict(data)
    planned_by_week = dict(planned_distance or [])
    planned_marks = [
        (week, value + actual_by_week.get(week, 0.0))
        for week, value in planned_by_week.items()
    ]
    axis_weeks = sorted(set(weeks) | set(planned_by_week))
    ceiling = max(
        _axis_ceiling(
            [value for _, value in data]
            + [value for _, value in planned_marks],
            step=VOLUME_Y_STEP,
            floor=VOLUME_Y_MIN,
        ),
        _axis_ceiling(
            [
                getattr(point, attribute) * distance_scale
                for point in distance_points or []
                for attribute in ("base", "fitness")
            ],
            step=VOLUME_Y_STEP,
            floor=VOLUME_Y_MIN,
        ),
    )

    figure = go.Figure()

    if axis_weeks:
        _period_bands(
            figure,
            periods,
            kind="season",
            color=SEASON_BAND_COLOR,
            start=axis_weeks[0],
            end=axis_weeks[-1] + timedelta(days=7),
            bottom=0,
            top=ceiling,
            labels=True,
        )

    if data:
        figure.add_bar(
            x=weeks,
            y=[value for _, value in data],
            name="weekly km",
            width=WEEK_MS,
            marker_color=VOLUME_BAR_COLOR,
        )

    if planned_distance:
        figure.add_bar(
            x=[week for week, _ in planned_distance],
            y=[value for _, value in planned_distance],
            # The current week already has an actual bar; stack the plan for
            # its remaining days on top of it.
            base=[
                actual_by_week.get(week, 0.0)
                for week, _ in planned_distance
            ],
            name="planned km",
            width=WEEK_MS,
            marker={
                "color": _fade(VOLUME_BAR_COLOR, 0.45),
                "line": {"color": "#9aa5b1", "width": 0.6},
                "pattern": {
                    "shape": "/",
                    "fgcolor": "#9aa5b1",
                    "solidity": 0.45,
                },
            },
        )

    if distance_points:
        _plot_average_lines(
            figure,
            distance_points,
            windows,
            scale=distance_scale,
            label=lambda attribute, days: f"{days}d avg (weekly)",
        )

    _clipped_markers(
        figure,
        list(data) + planned_marks,
        ceiling,
        "km",
    )
    figure.update_yaxes(range=[0, ceiling], dtick=20)

    if axis_weeks:
        figure.update_xaxes(
            range=[
                axis_weeks[0],
                axis_weeks[-1] + timedelta(days=7),
            ]
        )

    _base_layout(
        figure,
        title=title,
        xlabel="week starting (Monday)",
        ylabel=ylabel,
    )
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=1500,
    )
