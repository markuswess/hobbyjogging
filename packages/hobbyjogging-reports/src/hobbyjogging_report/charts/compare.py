"""Year and period comparison charts."""

from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go

from ..analysis import STEADY_BAND_LABEL
from ..defaults import COMPARE_VISIBLE_YEARS
from ..model import Vo2maxMeasurement

from .common import (
    _crosshair,
    _legend_below,
    _render,
    _require_data,
    compare_color,
)


def plot_compare_vo2max(
    measurements: list[Vo2maxMeasurement],
    output: str,
    title: str = "Garmin running VO2max by year",
    as_html: bool = False,
) -> str:
    """Raw Garmin running VO2max readings, one marker per activity, by year."""
    _require_data(measurements)
    reference_year = 2001
    reference_start = date(reference_year, 1, 1)
    years = sorted({measurement.date.year for measurement in measurements})
    visible_from = max(years) - (COMPARE_VISIBLE_YEARS - 1)
    figure = go.Figure()

    for year in years:
        chunk = [
            measurement
            for measurement in measurements
            if measurement.date.year == year
        ]
        year_start = date(year, 1, 1)

        figure.add_trace(
            go.Scatter(
                x=[
                    reference_start
                    + timedelta(days=(measurement.date - year_start).days)
                    for measurement in chunk
                ],
                y=[measurement.value for measurement in chunk],
                mode="lines",
                name=str(year),
                visible=(
                    True if year >= visible_from else "legendonly"
                ),
                marker={
                    "color": compare_color(year),
                    "size": 6,
                    "opacity": 0.7,
                },
            )
        )

    figure.update_xaxes(
        title_text="month",
        range=[
            reference_start,
            date(reference_year, 12, 31),
        ],
        dtick="M1",
        tickformat="%b",
    )
    figure.update_yaxes(title_text="Garmin running VO2max")
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=700,
        margin={"l": 60, "r": 30, "t": 70, "b": 100},
        legend=_legend_below(),
        # The rest of the compare tab is x-unified; match it so a year can be
        # read across the same month here too.
        hovermode="x unified",
    )
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=1200,
    )


def plot_compare(
    series: list[tuple[int, list[tuple[date, float]]]],
    output: str,
    *,
    metric: str,
    window: int,
    today: date,
    title: str = "Year comparison",
    as_html: bool = False,
    planned_series: list[tuple[int, list[tuple[date, float]]]] | None = None,
) -> str:
    """One EWMA line per year, plus dashed planned lines when supplied."""
    _require_data(series)
    reference_year = 2001
    reference_start = date(reference_year, 1, 1)
    ylabels = {
        "volume": "km / week",
        "time": "hours / week",
        "load": "running load / day",
        "runs": "runs / day",
        "efficiency": f"m / excess beat (steady {STEADY_BAND_LABEL})",
    }
    scale = 7.0 if metric in ("volume", "time") else 1.0
    planned_series = planned_series or []
    planned_by_year = dict(planned_series)
    all_years = sorted(
        {year for year, _ in series}
        | {year for year, _ in planned_series}
    )
    visible_from = max(all_years) - (COMPARE_VISIBLE_YEARS - 1)
    color_for = {
        year: compare_color(year)
        for year in all_years
    }
    figure = go.Figure()

    def add_line(
        year: int,
        points: list[tuple[date, float]],
        *,
        planned: bool,
    ) -> None:
        year_start = date(year, 1, 1)
        figure.add_trace(
            go.Scatter(
                x=[
                    reference_start
                    + timedelta(days=(day - year_start).days)
                    for day, _ in points
                ],
                y=[value * scale for _, value in points],
                mode="lines",
                name=f"{year} planned" if planned else str(year),
                visible=(
                    True if year >= visible_from else "legendonly"
                ),
                line={
                    "color": color_for[year],
                    "width": 1.5 if planned else 2,
                    "dash": "dash" if planned else "solid",
                },
            )
        )

    for year, points in series:
        add_line(year, points, planned=False)

        planned_points = planned_by_year.pop(year, None)
        if planned_points is not None:
            add_line(year, planned_points, planned=True)

    for year, points in sorted(planned_by_year.items()):
        add_line(year, points, planned=True)

    if any(year == today.year for year, _ in series):
        moment = reference_start + timedelta(
            days=(today - date(today.year, 1, 1)).days
        )
        figure.add_vline(
            x=moment.isoformat(),
            line_width=1,
            line_dash="dot",
            line_color="#7f7f7f",
            annotation_text="today",
            annotation_position="top",
        )

    figure.update_xaxes(
        title_text="month",
        range=[
            reference_start,
            date(reference_year, 12, 31),
        ],
        dtick="M1",
        tickformat="%b",
    )
    figure.update_yaxes(
        title_text=ylabels.get(metric, metric),
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
        height=1500,
    )
