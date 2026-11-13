"""Plotly chart builders shared by the CLI and the dashboard."""

from __future__ import annotations

import math
import warnings
from datetime import date, timedelta

import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings(
    "ignore",
    message=r"(?s).*Kaleido versions less than 1\.0\.0.*",
    category=DeprecationWarning,
)

from .analysis import (
    EFFICIENCY_UNIT,
    EquipmentStat,
    RaceResult,
    STEADY_BAND_LABEL,
    SUBT_CATEGORIES,
    pace_hr_efficiency_lines,
    pace_hr_trends,
    recovery_bands,
)
from .format import fmt_clock, fmt_time, format_pace
from .model import (
    AverageWindows,
    DistancePoint,
    LoadPoint,
    PaceHrPoint,
    RecoveryPoint,
    RpePoint,
    SubtPoint,
    TimePoint,
    TimeZoneWeek,
    Vo2maxMeasurement,
    Vo2maxPoint,
    ZoneAveragePoint,
)
from .style import (
    CLIPPED_COLOR,
    EASY_COLOR,
    EASY_EDGE,
    EASY_PLANNED_COLOR,
    HARD_COLOR,
    HARD_EDGE,
    HARD_LINE_COLORS,
    HARD_PLANNED_COLOR,
    LINE_STYLES,
    LINE_WIDTHS,
    LOAD_Y_MAX,
    PLANNED_PATTERN,
    PROJECTED_OPACITY,
    RECOVERY_BAND_COLORS,
    RECOVERY_BAND_MARKERS,
    RPE_LINE_COLORS,
    RPE_PER_LOAD,
    SUBT_HR_RANGE,
    SUBT_PACE_RANGE,
    TIME_Y_MAX,
    TOTAL_LINE_COLORS,
    UNZONED_COLOR,
    UNZONED_EDGE,
    UNZONED_PLANNED_COLOR,
    VOLUME_Y_MAX,
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
    "#8ecae6",
    "#219ebc",
    "#ffb3b3",
    "#ff6b6b",
    "#e63946",
)
ZONE_LINE_COLORS = (
    "#0077b6",
    "#023e8a",
    "#d00000",
    "#9d0208",
    "#6a040f",
)
SUBT_COLORS = {
    "short": "#1f77b4",
    "medium": "#ff7f0e",
    "long": "#2ca02c",
    "lt1": "#9467bd",
}
CHART_CATEGORIES = (*SUBT_CATEGORIES, "lt1")
WEEK_MS = 7 * 24 * 60 * 60 * 1000
COMPARE_VISIBLE_YEARS = 5

COMPARE_COLORS = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
    "#c49c94",
    "#f7b6d2",
    "#c7c7c7",
    "#dbdb8d",
    "#9edae5",
)


def compare_color(year: int) -> str:
    """Stable per-year compare color, independent of the plotted year set."""
    return COMPARE_COLORS[(year - 2009) % len(COMPARE_COLORS)]


def _require_data(*series) -> None:
    if not any(series):
        raise ValueError("no data to plot")


def _two_decimal_hover(figure: go.Figure) -> None:
    """Keep hover values compact; the default shows full float precision."""
    for key in figure.layout:
        if key.startswith("yaxis"):
            figure.layout[key].hoverformat = ".2f"


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
    _two_decimal_hover(figure)

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


def _legend_below(*, font_size: int | None = None) -> dict:
    legend = {
        "orientation": "h",
        "y": -0.07,
        "yanchor": "top",
        "x": 0,
    }

    if font_size is not None:
        legend["font"] = {"size": font_size}

    return legend


def _base_layout(figure, *, title: str, xlabel: str, ylabel: str):
    figure.update_layout(
        template="plotly_white",
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        height=800,
        margin={"l": 60, "r": 30, "t": 60, "b": 100},
        legend=_legend_below(),
        hovermode="x unified",
    )


def _plot_average_lines(
    figure,
    points,
    windows: AverageWindows,
    *,
    scale: float = 1.0,
    label,
    colors: dict[str, str] | None = None,
    dash: dict[str, str] | None = None,
    row: int | None = None,
    col: int | None = None,
):
    actual = [point for point in points if not point.projected]
    projected = [point for point in points if point.projected]
    colors = colors or AVERAGE_COLORS
    dash = dash or {}

    for attribute in ("base", "fitness", "fatigue"):
        style = {
            "color": colors[attribute],
            "width": 2,
        }

        if attribute in dash:
            style["dash"] = dash[attribute]

        if actual:
            _add(
                figure,
                go.Scatter(
                    x=[point.date for point in actual],
                    y=[getattr(point, attribute) * scale for point in actual],
                    mode="lines",
                    name=label(attribute, getattr(windows, attribute)),
                    line=style,
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
                    line={**style, "dash": "dash"},
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


def _clipped_markers(
    figure,
    x,
    values,
    limit: float,
    unit: str,
    *,
    row: int | None = None,
    col: int | None = None,
):
    """Mark bars that exceed a fixed axis limit instead of hiding them."""
    clipped = [
        (day, value)
        for day, value in zip(x, values)
        if value > limit
    ]

    if not clipped:
        return

    _add(
        figure,
        go.Scatter(
            x=[day for day, _ in clipped],
            y=[limit * 0.98] * len(clipped),
            mode="markers",
            marker={
                "symbol": "triangle-up",
                "size": 9,
                "color": CLIPPED_COLOR,
            },
            name=f"clipped above {limit:g} {unit}",
            hovertext=[
                f"{value:.2f} {unit} (bar clipped)"
                for _, value in clipped
            ],
            hoverinfo="text",
        ),
        row=row,
        col=col,
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

    _clipped_markers(
        figure,
        weeks,
        [value for _, value in data],
        VOLUME_Y_MAX,
        "km",
    )
    figure.update_yaxes(range=[0, VOLUME_Y_MAX], dtick=20)

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
    hard_points: list[TimePoint] | None = None,
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

    rows = 3 if zone_points else 2
    subplot_titles = ["", "share of weekly running time"]

    if zone_points:
        subplot_titles.append(
            (
                f"{zone_window_days}-day EWMA stacked by pace zone"
                if zone_window_days
                else "EWMA stacked by pace zone"
            )
        )

    figure = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        row_heights=[3, 2, 2][:rows],
        vertical_spacing=0.08,
        subplot_titles=tuple(subplot_titles),
    )

    week_dates = [week.week for week in weeks]
    totals = [
        (sum(week.zones) + week.unzoned) / 3600 for week in weeks
    ]

    if weeks:
        bottoms = [0.0] * len(weeks)
        unzoned = [week.unzoned / 3600 for week in weeks]
        shares = [
            (
                value / total * 100
                if total
                else 0.0
            )
            for value, total in zip(unzoned, totals)
        ]

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
                row=1,
                col=1,
            )
            _add(
                figure,
                go.Bar(
                    x=week_dates,
                    y=shares,
                    base=[0.0] * len(weeks),
                    name="Unzoned",
                    width=WEEK_MS,
                    showlegend=False,
                    marker_color=UNZONED_COLOR,
                ),
                row=2,
                col=1,
            )
            bottoms = [
                bottom + value
                for bottom, value in zip(bottoms, unzoned)
            ]
            percent_bottoms = list(shares)

        else:
            percent_bottoms = [0.0] * len(weeks)

        # Highest zones at the bottom, Z1 on top.
        for index in reversed(range(zone_count)):
            values = [week.zones[index] / 3600 for week in weeks]
            shares = [
                value / total * 100 if total else 0.0
                for value, total in zip(values, totals)
            ]
            color = ZONE_COLORS[index % len(ZONE_COLORS)]
            _add(
                figure,
                go.Bar(
                    x=week_dates,
                    y=values,
                    base=bottoms,
                    name=f"Z{index + 1}",
                    width=WEEK_MS,
                    marker_color=color,
                ),
                row=1,
                col=1,
            )
            _add(
                figure,
                go.Bar(
                    x=week_dates,
                    y=shares,
                    base=percent_bottoms,
                    name=f"Z{index + 1}",
                    width=WEEK_MS,
                    showlegend=False,
                    marker_color=color,
                ),
                row=2,
                col=1,
            )
            bottoms = [
                bottom + value
                for bottom, value in zip(bottoms, values)
            ]
            percent_bottoms = [
                bottom + value
                for bottom, value in zip(percent_bottoms, shares)
            ]

    planned_zone_dates = {week.week for week in planned_zone_weeks}

    if planned_zone_weeks:
        planned_bottoms = [0.0] * len(planned_zone_weeks)

        for index in reversed(range(zone_count)):
            values = [
                week.zones[index] / 3600
                for week in planned_zone_weeks
            ]
            first = index == zone_count - 1
            _add(
                figure,
                go.Bar(
                    x=[week.week for week in planned_zone_weeks],
                    y=values,
                    base=planned_bottoms,
                    name=planned_zone_label if first else None,
                    width=WEEK_MS,
                    showlegend=first,
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
                row=1,
                col=1,
            )
            planned_bottoms = [
                bottom + value
                for bottom, value in zip(planned_bottoms, values)
            ]

    _clipped_markers(
        figure,
        week_dates,
        [total for total in totals],
        TIME_Y_MAX,
        "h",
        row=1,
        col=1,
    )

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
            row=1,
            col=1,
        )

    if time_points:
        _plot_average_lines(
            figure,
            time_points,
            windows,
            scale=time_scale / 3600,
            label=lambda attribute, days: f"{days}d avg (weekly)",
            colors={
                attribute: TOTAL_LINE_COLORS[
                    getattr(windows, attribute)
                ]
                for attribute in ("base", "fitness", "fatigue")
            },
            dash={
                attribute: LINE_STYLES[getattr(windows, attribute)]
                for attribute in ("base", "fitness", "fatigue")
            },
            row=1,
            col=1,
        )

    if hard_points:
        _plot_average_lines(
            figure,
            hard_points,
            windows,
            scale=time_scale / 3600,
            label=lambda attribute, days: (
                f"hard {days}d avg (weekly)"
            ),
            colors={
                attribute: HARD_LINE_COLORS[
                    getattr(windows, attribute)
                ]
                for attribute in ("base", "fitness", "fatigue")
            },
            dash={
                attribute: LINE_STYLES[getattr(windows, attribute)]
                for attribute in ("base", "fitness", "fatigue")
            },
            row=1,
            col=1,
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

        for index in reversed(range(zone_count)):
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
                row=3,
                col=1,
            )

        if projected and actual_count:
            figure.add_vline(
                x=projected[0].date,
                line_width=1,
                line_dash="dash",
                line_color="#7f7f7f",
                row=3,
                col=1,
            )

        figure.update_yaxes(
            title_text=ylabel,
            range=[0, TIME_Y_MAX],
            dtick=2,
            row=3,
            col=1,
        )

    figure.update_yaxes(
        title_text="% of week",
        range=[0, 100],
        ticksuffix="%",
        dtick=25,
        row=2,
        col=1,
    )
    figure.add_hline(
        y=22,
        line_width=1,
        line_dash="dot",
        line_color="#7f7f7f",
        annotation_text="22%",
        annotation_position="right",
        row=2,
        col=1,
    )
    figure.update_yaxes(
        title_text=ylabel,
        range=[0, TIME_Y_MAX],
        dtick=2,
        row=1,
        col=1,
    )
    figure.update_xaxes(
        title_text="week starting (Monday)",
        row=rows,
        col=1,
    )

    figure.update_layout(
        template="plotly_white",
        title=title,
        barmode="overlay",
        height=1500,
        margin={"l": 60, "r": 30, "t": 70, "b": 110},
        legend=_legend_below(),
        hovermode="x unified",
    )

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=3600 if zone_points else 2400,
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
                    y=_time_ewma(dates, values, window_days),
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
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=[point.efficiency for point in efficiency],
                mode="markers",
                marker={"color": color, "size": 7},
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
    figure.update_yaxes(
        title_text="efficiency (m/excess beat, work reps)",
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
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=3300,
    )


def plot_load(
    points: list[LoadPoint],
    output: str,
    planned_load: list[tuple[date, float]] | None = None,
    windows: AverageWindows | None = None,
    rpe_points: list[RpePoint] | None = None,
    title: str = "Training load",
    as_html: bool = False,
) -> str:
    """Daily load bars with EWMAs, plus session RPE on a right axis."""
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

    rpe = [point for point in rpe_points or [] if point.base is not None]

    for attribute, window in (
        ("base", 182),
        ("fitness", 42),
        ("fatigue", 7),
    ):
        if not rpe:
            break

        figure.add_trace(
            go.Scatter(
                x=[point.date for point in rpe],
                y=[getattr(point, attribute) for point in rpe],
                mode="lines",
                name=f"RPE {window}d",
                yaxis="y2",
                line={
                    "color": RPE_LINE_COLORS[window],
                    "width": LINE_WIDTHS[window],
                    "dash": LINE_STYLES[window],
                },
            )
        )

    if rpe:
        highest = max(
            max(
                getattr(point, attribute)
                for point in rpe
                for attribute in ("base", "fitness", "fatigue")
            ),
            0.0,
        )
        load_max = max(
            LOAD_Y_MAX,
            math.ceil(highest) * RPE_PER_LOAD,
        )
    else:
        load_max = LOAD_Y_MAX

    _clipped_markers(
        figure,
        [point.date for point in actual],
        [point.load for point in actual],
        load_max,
        "load",
    )
    figure.update_yaxes(range=[0, load_max], dtick=25)

    _base_layout(
        figure,
        title=title,
        xlabel="date",
        ylabel="training load",
    )

    if rpe:
        figure.update_layout(
            yaxis2={
                "title": "RPE",
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
                "range": [0, load_max / RPE_PER_LOAD],
                "dtick": 1,
            },
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


PACE_HR_SYMBOLS = {
    "easy": "circle",
    "recovery": "diamond",
    "intervals": "square",
    "longrun": "triangle-up",
    "race": "star",
    "tempo": "cross",
    "fartlek": "pentagon",
    "race-support": "triangle-down",
    "other": "x",
}
PACE_HR_CATEGORY_ORDER = tuple(PACE_HR_SYMBOLS)
PACE_HR_SYMBOL_TEXT = {
    "easy": "○",
    "recovery": "◇",
    "intervals": "□",
    "longrun": "△",
    "race": "★",
    "tempo": "+",
    "fartlek": "⬟",
    "race-support": "▽",
    "other": "×",
}


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
        range=[2.0, 5.2],
        tickvals=tick_speeds,
        ticktext=[format_pace(1000 / speed) for speed in tick_speeds],
    )
    figure.update_yaxes(
        title_text="avg HR (bpm)",
        range=[90, 190],
        dtick=10,
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
                    )
                    for point in chunk
                ],
                hoverinfo="text",
            )
        )

    trends = pace_hr_trends(points)
    colors = ("#1f77b4", "#d62728")
    notes = []

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

    efficiency_lines = pace_hr_efficiency_lines(points)

    for line in efficiency_lines:
        figure.add_trace(
            go.Scatter(
                x=[line.speed_low, line.speed_high],
                y=[
                    line.at(line.speed_low),
                    line.at(line.speed_high),
                ],
                mode="lines",
                name=f"{line.label} efficiency",
                line={
                    "color": color_for[line.label],
                    "width": 1.6,
                    "dash": "dash",
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
            "dashed efficiency lines use steady 45–75 min non-quality "
            "runs; outlined points are their inputs — all runs are shown"
        )

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
                    )
                    for point in chunk
                ],
                hoverinfo="text",
            )
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
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=1500,
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
        if result.activity.distance_m and result.activity.duration_s
    ]
    figure = go.Figure()

    if points:
        years = [point.activity.date.year for point in points]
        figure.add_trace(
            go.Scatter(
                x=[point.activity.distance_m / 1000 for point in points],
                y=[point.activity.duration_s / 60 for point in points],
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
                    f"{point.activity.name or point.bucket}"
                    f"<br>{point.activity.distance_m / 1000:.2f} km, "
                    f"{fmt_clock(point.activity.duration_s)}"
                    for point in points
                ],
                hoverinfo="text",
            )
        )

    if fit is not None and points:
        low = min(point.activity.distance_m for point in points)
        high = max(point.activity.distance_m for point in points)
        figure.add_trace(
            go.Scatter(
                x=[low / 1000, high / 1000],
                y=[fit.duration_s(low) / 60, fit.duration_s(high) / 60],
                mode="lines",
                name=f"Riegel (n={fit.points})",
                line={"color": "#111111", "width": 2, "dash": "dash"},
                hoverinfo="skip",
            )
        )
        figure.add_annotation(
            text=f"time ∝ distance^{fit.exponent:.2f} · R² = {fit.r2:.2f}",
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
        hovermode="closest",
    )
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=1100,
    )


def plot_equipment(
    stats: list[EquipmentStat],
    output: str,
    title: str = "Gear mileage",
    as_html: bool = False,
) -> str:
    """Horizontal mileage bars with target markers."""
    _require_data(stats)
    ordered = list(reversed(stats))
    labels = [stat.label for stat in ordered]
    colors = [
        "#c7c7c7" if stat.retired else "#1f77b4"
        for stat in ordered
    ]

    figure = go.Figure(
        go.Bar(
            x=[stat.distance_m / 1000 for stat in ordered],
            y=labels,
            orientation="h",
            name="mileage",
            marker={"color": colors},
            hovertemplate=(
                "%{y}<br>%{x:.0f} km<extra></extra>"
            ),
        )
    )

    targets = [stat for stat in ordered if stat.target_distance_m]
    if targets:
        figure.add_trace(
            go.Scatter(
                x=[
                    stat.target_distance_m / 1000
                    for stat in targets
                ],
                y=[stat.label for stat in targets],
                mode="markers",
                name="target",
                marker={
                    "symbol": "line-ns-open",
                    "size": 16,
                    "color": "#111111",
                    "line": {"width": 2},
                },
                hovertemplate=(
                    "%{y}<br>target %{x:.0f} km<extra></extra>"
                ),
            )
        )

    figure.update_xaxes(title_text="km")
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=max(500, 60 * len(stats) + 180),
        margin={"l": 170, "r": 30, "t": 70, "b": 100},
        legend=_legend_below(),
        hovermode="closest",
    )
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=1200,
    )


def plot_compare_vo2max(
    measurements: list[Vo2maxMeasurement],
    output: str,
    title: str = "Garmin VO2max by year",
    as_html: bool = False,
) -> str:
    """Raw Garmin VO2max readings, one marker per activity, by year."""
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
    figure.update_yaxes(title_text="Garmin VO2max")
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=700,
        margin={"l": 60, "r": 30, "t": 70, "b": 100},
        legend=_legend_below(),
        hovermode="closest",
    )
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
        "load": "load / day",
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
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=1500,
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

    figure.update_xaxes(title_text="date", row=3, col=1)
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=900,
        margin={"l": 60, "r": 30, "t": 70, "b": 110},
        legend=_legend_below(),
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

    vo2max = [
        point
        for point in vo2max_points or []
        if start <= point.date <= end and point.value is not None
    ]

    if vo2max:
        figure.add_trace(
            go.Scatter(
                x=[point.date.isoformat() for point in vo2max],
                y=[point.value for point in vo2max],
                mode="lines",
                name="VO2max",
                yaxis="y2",
                line={"color": "black", "width": 2},
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
        "height": 520,
        "margin": {"l": 50, "r": 20, "t": 95, "b": 100},
        "barmode": "stack",
        "bargap": 0.1,
        "hovermode": "x unified",
        "yaxis": {
            "title": "minutes",
            "range": [0, y_max],
            "dtick": 15,
        },
        "xaxis": {"range": [start.isoformat(), end.isoformat()]},
        "legend": _legend_below(font_size=9),
    }

    if vo2max:
        values = [point.value for point in vo2max]
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
        }

    figure.update_layout(**layout)
    return _render(
        figure,
        output,
        as_html=as_html,
        width=1800,
        height=900,
    )
