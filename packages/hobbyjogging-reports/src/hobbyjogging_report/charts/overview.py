"""The main training overview chart."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go

from ..model import Vo2maxPoint
from ..style import (
    EASY_COLOR,
    EASY_EDGE,
    EASY_PLANNED_COLOR,
    HARD_COLOR,
    HARD_EDGE,
    HARD_LINE_COLORS,
    HARD_PLANNED_COLOR,
    LINE_STYLES,
    LINE_WIDTHS,
    MINUTES_Y_MIN,
    MINUTES_Y_STEP,
    PLANNED_PATTERN,
    PROJECTED_OPACITY,
    TOTAL_LINE_COLORS,
    UNZONED_COLOR,
    UNZONED_EDGE,
    UNZONED_PLANNED_COLOR,
)
from ..zone_groups import ZoneGroupSeries

from .common import (
    _axis_ceiling,
    _clipped_markers,
    _crosshair,
    _legend_below,
    _outline,
    _render,
)


def plot_overview(
    actual_bars: list[tuple[date, float, float, float]],
    planned_bars: list[tuple[date, float, float, float]],
    zone_series: ZoneGroupSeries,
    output: str,
    start: date,
    end: date,
    today: date,
    vo2max_points: list[Vo2maxPoint] | None = None,
    title: str = "Training overview",
    as_html: bool = False,
) -> str:
    """Daily running minutes by intensity group with grouped EWMAs."""
    figure = go.Figure()
    groups = (
        ("hard", 2, HARD_COLOR, HARD_PLANNED_COLOR, HARD_EDGE),
        ("easy", 1, EASY_COLOR, EASY_PLANNED_COLOR, EASY_EDGE),
        ("unzoned", 3, UNZONED_COLOR, UNZONED_PLANNED_COLOR, UNZONED_EDGE),
    )

    for label, value_key, color, _planned_color, _edge in groups:
        values = [row[value_key] / 60 for row in actual_bars]

        if label == "unzoned" and not any(values):
            continue

        figure.add_bar(
            x=[row[0].isoformat() for row in actual_bars],
            y=values,
            name=label,
            marker_color=color,
        )

    if planned_bars:
        for label, value_key, _color, planned_color, edge in groups:
            planned_values = [row[value_key] / 60 for row in planned_bars]

            if label == "unzoned" and not any(planned_values):
                continue

            figure.add_bar(
                x=[row[0].isoformat() for row in planned_bars],
                y=planned_values,
                name=f"planned {label}",
                marker={
                    "color": planned_color,
                    "line": {"color": edge, "width": 1},
                    "pattern": {
                        "shape": PLANNED_PATTERN,
                        "fgcolor": edge,
                    },
                },
            )

    actual = [point for point in zone_series.points if not point.projected]
    projected = [point for point in zone_series.points if point.projected]

    series = []

    # Window-major, shortest first: every 7-day line, then 42, then 182, so
    # the smoothest lines end up on top.
    for window in (7, 42, 182):
        for family, colors in (
            ("hard", HARD_LINE_COLORS),
            ("total", TOTAL_LINE_COLORS),
        ):
            attribute = f"{family}_{window}"
            style = {
                "color": colors[window],
                "width": LINE_WIDTHS[window],
                "dash": LINE_STYLES[window],
            }

            if actual:
                series.append((
                    [point.date.isoformat() for point in actual],
                    [getattr(point, attribute) / 60 for point in actual],
                    f"{family} {window}d",
                    style,
                    1.0,
                    True,
                ))

            if projected:
                bridge = actual[-1:] + projected
                series.append((
                    [point.date.isoformat() for point in bridge],
                    [
                        getattr(point, attribute) / 60
                        for point in bridge
                    ],
                    f"{family} {window}d",
                    style,
                    PROJECTED_OPACITY,
                    False,
                ))

    # Bars are already drawn; all outlines go down before any line so a
    # later halo cannot cut an earlier line at a crossing.
    for x, y, _name, style, _opacity, _show in series:
        _outline(figure, x, y, style["width"])

    for x, y, name, style, opacity, showlegend in series:
        figure.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=name,
                line=style,
                opacity=opacity,
                showlegend=showlegend,
            )
        )

    y_max = max(
        _axis_ceiling(
            [sum(row[1:]) / 60 for row in (*actual_bars, *planned_bars)],
            step=MINUTES_Y_STEP,
            floor=MINUTES_Y_MIN,
            tail=0.10,
        ),
        _axis_ceiling(
            [
                getattr(point, attribute) / 60
                for point in zone_series.points
                for attribute in ("total_42", "total_182")
            ],
            step=MINUTES_Y_STEP,
            floor=MINUTES_Y_MIN,
            tail=0.10,
        ),
    )

    _clipped_markers(
        figure,
        [
            (row[0].isoformat(), sum(row[1:]) / 60)
            for row in (*actual_bars, *planned_bars)
        ],
        y_max,
        "min",
        number=".0f",
    )

    vo2max = [
        point
        for point in vo2max_points or []
        if start <= point.date <= end
        and (point.avg_42 is not None or point.avg_182 is not None)
    ]

    if vo2max:
        for label, attribute, color, dash in (
            ("VO2max 42d", "avg_42", "black", "solid"),
            ("VO2max 182d", "avg_182", "#7f7f7f", "dashdot"),
        ):
            figure.add_trace(
                go.Scatter(
                    x=[point.date.isoformat() for point in vo2max],
                    y=[getattr(point, attribute) for point in vo2max],
                    mode="lines",
                    name=label,
                    yaxis="y2",
                    line={"color": color, "width": 2, "dash": dash},
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
    layout = {
        "template": "plotly_white",
        "title": title,
        "height": 700,
        "margin": {"l": 50, "r": 20, "t": 95, "b": 110},
        "barmode": "stack",
        "bargap": 0.1,
        "hovermode": "x unified",
        "yaxis": {
            "title": "minutes",
            "range": [0, y_max],
            "dtick": MINUTES_Y_STEP,
            "tickfont": {"size": 10},
        },
        "xaxis": {
            "range": [start.isoformat(), end.isoformat()],
            "tickfont": {"size": 10},
        },
        "legend": _legend_below(font_size=10, columns=7),
    }

    if vo2max:
        values = [
            value
            for point in vo2max
            for value in (point.avg_42, point.avg_182)
            if value is not None
        ]
        low = min(values)
        high = max(values)
        pad = max(0.25, (high - low) * 0.15)
        span = high - low + 2 * pad
        layout["yaxis2"] = {
            "title": "VO2max",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "range": [low - pad, high + pad],
            "dtick": 0.5 if span <= 4 else 1,
            "tickfont": {"size": 10},
        }

    figure.update_layout(**layout)
    _crosshair(figure, second_y=True)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=900,
    )
