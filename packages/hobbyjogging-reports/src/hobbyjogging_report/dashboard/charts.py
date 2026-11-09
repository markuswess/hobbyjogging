"""Plotly figures for the static dashboard."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots

from ..model import RecoveryPoint, TimePoint
from ..series import alpha_from_time_constant, ewma

PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
}

PLOTLY_LAYOUT = {
    "template": "plotly_white",
    "height": 320,
    "margin": {"l": 50, "r": 20, "t": 30, "b": 40},
    "legend": {"orientation": "h", "y": 1.12, "x": 0},
}


def plotly_js() -> str:
    """Return the plotly library source to bundle with the site."""
    return get_plotlyjs()


def _to_html(figure: go.Figure) -> str:
    return figure.to_html(
        full_html=False,
        include_plotlyjs=False,
        config=PLOTLY_CONFIG,
    )


def running_volume_chart(
    actual_bars: list[tuple[date, float, float, float]],
    planned_bars: list[tuple[date, float, float, float]],
    points: list[TimePoint],
    start: date,
    end: date,
    today: date,
) -> str:
    """Daily running hours stacked by zone group with 182/42-day EWMAs."""
    figure = go.Figure()

    groups = (
        ("Z1+2", 1, "#9ecae1", "rgba(158, 202, 225, 0.45)", "#6baed6"),
        ("Z3+4", 2, "#e6550d", "rgba(230, 85, 13, 0.45)", "#a63603"),
        ("Unzoned", 3, "#d9d9d9", "rgba(217, 217, 217, 0.6)", "#969696"),
    )

    for label, value_key, color, _planned_color, _edge in groups:
        values = [row[value_key] / 3600 for row in actual_bars]

        if label == "Unzoned" and not any(values):
            continue

        figure.add_bar(
            x=[row[0].isoformat() for row in actual_bars],
            y=values,
            name=label,
            marker_color=color,
        )

    if planned_bars:
        for label, value_key, _color, planned_color, edge in groups:
            planned_values = [row[value_key] / 3600 for row in planned_bars]

            if label == "Unzoned" and not any(planned_values):
                continue

            figure.add_bar(
                x=[row[0].isoformat() for row in planned_bars],
                y=planned_values,
                name=f"planned {label}",
                marker={
                    "color": planned_color,
                    "line": {"color": edge, "width": 1},
                    "pattern": {"shape": "/", "fgcolor": edge},
                },
            )

    actual = [point for point in points if not point.projected]
    projected = [point for point in points if point.projected]

    for attribute, label, color in (
        ("base", "182-day EWMA", "#08519c"),
        ("fitness", "42-day EWMA", "#a63603"),
    ):
        if actual:
            figure.add_trace(
                go.Scatter(
                    x=[point.date.isoformat() for point in actual],
                    y=[getattr(point, attribute) / 3600 for point in actual],
                    mode="lines",
                    name=label,
                    line={"color": color, "width": 2},
                )
            )

        if projected:
            bridge = actual[-1:] + projected
            figure.add_trace(
                go.Scatter(
                    x=[point.date.isoformat() for point in bridge],
                    y=[getattr(point, attribute) / 3600 for point in bridge],
                    mode="lines",
                    name=label,
                    line={"color": color, "width": 2, "dash": "dash"},
                    showlegend=False,
                )
            )

    if projected:
        figure.add_trace(
            go.Scatter(
                x=[],
                y=[],
                mode="lines",
                name="projected",
                line={"color": "#7f7f7f", "width": 1, "dash": "dash"},
            )
        )

    figure.add_vline(
        x=today.isoformat(),
        line_width=1,
        line_dash="dot",
        line_color="#7f7f7f",
        annotation_text="today",
        annotation_position="top",
    )

    figure.update_layout(
        template="plotly_white",
        height=450,
        margin={"l": 50, "r": 20, "t": 40, "b": 40},
        barmode="stack",
        bargap=0.1,
        hovermode="x unified",
        yaxis_title="hours",
        xaxis={"range": [start.isoformat(), end.isoformat()]},
        legend={"orientation": "h", "y": 1.12, "x": 0},
    )

    return _to_html(figure)


def load_chart(series: list[tuple[date, float]]) -> str:
    """Daily training load with a 7-day EWMA line."""
    days = [day.isoformat() for day, _ in series]
    loads = [value for _, value in series]
    average = ewma(loads, alpha_from_time_constant(7))

    figure = go.Figure()
    figure.add_bar(
        x=days,
        y=loads,
        name="daily load",
        marker_color="#cbd2d9",
    )
    figure.add_trace(
        go.Scatter(
            x=days,
            y=average,
            name="7-day avg",
            mode="lines",
            line={"color": "#d1495b", "width": 2},
        )
    )
    figure.update_layout(
        **PLOTLY_LAYOUT,
        yaxis_title="training load",
    )

    return _to_html(figure)


def recovery_chart(points: list[RecoveryPoint]) -> str:
    """HRV, resting HR, and sleep with their 7-day averages."""
    dates = [point.date.isoformat() for point in points]
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("HRV (ms)", "Resting HR (bpm)", "Sleep (hours)"),
    )

    metrics = (
        (
            "hrv",
            "hrv_avg",
            1.0,
            "HRV",
            "#4c78a8",
        ),
        (
            "resting_hr",
            "resting_hr_avg",
            1.0,
            "Resting HR",
            "#d1495b",
        ),
        (
            "sleep_s",
            "sleep_avg",
            1 / 3600,
            "Sleep",
            "#8064a2",
        ),
    )

    for row, (value_key, average_key, scale, _name, color) in enumerate(
        metrics,
        start=1,
    ):
        values = [
            getattr(point, value_key) * scale
            if getattr(point, value_key) is not None
            else None
            for point in points
        ]
        averages = [
            getattr(point, average_key) * scale
            if getattr(point, average_key) is not None
            else None
            for point in points
        ]
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                mode="markers",
                marker={"color": color, "size": 5, "opacity": 0.45},
                name="daily",
                showlegend=False,
            ),
            row=row,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=averages,
                mode="lines",
                line={"color": color, "width": 2},
                name="7-day avg",
                showlegend=False,
            ),
            row=row,
            col=1,
        )

    figure.update_layout(
        template="plotly_white",
        height=700,
        margin={"l": 55, "r": 20, "t": 40, "b": 40},
    )

    return _to_html(figure)
