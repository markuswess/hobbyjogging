"""subT and LT1 work-interval panel."""

from __future__ import annotations

from datetime import timedelta
import math

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..analysis import EFFICIENCY_UNIT
from ..format import format_pace
from ..model import SubtPoint
from ..style import SUBT_HR_RANGE, SUBT_PACE_RANGE

from .common import (
    CHART_CATEGORIES,
    SUBT_COLORS,
    _bulk_range,
    _crosshair,
    _legend_below,
    _render,
    _require_data,
)


def _subt_points_for(points: list[SubtPoint], category: str, value):
    return sorted(
        (
            point for point in points
            if point.category == category and value(point) is not None
        ),
        key=lambda point: point.date,
    )


def _time_ewma(dates, values, window_days: int):
    """Gap-aware EWMA evaluated at each observation date."""
    state = None
    last = None
    result = []

    for day, value in zip(dates, values):
        if state is None:
            state = value
        else:
            gap = max((day - last).days, 1)
            alpha = 1 - math.exp(-gap / window_days)
            state = alpha * value + (1 - alpha) * state

        result.append(state)
        last = day

    return result


def _weighted_efficiency(points, window_days: int):
    """Trailing weighted efficiency: sum(distance) / sum(excess beats)."""
    curve = []

    for point in points:
        cutoff = point.date - timedelta(days=window_days - 1)
        distance = 0.0
        beats = 0.0

        for sample in points:
            if not (cutoff <= sample.date <= point.date):
                continue
            if sample.beats <= 0 or not sample.distance_m:
                continue

            distance += sample.distance_m
            beats += sample.beats

        curve.append(distance / beats if beats > 0 else None)

    return curve


def plot_subt(
    points: list[SubtPoint],
    output: str,
    window_days: int = 42,
    title: str = "subT and LT1 work intervals",
    as_html: bool = False,
) -> str:
    """Pace and heart rate in two stacked panels sharing a date axis.

    Lines are gap-aware EWMAs with a 42-day time constant.
    """
    _require_data(points)
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[3, 2, 2],
        vertical_spacing=0.08,
        subplot_titles=("Pace", "Average heart rate", "Efficiency"),
    )
    plotted = False

    for category in CHART_CATEGORIES:
        color = SUBT_COLORS[category]
        pace = _subt_points_for(
            points,
            category,
            lambda point: point.pace_s_per_km,
        )

        if pace:
            plotted = True
            dates = [point.date for point in pace]
            values = [point.pace_s_per_km for point in pace]

            for point in pace:
                if (
                    point.fastest_pace_s_per_km is None
                    or point.slowest_pace_s_per_km is None
                ):
                    continue

                figure.add_trace(
                    go.Scatter(
                        x=[point.date, point.date],
                        y=[
                            point.fastest_pace_s_per_km,
                            point.slowest_pace_s_per_km,
                        ],
                        mode="lines",
                        line={"color": color, "width": 1.1},
                        opacity=0.35,
                        showlegend=False,
                        hoverinfo="skip",
                    ),
                    row=1,
                    col=1,
                )

            if len(pace) >= 2:
                figure.add_trace(
                    go.Scatter(
                        x=dates,
                        y=_time_ewma(dates, values, window_days),
                        mode="lines",
                        name=f"{category} pace avg",
                        line={"color": color, "width": 1.8},
                        opacity=0.55,
                        showlegend=False,
                    ),
                    row=1,
                    col=1,
                )

            figure.add_trace(
                go.Scatter(
                    x=dates,
                    y=values,
                    mode="markers",
                    marker={"color": color, "size": 7},
                    name=f"{category} ({len(pace)})",
                ),
                row=1,
                col=1,
            )

        hr = _subt_points_for(
            points,
            category,
            lambda point: point.avg_hr,
        )

        if not hr:
            continue

        plotted = True
        dates = [point.date for point in hr]
        values = [point.avg_hr for point in hr]

        for point in hr:
            if point.max_hr is None:
                continue

            figure.add_trace(
                go.Scatter(
                    x=[point.date, point.date],
                    y=[point.avg_hr, point.max_hr],
                    mode="lines",
                    line={"color": color, "width": 1.1},
                    opacity=0.3,
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=2,
                col=1,
            )
            figure.add_trace(
                go.Scatter(
                    x=[point.date],
                    y=[point.max_hr],
                    mode="markers",
                    marker={
                        "color": color,
                        "size": 10,
                        "symbol": "line-ns",
                    },
                    name=f"{category} max HR",
                    showlegend=False,
                ),
                row=2,
                col=1,
            )

        if len(hr) >= 2:
            figure.add_trace(
                go.Scatter(
                    x=dates,
                    y=_time_ewma(dates, values, window_days),
                    mode="lines",
                    name=f"{category} HR avg",
                    line={"color": color, "width": 1.8},
                    opacity=0.55,
                    showlegend=False,
                ),
                row=2,
                col=1,
            )

        figure.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                mode="markers",
                marker={"color": color, "size": 7},
                name=f"{category} HR",
                showlegend=False,
            ),
            row=2,
            col=1,
        )

    for category in CHART_CATEGORIES:
        color = SUBT_COLORS[category]
        efficiency = _subt_points_for(
            points,
            category,
            lambda point: point.efficiency,
        )

        if not efficiency:
            continue

        dates = [point.date for point in efficiency]

        # The rep range, like the pace panel's fastest/slowest sticks.
        for point in efficiency:
            if (
                point.lowest_efficiency is None
                or point.highest_efficiency is None
                or point.lowest_efficiency == point.highest_efficiency
            ):
                continue

            figure.add_trace(
                go.Scatter(
                    x=[point.date, point.date],
                    y=[
                        point.lowest_efficiency,
                        point.highest_efficiency,
                    ],
                    mode="lines",
                    line={"color": color, "width": 1.1},
                    opacity=0.35,
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=3,
                col=1,
            )

        figure.add_trace(
            go.Scatter(
                x=dates,
                y=[point.efficiency for point in efficiency],
                mode="markers",
                marker={"color": color, "size": 7},
                text=[
                    (
                        f"{point.date} {category}"
                        f"<br>E {point.efficiency:.2f} {EFFICIENCY_UNIT}"
                        + (
                            f", reps {point.lowest_efficiency:.2f}–"
                            f"{point.highest_efficiency:.2f}"
                            if point.lowest_efficiency is not None
                            and point.highest_efficiency is not None
                            else ""
                        )
                        + f", n={point.count}"
                    )
                    for point in efficiency
                ],
                hoverinfo="text",
                name=f"{category} efficiency",
                showlegend=False,
            ),
            row=3,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=_weighted_efficiency(
                    efficiency,
                    window_days,
                ),
                mode="lines",
                name=f"{category} efficiency avg",
                line={"color": color, "width": 1.8},
                opacity=0.55,
                showlegend=False,
            ),
            row=3,
            col=1,
        )

    if not plotted:
        raise ValueError("no data to plot")

    ticks = [
        SUBT_PACE_RANGE[1] + 15 * index
        for index in range(5)
    ]
    figure.update_yaxes(
        range=list(SUBT_PACE_RANGE),
        tickvals=ticks,
        ticktext=[format_pace(value) for value in ticks],
        row=1,
        col=1,
    )
    figure.update_yaxes(
        title_text="pace (min/km)",
        row=1,
        col=1,
    )
    figure.update_yaxes(
        title_text="heart rate (bpm)",
        range=list(SUBT_HR_RANGE),
        dtick=10,
        row=2,
        col=1,
    )
    efficiency_range = _bulk_range(
        [
            value
            for point in points
            for value in (
                point.efficiency,
                point.lowest_efficiency,
                point.highest_efficiency,
            )
        ],
        step=0.1,
    )
    figure.update_yaxes(
        title_text="efficiency (m/excess beat, work reps)",
        range=efficiency_range,
        row=3,
        col=1,
    )
    figure.update_xaxes(title_text="date", row=3, col=1)
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=1200,
        margin={"l": 60, "r": 30, "t": 70, "b": 110},
        legend=_legend_below(),
        hovermode="x unified",
    )
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=3300,
    )
