"""Plotly chart builders shared by the CLI and the dashboard."""

from __future__ import annotations

import warnings
from datetime import date, timedelta

import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings(
    "ignore",
    message=r"(?s).*Kaleido versions less than 1\.0\.0.*",
    category=DeprecationWarning,
)

from .analysis import SUBT_CATEGORIES
from .format import format_pace
from .model import (
    AverageWindows,
    DistancePoint,
    LoadPoint,
    RecoveryPoint,
    SubtPoint,
    TimePoint,
    TimeZoneWeek,
    Vo2maxPoint,
    ZoneAveragePoint,
)
from .series import sma
from .style import (
    EASY_COLOR,
    EASY_EDGE,
    EASY_PLANNED_COLOR,
    HARD_COLOR,
    HARD_EDGE,
    HARD_LINE_COLORS,
    HARD_PLANNED_COLOR,
    LINE_STYLES,
    LINE_WIDTHS,
    PLANNED_PATTERN,
    PROJECTED_OPACITY,
    TOTAL_LINE_COLORS,
    UNZONED_COLOR,
    UNZONED_EDGE,
    UNZONED_PLANNED_COLOR,
)
from .zone_groups import ZoneGroupSeries

PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
}

AVERAGE_COLORS = {
    "base": "#1f77b4",
    "fitness": "#ff7f0e",
    "fatigue": "#d62728",
}

ZONE_COLORS = (
    "#e5f5e0",
    "#c7e9c0",
    "#a1d99b",
    "#74c476",
    "#31a354",
)
ZONE_LINE_COLORS = (
    "#74c476",
    "#41ab5d",
    "#238b45",
    "#006d2c",
    "#00441b",
)
SUBT_COLORS = {
    "short": "#1f77b4",
    "medium": "#ff7f0e",
    "long": "#2ca02c",
    "lt1": "#9467bd",
}
CHART_CATEGORIES = (*SUBT_CATEGORIES, "lt1")
WEEK_MS = 7 * 24 * 60 * 60 * 1000


def _require_data(*series) -> None:
    if not any(series):
        raise ValueError("no data to plot")


def _render(
    figure: go.Figure,
    output: str,
    *,
    as_html: bool,
    width: int,
    height: int,
) -> str:
    figure.update_xaxes(automargin=True)
    figure.update_yaxes(automargin=True)

    if as_html:
        return figure.to_html(
            full_html=False,
            include_plotlyjs=False,
            config=PLOTLY_CONFIG,
        )

    figure.write_image(output, width=width, height=height)
    return output


def _add(figure, trace, *, row: int | None = None, col: int | None = None):
    if row is None:
        figure.add_trace(trace)
    else:
        figure.add_trace(trace, row=row, col=col)


def _base_layout(figure, *, title: str, xlabel: str, ylabel: str):
    figure.update_layout(
        template="plotly_white",
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        height=800,
        margin={"l": 60, "r": 30, "t": 60, "b": 60},
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="x unified",
    )


def _plot_average_lines(
    figure,
    points,
    windows: AverageWindows,
    *,
    scale: float = 1.0,
    label,
    row: int | None = None,
    col: int | None = None,
):
    actual = [point for point in points if not point.projected]
    projected = [point for point in points if point.projected]

    for attribute in ("base", "fitness", "fatigue"):
        if actual:
            _add(
                figure,
                go.Scatter(
                    x=[point.date for point in actual],
                    y=[getattr(point, attribute) * scale for point in actual],
                    mode="lines",
                    name=label(attribute, getattr(windows, attribute)),
                    line={"color": AVERAGE_COLORS[attribute], "width": 2},
                ),
                row=row,
                col=col,
            )

        if projected:
            bridge = actual[-1:] + projected
            _add(
                figure,
                go.Scatter(
                    x=[point.date for point in bridge],
                    y=[
                        getattr(point, attribute) * scale
                        for point in bridge
                    ],
                    mode="lines",
                    line={
                        "color": AVERAGE_COLORS[attribute],
                        "width": 2,
                        "dash": "dash",
                    },
                    showlegend=False,
                ),
                row=row,
                col=col,
            )

    if projected:
        _add(
            figure,
            go.Scatter(
                x=[],
                y=[],
                mode="lines",
                name="avg projection",
                line={
                    "color": AVERAGE_COLORS["base"],
                    "width": 2,
                    "dash": "dash",
                },
            ),
            row=row,
            col=col,
        )


def _planned_total_bars(figure, values, *, label: str = "planned"):
    figure.add_bar(
        x=[day for day, _ in values],
        y=[value for _, value in values],
        name=label,
        marker={
            "color": "rgba(0, 0, 0, 0)",
            "line": {"color": "black", "width": 1.2},
        },
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
    as_html: bool = False,
) -> str:
    """Weekly running volume bars with distance-average lines."""
    _require_data(data, distance_points)
    windows = windows or AverageWindows()
    figure = go.Figure()
    weeks = [week for week, _ in data]

    if data:
        figure.add_bar(
            x=weeks,
            y=[value for _, value in data],
            name="weekly km",
            width=WEEK_MS,
            marker_color="lightgrey",
        )

    if planned_distance:
        xs = []
        ys = []

        for week, value in planned_distance:
            xs.extend([week, week + timedelta(days=7), None])
            ys.extend([value, value, None])

        figure.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                name="planned km",
                line={"color": "black", "width": 1.5, "dash": "dash"},
            )
        )

    if distance_points:
        _plot_average_lines(
            figure,
            distance_points,
            windows,
            scale=distance_scale,
            label=lambda attribute, days: f"{days}d avg (weekly)",
        )

    axis_weeks = sorted(
        set(weeks) | {week for week, _ in planned_distance or []}
    )

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
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=1500,
    )


def plot_time(
    weeks: list[TimeZoneWeek],
    output: str,
    *,
    time_points: list[TimePoint] | None = None,
    planned_time: list[tuple[date, float]] | None = None,
    planned_zone_weeks: list[TimeZoneWeek] | None = None,
    planned_zone_label: str = "planned zones",
    zone_points: list[ZoneAveragePoint] | None = None,
    zone_window_days: int | None = None,
    windows: AverageWindows | None = None,
    time_scale: float = 7.0,
    zone_scale: float = 7.0,
    ylabel: str = "hours / week",
    title: str = "Weekly running time by pace zone",
    as_html: bool = False,
) -> str:
    """Weekly running time stacked by pace zone with zone EWMA lines."""
    _require_data(weeks, time_points)
    windows = windows or AverageWindows()
    planned_zone_weeks = planned_zone_weeks or []
    zone_count = (
        len(weeks[0].zones)
        if weeks
        else len(zone_points[0].zones) if zone_points
        else len(planned_zone_weeks[0].zones) if planned_zone_weeks
        else 0
    )

    if zone_points:
        figure = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            row_heights=[3, 2],
            vertical_spacing=0.08,
            subplot_titles=(
                "",
                (
                    f"{zone_window_days}-day EWMA stacked by pace zone"
                    if zone_window_days
                    else "EWMA stacked by pace zone"
                ),
            ),
        )
    else:
        figure = go.Figure()

    week_dates = [week.week for week in weeks]

    if weeks:
        bottoms = [0.0] * len(weeks)

        for index in range(zone_count):
            values = [week.zones[index] / 3600 for week in weeks]
            _add(
                figure,
                go.Bar(
                    x=week_dates,
                    y=values,
                    base=bottoms,
                    name=f"Z{index + 1}",
                    width=WEEK_MS,
                    marker_color=ZONE_COLORS[index % len(ZONE_COLORS)],
                ),
                row=1 if zone_points else None,
                col=1 if zone_points else None,
            )
            bottoms = [
                bottom + value
                for bottom, value in zip(bottoms, values)
            ]

        unzoned = [week.unzoned / 3600 for week in weeks]

        if any(unzoned):
            _add(
                figure,
                go.Bar(
                    x=week_dates,
                    y=unzoned,
                    base=bottoms,
                    name="Unzoned",
                    width=WEEK_MS,
                    marker_color=UNZONED_COLOR,
                ),
                row=1 if zone_points else None,
                col=1 if zone_points else None,
            )

    planned_zone_dates = {week.week for week in planned_zone_weeks}

    if planned_zone_weeks:
        planned_bottoms = [0.0] * len(planned_zone_weeks)

        for index in range(zone_count):
            values = [
                week.zones[index] / 3600
                for week in planned_zone_weeks
            ]
            _add(
                figure,
                go.Bar(
                    x=[week.week for week in planned_zone_weeks],
                    y=values,
                    base=planned_bottoms,
                    name=(
                        planned_zone_label if index == 0 else None
                    ),
                    width=WEEK_MS,
                    showlegend=index == 0,
                    marker={
                        "color": "rgba(0, 0, 0, 0)",
                        "line": {
                            "color": ZONE_LINE_COLORS[
                                index % len(ZONE_LINE_COLORS)
                            ],
                            "width": 1,
                        },
                        "pattern": {
                            "shape": PLANNED_PATTERN,
                            "fgcolor": ZONE_LINE_COLORS[
                                index % len(ZONE_LINE_COLORS)
                            ],
                            "solidity": 0.35,
                        },
                    },
                ),
                row=1 if zone_points else None,
                col=1 if zone_points else None,
            )
            planned_bottoms = [
                bottom + value
                for bottom, value in zip(planned_bottoms, values)
            ]

    planned_totals = [
        (week, seconds / 3600)
        for week, seconds in planned_time or []
        if week not in planned_zone_dates
    ]

    if planned_totals:
        _add(
            figure,
            go.Bar(
                x=[week for week, _ in planned_totals],
                y=[value for _, value in planned_totals],
                name="planned",
                width=WEEK_MS,
                marker={
                    "color": "rgba(0, 0, 0, 0)",
                    "line": {"color": "black", "width": 1.4},
                },
            ),
            row=1 if zone_points else None,
            col=1 if zone_points else None,
        )

    if time_points:
        _plot_average_lines(
            figure,
            time_points,
            windows,
            scale=time_scale / 3600,
            label=lambda attribute, days: f"{days}d avg (weekly)",
            row=1 if zone_points else None,
            col=1 if zone_points else None,
        )

    axis_weeks = sorted(
        set(week_dates if weeks else [])
        | {week for week, _ in planned_time or []}
        | planned_zone_dates
    )

    if axis_weeks:
        figure.update_xaxes(
            range=[
                axis_weeks[0],
                axis_weeks[-1] + timedelta(days=7),
            ]
        )

    if zone_points:
        actual_count = sum(
            1 for point in zone_points if not point.projected
        )
        projected = [point for point in zone_points if point.projected]

        for index in range(zone_count):
            _add(
                figure,
                go.Scatter(
                    x=[point.date for point in zone_points],
                    y=[
                        point.zones[index] * zone_scale / 3600
                        for point in zone_points
                    ],
                    mode="lines",
                    name=f"Z{index + 1}",
                    stackgroup="one",
                    showlegend=False,
                    line={
                        "color": ZONE_LINE_COLORS[
                            index % len(ZONE_LINE_COLORS)
                        ],
                        "width": 1.2,
                    },
                ),
                row=2,
                col=1,
            )

        if projected and actual_count:
            figure.add_vline(
                x=projected[0].date,
                line_width=1,
                line_dash="dash",
                line_color="#7f7f7f",
                row=2,
                col=1,
            )

        figure.update_yaxes(title_text=ylabel, row=2, col=1)
        figure.update_xaxes(
            title_text="week starting (Monday)",
            row=2,
            col=1,
        )
        figure.update_yaxes(title_text=ylabel, row=1, col=1)
    else:
        figure.update_xaxes(title_text="week starting (Monday)")

    figure.update_layout(
        template="plotly_white",
        title=title,
        barmode="overlay",
        height=800,
        margin={"l": 60, "r": 30, "t": 70, "b": 60},
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="x unified",
    )

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=2400 if zone_points else 1500,
    )


def _subt_points_for(points: list[SubtPoint], category: str, value):
    return sorted(
        (
            point for point in points
            if point.category == category and value(point) is not None
        ),
        key=lambda point: point.date,
    )


def plot_subt(
    points: list[SubtPoint],
    output: str,
    window: int = 5,
    title: str = "subT and LT1 work intervals",
    as_html: bool = False,
) -> str:
    """Pace and heart rate in two stacked panels sharing a date axis."""
    _require_data(points)
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[3, 2],
        vertical_spacing=0.08,
        subplot_titles=("Pace", "Average heart rate"),
    )
    plotted = False
    pace_values = [
        point.pace_s_per_km
        for point in points
        if point.pace_s_per_km is not None
    ]

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
                    ),
                    row=1,
                    col=1,
                )

            if len(pace) >= 2:
                figure.add_trace(
                    go.Scatter(
                        x=dates,
                        y=sma(values, window),
                        mode="lines",
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
                    showlegend=False,
                ),
                row=2,
                col=1,
            )

        if len(hr) >= 2:
            figure.add_trace(
                go.Scatter(
                    x=dates,
                    y=sma(values, window),
                    mode="lines",
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
                showlegend=False,
            ),
            row=2,
            col=1,
        )

    if not plotted:
        raise ValueError("no data to plot")

    if pace_values:
        low = min(pace_values)
        high = max(pace_values)
        ticks = [
            low + (high - low) * index / 4
            for index in range(5)
        ]
        figure.update_yaxes(
            autorange="reversed",
            tickvals=ticks,
            ticktext=[format_pace(value) for value in ticks],
            row=1,
            col=1,
        )

    figure.update_yaxes(title_text="pace (min/km)", row=1, col=1)
    figure.update_yaxes(title_text="heart rate (bpm)", row=2, col=1)
    figure.update_xaxes(title_text="date", row=2, col=1)
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=900,
        margin={"l": 60, "r": 30, "t": 70, "b": 60},
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="x unified",
    )
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=2400,
    )


def plot_load(
    points: list[LoadPoint],
    output: str,
    planned_load: list[tuple[date, float]] | None = None,
    windows: AverageWindows | None = None,
    title: str = "Training load",
    as_html: bool = False,
) -> str:
    """Daily load bars with base, fitness, and fatigue EWMA lines."""
    _require_data(points)
    windows = windows or AverageWindows()
    actual = [point for point in points if not point.projected]
    figure = go.Figure()
    figure.add_bar(
        x=[point.date for point in actual],
        y=[point.load for point in actual],
        name="daily load",
        marker_color="lightgrey",
    )

    if planned_load:
        actual_days = {
            point.date for point in actual if point.load > 0
        }
        planned = [
            (day, value)
            for day, value in planned_load
            if day not in actual_days
        ]

        if planned:
            _planned_total_bars(figure, planned)

    _plot_average_lines(
        figure,
        points,
        windows,
        label=lambda attribute, days: f"{attribute.title()} ({days}d)",
    )
    _base_layout(
        figure,
        title=title,
        xlabel="date",
        ylabel="training load",
    )
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=1500,
    )


def plot_vo2max(
    points: list[Vo2maxPoint],
    output: str,
    title: str = "Garmin running VO2max",
    as_html: bool = False,
) -> str:
    """Daily Garmin VO2max dots with 7- and 42-day EWMA lines."""
    _require_data(points)
    measured = [point for point in points if point.value is not None]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[point.date for point in measured],
            y=[point.value for point in measured],
            mode="markers",
            marker={"color": "#1f77b4", "size": 6, "opacity": 0.55},
            name="Garmin VO2max",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[point.date for point in points],
            y=[point.avg_7 for point in points],
            mode="lines",
            line={"color": "#ff7f0e", "width": 2},
            name="7-day avg",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[point.date for point in points],
            y=[point.avg_42 for point in points],
            mode="lines",
            line={"color": "#d62728", "width": 2},
            name="42-day avg",
        )
    )
    _base_layout(
        figure,
        title=title,
        xlabel="date",
        ylabel="VO2max (mL/kg/min)",
    )
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=1500,
    )


def plot_recovery(
    points: list[RecoveryPoint],
    output: str,
    planned_dates: list[date] | None = None,
    window_days: int = 7,
    title: str = "Recovery trends",
    as_html: bool = False,
) -> str:
    """HRV, resting HR, and sleep with rolling averages."""
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

        if raw:
            figure.add_trace(
                go.Scatter(
                    x=[day for day, _ in raw],
                    y=[value for _, value in raw],
                    mode="markers",
                    marker={"color": color, "size": 4, "opacity": 0.45},
                    name="daily",
                    showlegend=False,
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

        label = {
            "hrv": "HRV (ms)",
            "resting_hr": "Resting HR (bpm)",
            "sleep_s": "Sleep (hours)",
        }.get(raw_attr, raw_attr)

        figure.update_yaxes(
            title_text=label,
            row=row,
            col=1,
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

    figure.update_xaxes(title_text="date", row=3, col=1)
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=900,
        margin={"l": 60, "r": 30, "t": 70, "b": 60},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        hovermode="x unified",
    )
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=2700,
    )


def plot_overview(
    actual_bars: list[tuple[date, float, float, float]],
    planned_bars: list[tuple[date, float, float, float]],
    zone_series: ZoneGroupSeries,
    output: str,
    start: date,
    end: date,
    today: date,
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
            name=label.title(),
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

    for family, colors in (
        ("hard", HARD_LINE_COLORS),
        ("total", TOTAL_LINE_COLORS),
    ):
        for window in (7, 42, 182):
            attribute = f"{family}_{window}"
            style = {
                "color": colors[window],
                "width": LINE_WIDTHS[window],
                "dash": LINE_STYLES[window],
            }

            if actual:
                figure.add_trace(
                    go.Scatter(
                        x=[point.date.isoformat() for point in actual],
                        y=[
                            getattr(point, attribute) / 60
                            for point in actual
                        ],
                        mode="lines",
                        name=f"{family.title()} {window}d",
                        line=style,
                    )
                )

            if projected:
                bridge = actual[-1:] + projected
                figure.add_trace(
                    go.Scatter(
                        x=[point.date.isoformat() for point in bridge],
                        y=[
                            getattr(point, attribute) / 60
                            for point in bridge
                        ],
                        mode="lines",
                        name=f"{family.title()} {window}d",
                        line=style,
                        opacity=PROJECTED_OPACITY,
                        showlegend=False,
                    )
                )

    y_max = 90.0
    clipped = [
        (row[0], sum(row[1:]) / 60)
        for row in (*actual_bars, *planned_bars)
        if sum(row[1:]) / 60 > y_max
    ]

    if clipped:
        figure.add_trace(
            go.Scatter(
                x=[day.isoformat() for day, _ in clipped],
                y=[y_max - 2] * len(clipped),
                mode="markers",
                marker={
                    "symbol": "triangle-up",
                    "size": 9,
                    "color": "#7f7f7f",
                },
                name=f"clipped above {y_max:.0f} min",
                hovertext=[
                    f"{minutes:.0f} min (bar clipped)"
                    for _, minutes in clipped
                ],
                hoverinfo="text",
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
        title=title,
        height=520,
        margin={"l": 50, "r": 20, "t": 95, "b": 40},
        barmode="stack",
        bargap=0.1,
        hovermode="x unified",
        yaxis={
            "title": "minutes",
            "range": [0, y_max],
            "dtick": 15,
        },
        xaxis={"range": [start.isoformat(), end.isoformat()]},
        legend={
            "orientation": "h",
            "y": 1.18,
            "x": 0,
            "font": {"size": 9},
        },
    )
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=900,
    )
