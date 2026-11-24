"""VO2max methods chart."""

from __future__ import annotations

import plotly.graph_objects as go

from ..model import Vo2maxMethods
from ..style import LINE_STYLES, LINE_WIDTHS

from .common import (
    VO2MAX_DEVICE_COLORS,
    _base_layout,
    _crosshair,
    _legend_below,
    _render,
    _require_data,
)


def plot_vo2max_methods(
    methods: Vo2maxMethods,
    output: str,
    title: str = "VO2max methods",
    as_html: bool = False,
) -> str:
    """The effective estimate against Garmin and Runalyze trends.

    Every method is drawn as 42-day solid and 182-day dash-dot EWMAs. Garmin
    keeps its raw readings as one marker series per recording device, and the
    latest device also carries the two EWMA lines.
    """
    _require_data(
        methods.all_runs,
        methods.garmin,
        methods.runalyze,
        methods.races,
    )
    figure = go.Figure()
    estimates = (
        ("Estimate", methods.all_runs, "#2ca02c", "#00441b"),
        ("Runalyze", methods.runalyze, "#8c8c8c", "#4d4d4d"),
    )

    for label, points, short_color, long_color in estimates:
        if not points:
            continue

        figure.add_trace(
            go.Scatter(
                x=[point.date for point in points],
                y=[point.avg_42 for point in points],
                mode="lines",
                name=f"{label} 42d",
                line={"color": short_color, "width": LINE_WIDTHS[42]},
                connectgaps=False,
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[point.date for point in points],
                y=[point.avg_182 for point in points],
                mode="lines",
                name=f"{label} 182d",
                line={
                    "color": long_color,
                    "width": LINE_WIDTHS[182],
                    "dash": LINE_STYLES[182],
                },
                connectgaps=False,
            )
        )

    colors = {
        device.device_id: VO2MAX_DEVICE_COLORS[
            index % len(VO2MAX_DEVICE_COLORS)
        ]
        for index, device in enumerate(methods.garmin)
    }

    for device in methods.garmin:
        figure.add_trace(
            go.Scatter(
                x=[measurement.date for measurement in device.measurements],
                y=[measurement.value for measurement in device.measurements],
                mode="markers",
                name=device.label,
                marker={
                    "color": colors[device.device_id],
                    "size": 4,
                    "opacity": 0.55,
                },
            )
        )

    if methods.garmin:
        latest = max(
            methods.garmin,
            key=lambda device: device.measurements[-1].date,
        )
        color = colors[latest.device_id]

        for window, values, dash in (
            (42, latest.avg_42, "dot"),
            (182, latest.avg_182, LINE_STYLES[182]),
        ):
            figure.add_trace(
                go.Scatter(
                    x=[day for day, value in values if value is not None],
                    y=[value for _, value in values if value is not None],
                    mode="lines",
                    name=f"{latest.label} {window}d",
                    line={
                        "color": color,
                        "width": LINE_WIDTHS[window],
                        "dash": dash,
                    },
                )
            )

    if methods.races:
        figure.add_trace(
            go.Scatter(
                x=[day for day, _ in methods.races],
                y=[value for _, value in methods.races],
                mode="markers",
                name="Race VDOT",
                marker={"color": "#d62728", "size": 10, "symbol": "star"},
            )
        )

    _base_layout(
        figure,
        title=title,
        xlabel="date",
        ylabel="VO2max (mL/kg/min)",
    )
    figure.update_layout(
        height=850,
        legend=_legend_below(font_size=10, columns=4),
    )
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=1000,
    )
