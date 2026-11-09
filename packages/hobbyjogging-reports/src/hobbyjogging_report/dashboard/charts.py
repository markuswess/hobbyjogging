"""Plotly figures for the static dashboard."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

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


def zone_mix_chart(
    actual_zones: list[float],
    planned_zones: list[float],
    *,
    unzoned_s: float = 0.0,
    planned_unzoned_s: float = 0.0,
) -> str:
    """Actual and planned weekly hours per pace zone."""
    categories = [f"Z{index + 1}" for index in range(len(actual_zones))]
    categories.append("Unzoned")

    actual = [seconds / 3600 for seconds in actual_zones]
    actual.append(unzoned_s / 3600)
    planned = [seconds / 3600 for seconds in planned_zones]
    planned.append(planned_unzoned_s / 3600)
    planned += [0.0] * (len(categories) - len(planned))

    figure = go.Figure()
    figure.add_bar(
        x=categories,
        y=actual,
        name="actual",
        marker_color="#4c78a8",
    )
    figure.add_bar(
        x=categories,
        y=planned,
        name="planned (next 7 days)",
        marker_color="#f58518",
    )
    figure.update_layout(
        **PLOTLY_LAYOUT,
        barmode="group",
        yaxis_title="hours",
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
