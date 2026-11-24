"""Race, PB progression and Riegel charts."""

from __future__ import annotations

import math

import plotly.graph_objects as go

from ..analysis import (
    PbProgression,
    RaceResult,
    pace_s_per_km,
    riegel_reference,
    riegel_time,
)
from ..format import fmt_clock, format_pace

from .common import (
    PB_COLORS,
    _crosshair,
    _legend_below,
    _render,
    _require_data,
)


def _pace_ticks(low: float, high: float) -> tuple[list[float], list[str]]:
    """Pace ticks in seconds/km with ``M:SS`` labels."""
    span = max(high - low, 10.0)
    steps = (5, 10, 15, 30, 60, 120)
    step = next(
        (candidate for candidate in steps if span / candidate <= 8),
        steps[-1],
    )
    start = int(low // step) * step
    end = int(math.ceil(high / step)) * step
    values = list(range(start, end + step, step))

    return values, [format_pace(value) for value in values]




def _race_title(result: RaceResult) -> str:
    """The session title plus the official race title when it differs."""
    title = result.activity.name or result.bucket
    official = result.official_name

    if official and official != result.activity.name:
        return f"{title}<br>{official}"

    return title


def plot_pb_progressions(
    progressions: list[PbProgression],
    output: str,
    title: str = "PB progression",
    as_html: bool = False,
) -> str:
    """PB improvements in pace, one connected line per standard bucket."""
    _require_data(progressions)
    pb_paces = [
        pace
        for progression in progressions
        for step in progression.steps
        if (
            pace := pace_s_per_km(
                step.time_s,
                step.distance_m,
            )
        )
        is not None
    ]
    others = [
        (step, pace, progression.bucket)
        for progression in progressions
        for step in progression.others
        if (
            pace := pace_s_per_km(
                step.time_s,
                step.distance_m,
            )
        )
        is not None
    ]
    # The axis follows the PB lines; a slow race above them is marked rather
    # than allowed to flatten the progression.
    pad = max((max(pb_paces) - min(pb_paces)) * 0.05, 3.0)
    top = max(pb_paces) + pad
    tickvals, ticktext = _pace_ticks(min(pb_paces), top)
    visible = [row for row in others if row[1] <= top]
    above = [row for row in others if row[1] > top]
    figure = go.Figure()

    if visible:
        figure.add_trace(
            go.Scatter(
                x=[step.activity.date for step, _pace, _bucket in visible],
                y=[pace for _step, pace, _bucket in visible],
                mode="markers",
                name="non-PB races",
                marker={
                    "symbol": "circle-open",
                    "size": 6,
                    "color": [
                        PB_COLORS[bucket]
                        for _step, _pace, bucket in visible
                    ],
                },
                text=[
                    f"{step.activity.date} {_race_title(step)}"
                    f"<br>{step.distance_m / 1000:.2f} km, "
                    f"{fmt_clock(step.time_s)}"
                    f" · {format_pace(pace)}/km"
                    for step, pace, bucket in visible
                ],
                hoverinfo="text",
            )
        )

    if above:
        figure.add_trace(
            go.Scatter(
                x=[step.activity.date for step, _pace, _bucket in above],
                y=[top * 0.98] * len(above),
                mode="markers",
                name=f"{len(above)} races above the axis",
                marker={
                    "symbol": "triangle-up",
                    "size": 9,
                    "color": [
                        PB_COLORS[bucket]
                        for _step, _pace, bucket in above
                    ],
                },
                hovertext=[
                    f"{step.activity.date} {_race_title(step)}"
                    f"<br>{format_pace(pace)}/km, above the axis"
                    for step, pace, bucket in above
                ],
                hoverinfo="text",
            )
        )

    for progression in progressions:
        steps = progression.steps
        color = PB_COLORS[progression.bucket]
        step_paces = [
            pace_s_per_km(
                step.time_s,
                step.distance_m,
            )
            for step in steps
        ]
        figure.add_trace(
            go.Scatter(
                x=[step.activity.date for step in steps],
                y=step_paces,
                mode="lines+markers",
                name=progression.bucket,
                line={"width": 2, "color": color},
                marker={"size": 7, "color": color},
                text=[
                    (
                        f"{step.activity.date} "
                        f"{_race_title(step)}"
                        f"<br>{step.distance_m / 1000:.2f} km, "
                        f"{fmt_clock(step.time_s)}"
                        f" · {format_pace(pace)}/km"
                    )
                    for step, pace in zip(steps, step_paces)
                ],
                hoverinfo="text",
            )
        )
        last = steps[-1]
        figure.add_annotation(
            x=last.activity.date,
            y=step_paces[-1],
            text=(
                f"{progression.bucket} "
                f"{format_pace(step_paces[-1])}/km"
            ),
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            font={"size": 10, "color": color},
        )

    figure.update_xaxes(title_text="date")
    figure.update_yaxes(
        title_text="pace (min/km)",
        range=[min(pb_paces) - pad, top],
        tickvals=tickvals,
        ticktext=ticktext,
    )
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=700,
        margin={"l": 70, "r": 100, "t": 70, "b": 100},
        legend=_legend_below(),
        hovermode="closest",
    )
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=1200,
    )


def plot_races(
    results: list[RaceResult],
    fit,
    output: str,
    title: str = "Race performance",
    as_html: bool = False,
) -> str:
    """Log-log race distance/time scatter with the Riegel fit."""
    _require_data(results)
    points = [
        result for result in results
        if result.distance_m and result.time_s
    ]
    figure = go.Figure()

    if points:
        years = [point.activity.date.year for point in points]
        figure.add_trace(
            go.Scatter(
                x=[point.distance_m / 1000 for point in points],
                y=[point.time_s / 60 for point in points],
                mode="markers",
                name="races",
                marker={
                    "color": years,
                    "colorscale": [
                        [0.0, "#1f77b4"],
                        [1.0, "#d62728"],
                    ],
                    "size": 8,
                    "opacity": 0.85,
                    "showscale": True,
                    "colorbar": {"title": {"text": "year"}},
                },
                text=[
                    f"{point.activity.date} "
                    f"{_race_title(point)}"
                    f"<br>{point.distance_m / 1000:.2f} km, "
                    f"{fmt_clock(point.time_s)}"
                    for point in points
                ],
                hoverinfo="text",
            )
        )

    if fit is not None and points:
        reference = riegel_reference(results)
        low = min(point.distance_m for point in points)
        high = max(point.distance_m for point in points)

        # One line: the one the equivalent-time table uses, anchored on the
        # reference race rather than a free fit that can miss every point.
        if reference is not None:
            race = reference.activity
            figure.add_trace(
                go.Scatter(
                    x=[low / 1000, high / 1000],
                    y=[
                        riegel_time(reference, fit, low) / 60,
                        riegel_time(reference, fit, high) / 60,
                    ],
                    mode="lines",
                    name=f"Riegel from {race.date}",
                    line={"color": "#111111", "width": 2, "dash": "dash"},
                    hoverinfo="skip",
                )
            )
            figure.add_trace(
                go.Scatter(
                    x=[reference.distance_m / 1000],
                    y=[reference.time_s / 60],
                    mode="markers",
                    name="reference race",
                    marker={
                        "symbol": "circle-open",
                        "size": 17,
                        "line": {"color": "#111111", "width": 2},
                    },
                    text=[
                        f"{race.date} {_race_title(reference)}"
                        f"<br>{reference.distance_m / 1000:.2f} km, "
                        f"{fmt_clock(reference.time_s)}"
                    ],
                    hoverinfo="text",
                )
            )
            figure.add_annotation(
                text=(
                    f"time ∝ distance^{fit.exponent:.2f} · n={fit.points}"
                    f"<br>through the {reference.bucket} on {race.date}"
                ),
                xref="paper",
                yref="paper",
                x=0.01,
                y=0.99,
                xanchor="left",
                yanchor="top",
                showarrow=False,
                font={"size": 11},
            )

    figure.update_xaxes(title_text="distance (km)", type="log")
    figure.update_yaxes(title_text="time (min)", type="log")
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
        height=1100,
    )
