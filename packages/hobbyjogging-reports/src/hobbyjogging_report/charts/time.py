"""Weekly time and zone-share charts."""

from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..model import AverageWindows, TimePoint, TimeZoneWeek, ZoneAveragePoint
from ..style import (
    HARD_LINE_COLORS,
    LINE_STYLES,
    HARD_MINUTES_STEP,
    TIME_Y_MIN,
    TIME_Y_STEP,
    TOTAL_LINE_COLORS,
    UNZONED_COLOR,
)

from .common import (
    VOLUME_BAR_COLOR,
    WEEK_MS,
    ZONE_COLORS,
    ZONE_LINE_COLORS,
    _add,
    _axis_ceiling,
    _clipped_markers,
    _crosshair,
    _fade,
    _legend_below,
    _plot_average_lines,
    _render,
    _require_data,
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
