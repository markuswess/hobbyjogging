"""Recovery panels."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from hobbyjogging_core.model import TrainingPeriod

from ..analysis import recovery_bands
from ..model import RecoveryPoint
from ..style import (
    RECOVERY_BAND_COLORS,
    RECOVERY_BAND_MARKERS,
    ILLNESS_BAND_COLOR,
)

from .common import (
    _crosshair,
    _legend_below,
    _period_bands,
    _render,
    _require_data,
)


def _recovery_axis_bounds(values: list[float]) -> tuple[float, float]:
    """Padded y-range for one recovery panel."""
    low = min(values)
    high = max(values)
    pad = max((high - low) * 0.08, 1.0)

    return low - pad, high + pad


def plot_recovery(
    points: list[RecoveryPoint],
    output: str,
    planned_dates: list[date] | None = None,
    window_days: int = 7,
    title: str = "Recovery trends",
    as_html: bool = False,
    baseline_points: list[RecoveryPoint] | None = None,
    periods: list[TrainingPeriod] | None = None,
) -> str:
    """HRV, resting HR, and sleep with averages and readiness bands.

    ``baseline_points`` may include a year of history before the displayed
    range; the bands are computed at the end of that history, while only
    ``points`` are drawn.
    """
    _require_data(points)
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("HRV", "Resting HR", "Sleep"),
    )
    metrics = (
        ("hrv", "hrv_avg", 1.0, "ms", "#1f77b4"),
        ("resting_hr", "resting_hr_avg", 1.0, "bpm", "#d62728"),
        ("sleep_s", "sleep_avg", 1 / 3600, "hours", "#9467bd"),
    )
    bands = recovery_bands(baseline_points or points)
    band_sets = (bands.hrv, bands.resting_hr, bands.sleep_s)
    range_start = min(point.date for point in points)
    range_end = max(point.date for point in points)

    if planned_dates:
        range_start = min(range_start, min(planned_dates))
        range_end = max(range_end, max(planned_dates))

    for row, (raw_attr, average_attr, scale, unit, color) in enumerate(
        metrics,
        start=1,
    ):
        raw = [
            (point.date, getattr(point, raw_attr) * scale)
            for point in points
            if getattr(point, raw_attr) is not None
        ]
        average = [
            (point.date, getattr(point, average_attr) * scale)
            for point in points
            if getattr(point, average_attr) is not None
        ]
        bounds = _recovery_axis_bounds(
            [value for _, value in raw] + [value for _, value in average]
            or [0.0]
        )

        _period_bands(
            figure,
            periods,
            kind="illness",
            color=ILLNESS_BAND_COLOR,
            start=range_start,
            end=range_end,
            bottom=bounds[0],
            top=bounds[1],
            row=row,
            col=1,
        )

        if raw:
            figure.add_trace(
                go.Scatter(
                    x=[day for day, _ in raw],
                    y=[value for _, value in raw],
                    mode="markers",
                    marker={"color": color, "size": 4, "opacity": 0.45},
                    name="daily",
                    showlegend=False,
                    cliponaxis=False,
                ),
                row=row,
                col=1,
            )

        if average:
            figure.add_trace(
                go.Scatter(
                    x=[day for day, _ in average],
                    y=[value for _, value in average],
                    mode="lines",
                    line={"color": color, "width": 2},
                    name=f"{window_days}-day avg",
                    showlegend=False,
                ),
                row=row,
                col=1,
            )

        # Shapes only attach to populated subplot axes, so draw the bands
        # after the panel's traces.
        for band in band_sets[row - 1]:
            low = bounds[0] if band.low is None else band.low * scale
            high = bounds[1] if band.high is None else band.high * scale

            if low >= high:
                continue

            figure.add_hrect(
                y0=low,
                y1=high,
                fillcolor=RECOVERY_BAND_COLORS[band.level],
                line_width=0,
                layer="below",
                row=row,
                col=1,
            )

        label = {
            "hrv": "HRV (ms)",
            "resting_hr": "Resting HR (bpm)",
            "sleep_s": "Sleep (hours)",
        }.get(raw_attr, raw_attr)

        figure.update_yaxes(
            title_text=label,
            range=list(bounds),
            row=row,
            col=1,
        )

    figure.add_annotation(
        text="   ".join(
            f"<span style='color:{color}'>\u25a0 {level}</span>"
            for level, color in RECOVERY_BAND_MARKERS.items()
        ),
        xref="paper",
        yref="paper",
        x=0.995,
        y=1.0,
        xanchor="right",
        yanchor="bottom",
        showarrow=False,
        font={"size": 11},
    )

    if planned_dates:
        for day in planned_dates:
            figure.add_shape(
                type="line",
                xref="x3",
                yref="y3 domain",
                x0=day,
                x1=day,
                y0=0.01,
                y1=0.05,
                line={"color": "black", "width": 2},
            )

    figure.update_xaxes(
        title_text="date",
        range=[range_start, range_end],
        row=3,
        col=1,
    )
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=900,
        margin={"l": 60, "r": 30, "t": 70, "b": 110},
        legend=_legend_below(),
        hovermode="x unified",
    )
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=2700,
    )
