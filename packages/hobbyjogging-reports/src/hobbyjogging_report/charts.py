"""Plotly chart builders shared by the CLI and the dashboard."""

from __future__ import annotations

import math
import warnings
from datetime import date, timedelta

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from hobbyjogging_core.model import TrainingPeriod

warnings.filterwarnings(
    "ignore",
    message=r"(?s).*Kaleido versions less than 1\.0\.0.*",
    category=DeprecationWarning,
)

from .analysis import (
    EFFICIENCY_UNIT,
    EquipmentStat,
    group_equipment,
    PbProgression,
    RaceResult,
    STEADY_BAND_LABEL,
    SUBT_CATEGORIES,
    pace_hr_efficiency_lines,
    pace_hr_trends,
    pace_hr_year_efficiency,
    pace_s_per_km,
    RacePacePoint,
    ThresholdPoint,
    recovery_bands,
    riegel_reference,
    riegel_time,
    week_start,
)
from .format import fmt_clock, fmt_time, format_pace, format_weather
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
    AXIS_HEADROOM,
    AXIS_TAIL,
    CLIPPED_COLOR,
    EASY_COLOR,
    EASY_EDGE,
    EASY_PLANNED_COLOR,
    EQUIPMENT_CATEGORY_COLORS,
    HARD_COLOR,
    HARD_EDGE,
    HARD_LINE_COLORS,
    HARD_PLANNED_COLOR,
    LINE_STYLES,
    LINE_WIDTHS,
    LOAD_WEEK_Y_MIN,
    LOAD_WEEK_Y_STEP,
    MINUTES_Y_MIN,
    MINUTES_Y_STEP,
    PLANNED_PATTERN,
    PROJECTED_OPACITY,
    RECOVERY_BAND_COLORS,
    RECOVERY_BAND_MARKERS,
    PERIOD_LABEL_COLOR,
    ILLNESS_BAND_COLOR,
    RPE_AXIS_MIN,
    RPE_LINE_COLORS,
    SEASON_BAND_COLOR,
    SPIKE_COLOR,
    SUBT_HR_RANGE,
    SUBT_PACE_RANGE,
    HARD_MINUTES_STEP,
    TIME_Y_MIN,
    TIME_Y_STEP,
    TOTAL_LINE_COLORS,
    UNZONED_COLOR,
    UNZONED_EDGE,
    UNZONED_PLANNED_COLOR,
    VOLUME_Y_MIN,
    VOLUME_Y_STEP,
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

VOLUME_BAR_COLOR = "lightgrey"
LOAD_BAR_COLOR = "#b0bec5"
CROSS_LOAD_COLOR = "#d8cfc2"

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
# The pace/HR scatters share one linear-speed x-axis; fits run across it.
PACE_HR_SPEED_RANGE = (2.0, 5.2)
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


COMPARE_COLOR_ANCHOR_YEAR = 2026


def compare_color(year: int) -> str:
    """A stable per-year compare colour, strongest contrast for recent years.

    The palette runs backwards from the anchor year, so the newest years get
    the saturated colours and old years fade out. A year keeps one colour
    across every compare chart and the colour does not depend on the plotted
    range. Move the anchor forward when the data does; each year beyond it
    takes the next (lighter) colour, so bump it before the palette wraps.
    """
    return COMPARE_COLORS[
        (COMPARE_COLOR_ANCHOR_YEAR - year) % len(COMPARE_COLORS)
    ]


def _fade(color: str, alpha: float) -> str:
    """The same colour at reduced opacity, for planned or ghost marks."""
    if not color.startswith("#") or len(color) != 7:
        return color

    return "rgba({}, {}, {}, {})".format(
        *(int(color[index:index + 2], 16) for index in (1, 3, 5)),
        alpha,
    )


def _darker(color: str, factor: float = 0.6) -> str:
    """Darken a hex colour so a line stays legible over pale markers."""
    if not color.startswith("#") or len(color) != 7:
        return color

    return "rgb({}, {}, {})".format(
        *(
            int(int(color[index:index + 2], 16) * factor)
            for index in (1, 3, 5)
        )
    )


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


def _legend_below(
    *,
    font_size: int | None = None,
    columns: int | None = None,
) -> dict:
    legend = {
        "orientation": "h",
        "y": -0.07,
        "yanchor": "top",
        "x": 0,
    }

    if font_size is not None:
        legend["font"] = {"size": font_size}
    if columns:
        legend["entrywidth"] = round(1 / columns, 4)
        legend["entrywidthmode"] = "fraction"
        # A wrapped horizontal legend otherwise fills in reverse trace order.
        legend["traceorder"] = "normal"

    return legend


def _crosshair(figure, *, second_y: bool = False) -> None:
    """A vertical guide on the nearest day and a horizontal one at the cursor."""
    spikes = {
        "showspikes": True,
        "spikemode": "across",
        "spikethickness": 1,
        "spikecolor": SPIKE_COLOR,
        "spikedash": "dot",
    }

    # x snaps to the data so a day stays marked; y follows the pointer so a
    # value can be read anywhere, not only at a plotted point.
    figure.update_xaxes(**spikes, spikesnap="data")
    figure.update_yaxes(**spikes, spikesnap="cursor")

    if second_y:
        figure.update_layout(
            yaxis2={**spikes, "spikesnap": "cursor"},
        )


def _base_layout(figure, *, title: str, xlabel: str, ylabel: str):
    figure.update_layout(
        template="plotly_white",
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        # Planned bars stack on the actual bar of the same week; the grouped
        # default would place them side by side instead.
        barmode="overlay",
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
    yaxis: str | None = None,
    projection_label: str = "avg projection",
):
    actual = [point for point in points if not point.projected]
    projected = [point for point in points if point.projected]
    colors = colors or AVERAGE_COLORS
    dash = {
        attribute: LINE_STYLES[getattr(windows, attribute)]
        for attribute in ("base", "fitness", "fatigue")
    } | (dash or {})

    series = []

    # Shortest window first, so the smoothest line ends up on top.
    for attribute in ("fatigue", "fitness", "base"):
        style = {
            "color": colors[attribute],
            "width": 2,
        }

        if attribute in dash:
            style["dash"] = dash[attribute]

        if actual:
            series.append((
                [point.date for point in actual],
                [getattr(point, attribute) * scale for point in actual],
                style,
                1.0,
                label(attribute, getattr(windows, attribute)),
                True,
            ))

        if projected:
            bridge = actual[-1:] + projected
            series.append((
                [point.date for point in bridge],
                [
                    getattr(point, attribute) * scale
                    for point in bridge
                ],
                {**style, "dash": "dash"},
                PROJECTED_OPACITY,
                label(attribute, getattr(windows, attribute)),
                False,
            ))

    # All halos go down before any line, so a later halo cannot cut an
    # earlier line at a crossing; the pale halo is what keeps a line legible
    # over the bars.
    for x, y, style, _opacity, _name, _show in series:
        _outline(
            figure,
            x,
            y,
            style["width"],
            row=row,
            col=col,
            yaxis=yaxis,
        )

    for x, y, style, opacity, name, showlegend in series:
        _add(
            figure,
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=name,
                line=style,
                opacity=opacity,
                showlegend=showlegend,
                yaxis=yaxis,
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
                name=projection_label,
                line={
                    "color": AVERAGE_COLORS["base"],
                    "width": 2,
                    "dash": "dash",
                },
            ),
            row=row,
            col=col,
        )


def _bulk_range(values, *, step: float) -> list[float] | None:
    """Round a range around the bulk, so an extreme value cannot flatten it."""
    ordered = sorted(value for value in values if value is not None)

    if not ordered:
        return None

    dropped = max(1, round(AXIS_TAIL * (len(ordered) - 1)))
    low = ordered[min(dropped, len(ordered) - 1)]
    high = ordered[max(0, len(ordered) - 1 - dropped)]

    return [
        step * math.floor(low / AXIS_HEADROOM / step),
        step * math.ceil(high * AXIS_HEADROOM / step),
    ]


def _axis_ceiling(
    values,
    *,
    step: float,
    floor: float,
    tail: float = AXIS_TAIL,
) -> float:
    """Round an axis ceiling up from the bulk of the values, not the peak.

    The top ``tail`` share of the values is dropped (always at least one), so a
    single ultra week or long day cannot set the axis; what is left gets a
    little headroom and rounds up to ``step``, which leaves the typical bar
    comfortably inside the frame. Later values above the result are drawn
    clipped and marked.
    """
    ordered = sorted(value for value in values if value is not None)

    if not ordered:
        return floor

    dropped = max(1, round(tail * (len(ordered) - 1)))
    upper = ordered[max(0, len(ordered) - 1 - dropped)]

    return max(floor, step * math.ceil(upper * AXIS_HEADROOM / step))


def _clipped_markers(
    figure,
    points: list[tuple[object, float]],
    limit: float,
    unit: str,
    *,
    row: int | None = None,
    col: int | None = None,
    number: str = ".2f",
):
    """Mark values that exceed the axis ceiling instead of hiding them."""
    clipped = [
        (where, value)
        for where, value in points
        if value > limit
    ]

    if not clipped:
        return

    _add(
        figure,
        go.Scatter(
            x=[where for where, _ in clipped],
            y=[limit * 0.98] * len(clipped),
            mode="markers",
            marker={
                "symbol": "triangle-up",
                "size": 9,
                "color": CLIPPED_COLOR,
            },
            name=f"clipped above {limit:g} {unit}",
            hovertext=[
                f"{value:{number}} {unit} (bar clipped)"
                for _, value in clipped
            ],
            hoverinfo="text",
        ),
        row=row,
        col=col,
    )


def _period_bands(
    figure,
    periods: list[TrainingPeriod] | None,
    *,
    kind: str,
    color: str,
    start: date,
    end: date,
    bottom: float,
    top: float,
    labels: bool = False,
    row: int | None = None,
    col: int | None = None,
) -> None:
    """Shade training periods of one kind behind a date-axis chart."""
    for period in periods or []:
        if period.kind != kind or period.start_date is None:
            continue

        first = max(period.start_date, start)
        last = min(period.end_date or end, end)

        if last < first:
            continue

        label = period.label.strip() or period.kind.title()
        span = (
            f"{period.start_date} \u2192 {period.end_date}"
            if period.end_date
            else f"{period.start_date} \u2192 ongoing"
        )
        hover = f"{label}: {span}"
        trace = go.Scatter(
            x=[
                first,
                first,
                last + timedelta(days=1),
                last + timedelta(days=1),
            ],
            y=[bottom, top, top, bottom],
            fill="toself",
            mode="lines",
            line={"width": 0},
            fillcolor=color,
            hoveron="fills",
            hoverinfo="text",
            name=hover,
            text=hover,
            showlegend=False,
        )
        _add(figure, trace, row=row, col=col)

        if labels:
            annotation = {
                "x": first,
                "y": top,
                "text": label,
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "top",
                "font": {"size": 10, "color": PERIOD_LABEL_COLOR},
            }
            if row is None:
                figure.add_annotation(**annotation)
            else:
                figure.add_annotation(**annotation, row=row, col=col)


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
    periods: list[TrainingPeriod] | None = None,
    as_html: bool = False,
) -> str:
    """Weekly running volume bars with distance-average lines."""
    _require_data(data, distance_points)
    windows = windows or AverageWindows()
    weeks = [week for week, _ in data]
    actual_by_week = dict(data)
    planned_by_week = dict(planned_distance or [])
    planned_marks = [
        (week, value + actual_by_week.get(week, 0.0))
        for week, value in planned_by_week.items()
    ]
    axis_weeks = sorted(set(weeks) | set(planned_by_week))
    ceiling = max(
        _axis_ceiling(
            [value for _, value in data]
            + [value for _, value in planned_marks],
            step=VOLUME_Y_STEP,
            floor=VOLUME_Y_MIN,
        ),
        _axis_ceiling(
            [
                getattr(point, attribute) * distance_scale
                for point in distance_points or []
                for attribute in ("base", "fitness")
            ],
            step=VOLUME_Y_STEP,
            floor=VOLUME_Y_MIN,
        ),
    )

    figure = go.Figure()

    if axis_weeks:
        _period_bands(
            figure,
            periods,
            kind="season",
            color=SEASON_BAND_COLOR,
            start=axis_weeks[0],
            end=axis_weeks[-1] + timedelta(days=7),
            bottom=0,
            top=ceiling,
            labels=True,
        )

    if data:
        figure.add_bar(
            x=weeks,
            y=[value for _, value in data],
            name="weekly km",
            width=WEEK_MS,
            marker_color=VOLUME_BAR_COLOR,
        )

    if planned_distance:
        figure.add_bar(
            x=[week for week, _ in planned_distance],
            y=[value for _, value in planned_distance],
            # The current week already has an actual bar; stack the plan for
            # its remaining days on top of it.
            base=[
                actual_by_week.get(week, 0.0)
                for week, _ in planned_distance
            ],
            name="planned km",
            width=WEEK_MS,
            marker={
                "color": _fade(VOLUME_BAR_COLOR, 0.45),
                "line": {"color": "#9aa5b1", "width": 0.6},
                "pattern": {
                    "shape": "/",
                    "fgcolor": "#9aa5b1",
                    "solidity": 0.45,
                },
            },
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
        list(data) + planned_marks,
        ceiling,
        "km",
    )
    figure.update_yaxes(range=[0, ceiling], dtick=20)

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
    _crosshair(figure)

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
    # Hard running is read in minutes per week, on its own right-hand axis;
    # the bar and total axes stay in hours.
    hard_axis = f"y{rows + 1}" if hard_points else None
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
    display_weeks = sorted(
        set(week_dates) | {week.week for week in planned_zone_weeks}
    )
    actual_week_totals = {
        week.week: (sum(week.zones) + week.unzoned) / 3600
        for week in weeks
    }
    planned_week_totals = {
        week.week: (sum(week.zones) + week.unzoned) / 3600
        for week in planned_zone_weeks
    }
    planned_time_by_week = {
        week: seconds / 3600
        for week, seconds in planned_time or []
        if week not in planned_week_totals
    }
    # In an overlapping week the share panel normalizes to the combined
    # actual and planned time; a total-only plan has no zone split, so it
    # leaves the shares alone.
    share_totals = {
        week: actual_week_totals.get(week, 0.0)
        + planned_week_totals.get(week, 0.0)
        for week in display_weeks
    }
    hour_bottom = {week: 0.0 for week in display_weeks}
    share_bottom = {week: 0.0 for week in display_weeks}

    def add_segment(weeks, values, name, color, *, legend):
        """One stacked bar segment, in hours and as a share."""
        xs = list(weeks)

        if not xs:
            return

        _add(
            figure,
            go.Bar(
                x=xs,
                y=[values[week] for week in xs],
                base=[hour_bottom[week] for week in xs],
                name=name,
                width=WEEK_MS,
                showlegend=legend,
                marker_color=color,
            ),
            row=1,
            col=1,
        )
        shares = [
            (
                values[week] / share_totals[week] * 100
                if share_totals[week]
                else 0.0
            )
            for week in xs
        ]
        _add(
            figure,
            go.Bar(
                x=xs,
                y=shares,
                base=[share_bottom[week] for week in xs],
                name=name,
                width=WEEK_MS,
                showlegend=False,
                marker_color=color,
            ),
            row=2,
            col=1,
        )

        for week, share in zip(xs, shares):
            hour_bottom[week] += values[week]
            share_bottom[week] += share

    # Unzoned first, then each zone's actual with its plan directly above, so
    # a week reads bottom to top as hard done, hard planned, easy done, easy
    # planned.
    unzoned_actual = {
        week.week: week.unzoned / 3600 for week in weeks if week.unzoned
    }
    add_segment(
        unzoned_actual.keys(),
        unzoned_actual,
        "Unzoned",
        UNZONED_COLOR,
        legend=True,
    )
    unzoned_planned = {
        week.week: week.unzoned / 3600
        for week in planned_zone_weeks
        if week.unzoned
    }
    add_segment(
        unzoned_planned.keys(),
        unzoned_planned,
        "planned unzoned",
        _fade(UNZONED_COLOR, 0.45),
        legend=True,
    )

    if planned_zone_weeks:
        # A zero-height bar keeps the faded planned bars in the legend; an
        # empty trace would not render one, and giving a segment the group
        # name would make its hover read "planned zones" instead of its zone.
        _add(
            figure,
            go.Bar(
                x=[planned_zone_weeks[0].week],
                y=[0.0],
                name=planned_zone_label,
                marker_color=_fade(ZONE_COLORS[0], 0.45),
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )

    # Two blocks per week: hard (Z3+) and easy (Z1-2), each with the actual
    # time first and the plan for the rest of the week directly above it.
    for group in (
        tuple(range(zone_count - 1, 1, -1)),
        tuple(range(min(1, zone_count - 1), -1, -1)),
    ):
        for planned in (False, True):
            for index in group:
                color = ZONE_COLORS[index % len(ZONE_COLORS)]

                if planned:
                    values_for_week = {
                        week.week: week.zones[index] / 3600
                        for week in planned_zone_weeks
                    }
                    add_segment(
                        values_for_week.keys(),
                        values_for_week,
                        f"Z{index + 1} planned",
                        _fade(color, 0.45),
                        legend=False,
                    )
                else:
                    values_for_week = {
                        week.week: week.zones[index] / 3600
                        for week in weeks
                    }
                    add_segment(
                        values_for_week.keys(),
                        values_for_week,
                        f"Z{index + 1}",
                        color,
                        legend=True,
                    )

    planned_totals = [
        (week, seconds / 3600)
        for week, seconds in planned_time or []
        if week not in planned_week_totals
    ]

    if planned_totals:
        weeks = [week for week, _ in planned_totals]
        values = [value for _, value in planned_totals]
        _add(
            figure,
            go.Bar(
                x=weeks,
                y=values,
                base=[hour_bottom.get(week, 0.0) for week in weeks],
                name="planned total",
                width=WEEK_MS,
                marker_color=_fade(VOLUME_BAR_COLOR, 0.55),
            ),
            row=1,
            col=1,
        )

        for week, value in planned_totals:
            hour_bottom[week] = hour_bottom.get(week, 0.0) + value

    ceiling = max(
        _axis_ceiling(
            list(hour_bottom.values()),
            step=TIME_Y_STEP,
            floor=TIME_Y_MIN,
        ),
        _axis_ceiling(
            [
                getattr(point, attribute) * time_scale / 3600
                for point in time_points or []
                for attribute in ("base", "fitness")
            ],
            step=TIME_Y_STEP,
            floor=TIME_Y_MIN,
        ),
        _axis_ceiling(
            [
                getattr(point, attribute) * time_scale / 3600
                for point in hard_points or []
                for attribute in ("base", "fitness")
            ],
            step=TIME_Y_STEP,
            floor=TIME_Y_MIN,
        ),
    )

    if hard_points:
        # The minutes axis mirrors the hour axis instead of zooming to the
        # hard series: same range in minutes, ticks every 2 hours' worth, so
        # the lines and bars keep sharing one vertical scale.
        figure.update_layout({
            f"yaxis{hard_axis[1:]}": {
                "overlaying": "y",
                "side": "right",
                "anchor": "x",
                "title": {"text": "hard minutes / week"},
                "range": [0, ceiling * 60],
                "showgrid": False,
                "dtick": HARD_MINUTES_STEP,
            },
        })

    totals_by_week = dict(zip(week_dates, (
        actual_week_totals[w] for w in week_dates
    )))
    totals_by_week.update(hour_bottom)

    _clipped_markers(
        figure,
        list(totals_by_week.items()),
        ceiling,
        "h",
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
            scale=time_scale / 60,
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
            # No row/col: adding through a subplot would snap the trace back
            # to the row's primary axis.
            yaxis=hard_axis,
            projection_label="hard projection",
        )

    axis_weeks = sorted(
        set(week_dates if weeks else [])
        | set(planned_week_totals)
        | set(planned_time_by_week)
    )

    if axis_weeks:
        figure.update_xaxes(
            range=[
                axis_weeks[0],
                axis_weeks[-1] + timedelta(days=7),
            ]
        )

    if zone_points:
        actual_zone = [
            point for point in zone_points if not point.projected
        ]
        projected_zone = [
            point for point in zone_points if point.projected
        ]

        for index in reversed(range(zone_count)):
            line = {
                "color": ZONE_LINE_COLORS[
                    index % len(ZONE_LINE_COLORS)
                ],
                "width": 1.2,
            }

            if actual_zone:
                _add(
                    figure,
                    go.Scatter(
                        x=[point.date for point in actual_zone],
                        y=[
                            point.zones[index] * zone_scale / 3600
                            for point in actual_zone
                        ],
                        mode="lines",
                        name=f"Z{index + 1}",
                        stackgroup="one",
                        showlegend=False,
                        line=line,
                    ),
                    row=3,
                    col=1,
                )

            if projected_zone and actual_zone:
                bridge = actual_zone[-1:] + projected_zone
                _add(
                    figure,
                    go.Scatter(
                        x=[point.date for point in bridge],
                        y=[
                            point.zones[index] * zone_scale / 3600
                            for point in bridge
                        ],
                        mode="lines",
                        name=f"Z{index + 1}",
                        stackgroup="projected",
                        showlegend=False,
                        opacity=0.35,
                        line={**line, "dash": "dash"},
                    ),
                    row=3,
                    col=1,
                )

        if projected_zone and actual_zone:
            figure.add_vline(
                x=projected_zone[0].date,
                line_width=1,
                line_dash="dash",
                line_color="#7f7f7f",
                row=3,
                col=1,
            )

        figure.update_yaxes(
            title_text=ylabel,
            range=[0, ceiling],
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
        range=[0, ceiling],
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

    _crosshair(figure)

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
                        hoverinfo="skip",
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
                        name=f"{category} pace avg",
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
                    hoverinfo="skip",
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
                    name=f"{category} max HR",
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
                    name=f"{category} HR avg",
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
                name=f"{category} HR",
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

        # The rep range, like the pace panel's fastest/slowest sticks.
        for point in efficiency:
            if (
                point.lowest_efficiency is None
                or point.highest_efficiency is None
                or point.lowest_efficiency == point.highest_efficiency
            ):
                continue

            figure.add_trace(
                go.Scatter(
                    x=[point.date, point.date],
                    y=[
                        point.lowest_efficiency,
                        point.highest_efficiency,
                    ],
                    mode="lines",
                    line={"color": color, "width": 1.1},
                    opacity=0.35,
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=3,
                col=1,
            )

        figure.add_trace(
            go.Scatter(
                x=dates,
                y=[point.efficiency for point in efficiency],
                mode="markers",
                marker={"color": color, "size": 7},
                text=[
                    (
                        f"{point.date} {category}"
                        f"<br>E {point.efficiency:.2f} {EFFICIENCY_UNIT}"
                        + (
                            f", reps {point.lowest_efficiency:.2f}–"
                            f"{point.highest_efficiency:.2f}"
                            if point.lowest_efficiency is not None
                            and point.highest_efficiency is not None
                            else ""
                        )
                        + f", n={point.count}"
                    )
                    for point in efficiency
                ],
                hoverinfo="text",
                name=f"{category} efficiency",
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
                name=f"{category} efficiency avg",
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
    efficiency_range = _bulk_range(
        [
            value
            for point in points
            for value in (
                point.efficiency,
                point.lowest_efficiency,
                point.highest_efficiency,
            )
        ],
        step=0.1,
    )
    figure.update_yaxes(
        title_text="efficiency (m/excess beat, work reps)",
        range=efficiency_range,
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
    _crosshair(figure)

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
    *,
    planned_load: list[tuple[date, float]] | None = None,
    planned_cross_load: list[tuple[date, float]] | None = None,
    windows: AverageWindows | None = None,
    rpe_points: list[RpePoint] | None = None,
    load_scale: float = 7.0,
    title: str = "Weekly training load and session RPE",
    periods: list[TrainingPeriod] | None = None,
    as_html: bool = False,
) -> str:
    """Weekly load bars with weekly EWMA lines and session RPE on a right axis.

    Bars stack running and cross load for each Monday-to-Sunday week; the
    running-fitness averages are scaled to the same per-week units. Cross
    load is context: it does not feed the averages, because the lab found no
    positive transfer to running fitness. Planned load stacks on the current
    week's actual bars as faded, hatched bars.
    """
    _require_data(points)
    windows = windows or AverageWindows()
    actual = [point for point in points if not point.projected]

    weekly_run: dict[date, float] = {}
    weekly_cross: dict[date, float] = {}

    for point in actual:
        week = week_start(point.date)
        weekly_run[week] = weekly_run.get(week, 0.0) + point.load
        weekly_cross[week] = (
            weekly_cross.get(week, 0.0) + point.cross_load
        )

    actual_weeks = sorted(set(weekly_run) | set(weekly_cross))
    weekly_total = {
        week: weekly_run.get(week, 0.0) + weekly_cross.get(week, 0.0)
        for week in actual_weeks
    }
    planned_run: dict[date, float] = {}
    planned_cross: dict[date, float] = {}

    if planned_load or planned_cross_load:
        actual_days = {
            point.date
            for point in actual
            if point.load > 0 or point.cross_load > 0
        }

        for source, target in (
            (planned_load, planned_run),
            (planned_cross_load, planned_cross),
        ):
            for day, value in source or []:
                if day in actual_days:
                    continue
                week = week_start(day)
                target[week] = target.get(week, 0.0) + value

    planned_weeks = sorted(set(planned_run) | set(planned_cross))
    planned_run = {week: planned_run.get(week, 0.0) for week in planned_weeks}
    planned_cross = {
        week: planned_cross.get(week, 0.0) for week in planned_weeks
    }
    planned_marks = [
        (
            week,
            weekly_total.get(week, 0.0)
            + planned_run[week]
            + planned_cross[week],
        )
        for week in planned_weeks
    ]
    ceiling = max(
        _axis_ceiling(
            list(weekly_total.values())
            + [value for _, value in planned_marks],
            step=LOAD_WEEK_Y_STEP,
            floor=LOAD_WEEK_Y_MIN,
        ),
        _axis_ceiling(
            [
                getattr(point, attribute) * load_scale
                for point in points
                for attribute in ("base", "fitness")
            ],
            step=LOAD_WEEK_Y_STEP,
            floor=LOAD_WEEK_Y_MIN,
        ),
    )
    axis_weeks = sorted(set(actual_weeks) | set(planned_weeks))

    figure = go.Figure()

    if axis_weeks:
        _period_bands(
            figure,
            periods,
            kind="season",
            color=SEASON_BAND_COLOR,
            start=axis_weeks[0],
            end=axis_weeks[-1] + timedelta(days=7),
            bottom=0,
            top=ceiling,
            labels=True,
        )

    if any(weekly_run.values()):
        figure.add_bar(
            x=actual_weeks,
            y=[weekly_run.get(week, 0.0) for week in actual_weeks],
            name="running load",
            width=WEEK_MS,
            marker_color=LOAD_BAR_COLOR,
        )

    if any(weekly_cross.values()):
        figure.add_bar(
            x=actual_weeks,
            y=[weekly_cross.get(week, 0.0) for week in actual_weeks],
            base=[weekly_run.get(week, 0.0) for week in actual_weeks],
            name="cross load",
            width=WEEK_MS,
            marker_color=CROSS_LOAD_COLOR,
        )

    if planned_weeks:
        run_base = [weekly_total.get(week, 0.0) for week in planned_weeks]
        cross_base = list(run_base)

        if any(planned_run.values()):
            figure.add_bar(
                x=planned_weeks,
                y=[planned_run[week] for week in planned_weeks],
                # The current week already has actual bars; stack the plan
                # for its remaining days on top of them.
                base=run_base,
                name="planned run",
                width=WEEK_MS,
                marker={
                    "color": _fade(LOAD_BAR_COLOR, 0.45),
                    "line": {"color": "#9aa5b1", "width": 0.6},
                    "pattern": {
                        "shape": PLANNED_PATTERN,
                        "fgcolor": "#9aa5b1",
                        "solidity": 0.45,
                    },
                },
            )
            cross_base = [
                value + planned_run[week]
                for value, week in zip(run_base, planned_weeks)
            ]

        if any(planned_cross.values()):
            figure.add_bar(
                x=planned_weeks,
                y=[planned_cross[week] for week in planned_weeks],
                base=cross_base,
                name="planned cross",
                width=WEEK_MS,
                marker={
                    "color": _fade(CROSS_LOAD_COLOR, 0.45),
                    "line": {"color": "#9aa5b1", "width": 0.6},
                    "pattern": {
                        "shape": PLANNED_PATTERN,
                        "fgcolor": "#9aa5b1",
                        "solidity": 0.45,
                    },
                },
            )

    _plot_average_lines(
        figure,
        points,
        windows,
        scale=load_scale,
        label=lambda attribute, days: f"{attribute.title()} ({days}d)",
    )

    rpe = [point for point in rpe_points or [] if point.base is not None]
    rpe_windows = (("base", 182), ("fitness", 42), ("fatigue", 7))

    if rpe:
        # All halos go down before any line, as in the other charts.
        for attribute, window in rpe_windows:
            _outline(
                figure,
                [point.date for point in rpe],
                [getattr(point, attribute) for point in rpe],
                LINE_WIDTHS[window],
                yaxis="y2",
            )

        for attribute, window in rpe_windows:
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

    totals_by_week = dict(weekly_total)
    totals_by_week.update(planned_marks)
    _clipped_markers(
        figure,
        list(totals_by_week.items()),
        ceiling,
        "load",
    )
    figure.update_yaxes(range=[0, ceiling], dtick=LOAD_WEEK_Y_STEP)

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
        ylabel="load / week",
    )

    if rpe:
        highest = max(
            getattr(point, attribute)
            for point in rpe
            for attribute in ("base", "fitness", "fatigue")
        )
        figure.update_layout(
            yaxis2={
                "title": "RPE",
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
                "range": [0, float(max(RPE_AXIS_MIN, math.ceil(highest)))],
                "dtick": 1,
            },
        )

    _crosshair(figure, second_y=True)

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
            name="Running VO2max",
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
    _crosshair(figure)

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


PB_COLORS = {
    "5k": "#1f77b4",
    "10k": "#ff7f0e",
    "HM": "#2ca02c",
    "M": "#d62728",
}


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
                step.activity.duration_s,
                step.activity.distance_m,
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
                step.activity.duration_s,
                step.activity.distance_m,
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
                    f"{step.activity.date} {step.activity.name or bucket}"
                    f"<br>{step.activity.distance_m / 1000:.2f} km, "
                    f"{fmt_clock(step.activity.duration_s)}"
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
                    f"{step.activity.date} {step.activity.name or bucket}"
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
                step.activity.duration_s,
                step.activity.distance_m,
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
                        f"{step.activity.name or progression.bucket}"
                        f"<br>{step.activity.distance_m / 1000:.2f} km, "
                        f"{fmt_clock(step.activity.duration_s)}"
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
        reference = riegel_reference(results)
        low = min(point.activity.distance_m for point in points)
        high = max(point.activity.distance_m for point in points)

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
                    x=[race.distance_m / 1000],
                    y=[race.duration_s / 60],
                    mode="markers",
                    name="reference race",
                    marker={
                        "symbol": "circle-open",
                        "size": 17,
                        "line": {"color": "#111111", "width": 2},
                    },
                    text=[
                        f"{race.date} {race.name or reference.bucket}"
                        f"<br>{race.distance_m / 1000:.2f} km, "
                        f"{fmt_clock(race.duration_s)}"
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


def plot_equipment(
    stats: list[EquipmentStat],
    output: str,
    title: str = "Gear mileage by category",
    as_html: bool = False,
) -> str:
    """Horizontal mileage bars grouped and coloured by gear category."""
    _require_data(stats)
    groups = group_equipment(stats)
    colors_for = EQUIPMENT_CATEGORY_COLORS
    legend_rank = {"shoe": 1, "bike": 2, "other": 3}
    figure = go.Figure()

    # Add the groups in reverse so shoes sit at the top of the chart, while
    # legendrank keeps the legend in shoes/bikes/other order.
    for key, label, items in reversed(groups):
        ordered = list(reversed(items))
        color = colors_for[key]
        figure.add_bar(
            x=[stat.distance_m / 1000 for stat in ordered],
            y=[stat.label for stat in ordered],
            orientation="h",
            name=label,
            marker={
                "color": [
                    _fade(color, 0.35) if stat.retired else color
                    for stat in ordered
                ],
            },
            hovertemplate=(
                "%{y}<br>%{x:.0f} km<extra></extra>"
            ),
            legendrank=legend_rank[key],
        )

    targets = [stat for stat in stats if stat.target_distance_m]
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
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=1200,
    )


def plot_thresholds(
    thresholds: list[ThresholdPoint],
    races: list[RacePacePoint] | None = None,
    output: str = "",
    *,
    today: date | None = None,
    title: str = "Threshold and official race pace",
    as_html: bool = False,
) -> str:
    """Run LTHR/max-HR snapshots with threshold and race pace on the right."""
    _require_data(thresholds, races)
    today = today or date.today()
    snapshots = sorted(thresholds, key=lambda point: point.date)
    races = sorted(races or [], key=lambda point: point.date)
    figure = go.Figure()

    def series(getter):
        values = [
            (point.date, getter(point))
            for point in snapshots
            if getter(point) is not None
        ]

        if values and values[-1][0] < today:
            values.append((today, values[-1][1]))

        return values

    lthr = series(lambda point: point.lthr)
    max_hr = series(lambda point: point.max_hr)
    pace = series(lambda point: point.pace_s_per_km)

    for values, name, color, dash in (
        (lthr, "LTHR", "#d62728", "solid"),
        (max_hr, "Max HR", "#1f77b4", "dash"),
    ):
        if not values:
            continue

        figure.add_trace(
            go.Scatter(
                x=[day for day, _ in values],
                y=[value for _, value in values],
                mode="lines+markers",
                name=name,
                line={
                    "color": color,
                    "width": 2,
                    "shape": "hv",
                    "dash": dash,
                },
                marker={"size": 5, "color": color},
            )
        )

    if pace:
        figure.add_trace(
            go.Scatter(
                x=[day for day, _ in pace],
                y=[value for _, value in pace],
                mode="lines+markers",
                name="Threshold pace",
                yaxis="y2",
                line={
                    "color": "#2ca02c",
                    "width": 2,
                    "shape": "hv",
                },
                marker={"size": 5, "color": "#2ca02c"},
                customdata=[format_pace(value) for _, value in pace],
                hovertemplate="%{x}<br>%{customdata}<extra></extra>",
            )
        )

    if races:
        figure.add_trace(
            go.Scatter(
                x=[point.date for point in races],
                y=[point.pace_s_per_km for point in races],
                mode="markers",
                name="Official race pace",
                yaxis="y2",
                marker={
                    "symbol": "diamond",
                    "size": 9,
                    "color": "#9467bd",
                    "line": {"color": "#222222", "width": 1},
                },
                text=[
                    f"{point.name} ({point.distance_m / 1000:.1f} km)"
                    for point in races
                ],
                customdata=[
                    format_pace(point.pace_s_per_km)
                    for point in races
                ],
                hovertemplate=(
                    "%{x}<br>%{text}<br>%{customdata}<extra></extra>"
                ),
            )
        )

    hr_values = [
        value
        for values in (lthr, max_hr)
        for _, value in values
    ]

    if hr_values:
        figure.update_yaxes(
            title_text="heart rate (bpm)",
            range=[min(hr_values) - 5, max(hr_values) + 5],
            dtick=10,
        )
    else:
        figure.update_yaxes(title_text="heart rate (bpm)")

    figure.update_xaxes(title_text="date")

    if pace:
        pace_values = [value for _, value in pace]
        low = min(pace_values) - 8
        high = max(pace_values) + 8

        if races:
            race_values = [point.pace_s_per_km for point in races]
            low = min(low, min(race_values) - 8)
            high = max(high, max(race_values) + 8)

        ticks = [
            value
            for value in range(
                int(low // 10 * 10),
                int(high) + 11,
                10,
            )
        ]
        figure.update_layout(
            yaxis2={
                "title": "pace (min/km)",
                "overlaying": "y",
                "side": "right",
                "range": [high, low],
                "tickvals": ticks,
                "ticktext": [format_pace(value) for value in ticks],
                "showgrid": False,
            },
        )

    figure.update_layout(
        template="plotly_white",
        title=title,
        height=900,
        margin={"l": 60, "r": 70, "t": 70, "b": 110},
        legend=_legend_below(),
        hovermode="x unified",
    )
    _crosshair(figure, second_y=True)

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


def _outline(
    figure,
    x: list,
    y: list,
    width: float,
    *,
    row: int | None = None,
    col: int | None = None,
    yaxis: str | None = None,
) -> None:
    """A pale halo under an EWMA line so it reads over the bars."""
    _add(
        figure,
        go.Scatter(
            x=x,
            y=y,
            mode="lines",
            line={"color": "rgba(255, 255, 255, 0.85)", "width": width + 2.5},
            hoverinfo="skip",
            showlegend=False,
            yaxis=yaxis,
        ),
        row=row,
        col=col,
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
