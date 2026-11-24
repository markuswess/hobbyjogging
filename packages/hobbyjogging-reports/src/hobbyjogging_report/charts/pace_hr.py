"""Pace-vs-heart-rate scatters."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go

from ..analysis import (
    EFFICIENCY_UNIT,
    STEADY_BAND_LABEL,
    pace_hr_efficiency_lines,
    pace_hr_trends,
    pace_hr_year_efficiency,
)
from ..defaults import COMPARE_VISIBLE_YEARS, PACE_HR_SPEED_RANGE
from ..format import format_pace, format_weather
from ..model import PaceHrPoint

from .common import (
    PACE_HR_CATEGORY_ORDER,
    PACE_HR_SYMBOLS,
    PACE_HR_SYMBOL_TEXT,
    _crosshair,
    _darker,
    _legend_below,
    _outline,
    _render,
    _require_data,
    compare_color,
)


def _pace_hr_category(category: str) -> str:
    return category if category in PACE_HR_SYMBOLS else "other"


def _pace_hr_label(category: str) -> str:
    return {
        "longrun": "long run",
        "race-support": "race support",
    }.get(category, category.replace("_", " ").title())


def _style_pace_hr_axes(figure) -> None:
    """Shared linear-speed axis with pace ticks and HR bounds."""
    tick_speeds = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    figure.update_xaxes(
        title_text="pace (min/km)",
        range=list(PACE_HR_SPEED_RANGE),
        tickvals=tick_speeds,
        ticktext=[format_pace(1000 / speed) for speed in tick_speeds],
    )
    figure.update_yaxes(
        title_text="avg HR (bpm)",
        range=[90, 190],
        dtick=10,
    )


def _weather_hint(weather) -> str:
    text = format_weather(weather)

    return f"<br>{text}" if text else ""


def _weather_summary(points: list[PaceHrPoint]) -> str | None:
    """One chart note: how many runs have weather and the range it spans."""
    temps = sorted(
        point.weather.temp_c
        for point in points
        if point.weather is not None and point.weather.temp_c is not None
    )

    if not temps:
        return None

    median = temps[len(temps) // 2]

    return (
        f"weather on {len(temps)} of {len(points)} runs "
        f"(median {median:.0f} °C, {temps[0]:.0f} to {temps[-1]:.0f} °C)"
    )


def plot_pace_hr(
    points: list[PaceHrPoint],
    output: str,
    title: str = "Pace vs heart rate",
    as_html: bool = False,
) -> str:
    """One point per run: average speed against average heart rate."""
    _require_data(points)
    figure = go.Figure()
    years = sorted({point.date.year for point in points})
    ordinals = [point.date.toordinal() for point in points]
    categories = {
        _pace_hr_category(point.category)
        for point in points
    }
    ordered = [
        category for category in PACE_HR_CATEGORY_ORDER
        if category in categories
    ]

    for index, category in enumerate(ordered):
        chunk = [
            point for point in points
            if _pace_hr_category(point.category) == category
        ]
        figure.add_trace(
            go.Scatter(
                x=[point.speed_m_s for point in chunk],
                y=[point.avg_hr for point in chunk],
                mode="markers",
                name=_pace_hr_label(category),
                marker={
                    "color": [point.date.toordinal() for point in chunk],
                    "cmin": min(ordinals),
                    "cmax": max(ordinals),
                    "colorscale": [
                        [0.0, "#1f77b4"],
                        [1.0, "#d62728"],
                    ],
                    "size": 6,
                    "opacity": 0.75,
                    "symbol": PACE_HR_SYMBOLS[category],
                    "line": {
                        "color": "#222222",
                        "width": [
                            1.2 if point.steady else 0
                            for point in chunk
                        ],
                    },
                    "showscale": index == 0,
                    "colorbar": {
                        "title": {"text": "year"},
                        "thickness": 12,
                        "tickvals": [
                            date(year, 1, 1).toordinal()
                            for year in years
                        ],
                        "ticktext": [str(year) for year in years],
                    },
                },
                text=[
                    (
                        f"{point.date} {point.name}".strip()
                        + f"<br>{_pace_hr_label(category)}"
                        + f"<br>{format_pace(point.pace_s_per_km)}/km"
                        + f", {point.avg_hr:.0f} bpm"
                        + _weather_hint(point.weather)
                    )
                    for point in chunk
                ],
                hoverinfo="text",
            )
        )

    trends = pace_hr_trends(points)
    colors = ("#1f77b4", "#d62728")
    notes = []
    efficiency_lines = pace_hr_efficiency_lines(points)

    # All halos go down before the trend and efficiency lines, so none of
    # them can cut an earlier line at a crossing.
    for line in efficiency_lines:
        _outline(
            figure,
            list(PACE_HR_SPEED_RANGE),
            [line.at(speed) for speed in PACE_HR_SPEED_RANGE],
            1.6,
        )

    for trend, color in zip(trends, colors):
        figure.add_trace(
            go.Scatter(
                x=[trend.speed_low, trend.speed_high],
                y=[
                    trend.at(trend.speed_low),
                    trend.at(trend.speed_high),
                ],
                mode="lines",
                name=f"{trend.label} trend",
                line={"color": color, "width": 2},
                hoverinfo="skip",
            )
        )
        notes.append(
            f"{trend.label}: HR = {trend.intercept:.2f} "
            f"+ {trend.slope:.2f}\u00b7v, r = {trend.correlation:.2f}"
        )

    color_for = {
        "first half": colors[0],
        "second half": colors[1],
    }

    for line in efficiency_lines:
        figure.add_trace(
            go.Scatter(
                x=list(PACE_HR_SPEED_RANGE),
                y=[line.at(speed) for speed in PACE_HR_SPEED_RANGE],
                mode="lines",
                name=f"{line.label} efficiency",
                line={
                    "color": color_for[line.label],
                    "width": 1.6,
                    "dash": "longdash",
                },
                hoverinfo="skip",
            )
        )
        notes.append(
            f"{line.label} efficiency (steady {STEADY_BAND_LABEL}): "
            f"E = {line.efficiency:.2f} {EFFICIENCY_UNIT}, "
            f"RHR {line.resting_hr:.2f} bpm"
        )

    if efficiency_lines:
        notes.append(
            f"dashed efficiency lines use steady {STEADY_BAND_LABEL} "
            "non-quality runs; outlined points are their inputs — all runs "
            "are shown"
        )

    weather_note = _weather_summary(points)

    if weather_note:
        notes.append(weather_note)

    if notes:
        figure.add_annotation(
            text="<br>".join(notes),
            xref="paper",
            yref="paper",
            x=0.01,
            y=0.99,
            xanchor="left",
            yanchor="top",
            align="left",
            showarrow=False,
            font={"size": 11},
        )

    _style_pace_hr_axes(figure)
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=900,
        margin={"l": 60, "r": 30, "t": 70, "b": 110},
        legend=_legend_below(),
        hovermode="closest",
    )
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=1500,
    )


def plot_compare_pace_hr(
    points: list[PaceHrPoint],
    output: str,
    title: str = "Pace vs heart rate by year",
    as_html: bool = False,
) -> str:
    """One point per run, coloured by calendar year for the compare view."""
    _require_data(points)
    figure = go.Figure()
    years = sorted({point.date.year for point in points})

    visible_from = max(years) - COMPARE_VISIBLE_YEARS + 1

    for year in years:
        chunk = [point for point in points if point.date.year == year]
        visible = True if year >= visible_from else "legendonly"

        figure.add_trace(
            go.Scatter(
                x=[point.speed_m_s for point in chunk],
                y=[point.avg_hr for point in chunk],
                mode="markers",
                name=str(year),
                visible=visible,
                marker={
                    "color": compare_color(year),
                    "size": 6,
                    "opacity": 0.72,
                    "symbol": [
                        PACE_HR_SYMBOLS[
                            _pace_hr_category(point.category)
                        ]
                        for point in chunk
                    ],
                },
                text=[
                    (
                        f"{point.date} {point.name}".strip()
                        + f"<br>{format_pace(point.pace_s_per_km)}/km"
                        + f", {point.avg_hr:.0f} bpm"
                        + _weather_hint(point.weather)
                    )
                    for point in chunk
                ],
                hoverinfo="text",
            )
        )

    efficiency_lines = pace_hr_year_efficiency(points)

    for line in efficiency_lines:
        _outline(
            figure,
            list(PACE_HR_SPEED_RANGE),
            [line.at(speed) for speed in PACE_HR_SPEED_RANGE],
            1.8,
        )

    for line in efficiency_lines:
        hover = (
            f"{line.label} efficiency: E = {line.efficiency:.2f} "
            f"{EFFICIENCY_UNIT}, RHR {line.resting_hr:.0f} bpm "
            f"(n={line.points} steady runs)"
        )
        figure.add_trace(
            go.Scatter(
                x=list(PACE_HR_SPEED_RANGE),
                y=[line.at(speed) for speed in PACE_HR_SPEED_RANGE],
                mode="lines",
                name=f"{line.label} efficiency",
                line={
                    "color": _darker(compare_color(int(line.label))),
                    "width": 1.8,
                    "dash": "longdash",
                },
                text=[hover, hover],
                hoverinfo="text",
                showlegend=False,
            )
        )

    efficiency_note = ""

    if efficiency_lines:
        efficiency_note = (
            "dashed: steady efficiency per year ("
            + ", ".join(
                f"{line.label} {line.efficiency:.2f}"
                for line in efficiency_lines
            )
            + ")"
        )

    _style_pace_hr_axes(figure)
    symbols = [
        category
        for category in PACE_HR_CATEGORY_ORDER
        if any(
            _pace_hr_category(point.category) == category
            for point in points
        )
    ]
    if symbols:
        figure.add_annotation(
            text=(
                "   ".join(
                    f"{PACE_HR_SYMBOL_TEXT[category]} "
                    f"{_pace_hr_label(category)}"
                    for category in symbols
                )
                + "<br>all runs; colour = calendar year"
                + (
                    f"<br>{weather_line}"
                    if (weather_line := _weather_summary(points))
                    else ""
                )
                + (f"<br>{efficiency_note}" if efficiency_note else "")
            ),
            xref="paper",
            yref="paper",
            x=0.01,
            y=0.01,
            xanchor="left",
            yanchor="bottom",
            showarrow=False,
            font={"size": 10},
        )

    figure.update_layout(
        template="plotly_white",
        title=title,
        height=900,
        margin={"l": 60, "r": 30, "t": 70, "b": 110},
        legend=_legend_below(),
        hovermode="closest",
    )
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=1500,
    )
