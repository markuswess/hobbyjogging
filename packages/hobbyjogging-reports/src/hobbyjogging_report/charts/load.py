"""Weekly load and running-fitness charts."""

from __future__ import annotations

from datetime import date, timedelta
import math

import plotly.graph_objects as go

from hobbyjogging_core.model import TrainingPeriod

from ..analysis import week_start
from ..model import AverageWindows, LoadPoint, RpePoint
from ..style import (
    LINE_STYLES,
    LINE_WIDTHS,
    LOAD_WEEK_Y_MIN,
    LOAD_WEEK_Y_STEP,
    PLANNED_PATTERN,
    RPE_AXIS_MIN,
    RPE_LINE_COLORS,
    SEASON_BAND_COLOR,
    SEASON_START_COLOR,
)

from .common import (
    CROSS_LOAD_COLOR,
    LOAD_BAR_COLOR,
    WEEK_MS,
    _axis_ceiling,
    _base_layout,
    _clipped_markers,
    _crosshair,
    _fade,
    _outline,
    _period_bands,
    _plot_average_lines,
    _render,
    _require_data,
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
            mark_start=True,
            start_color=SEASON_START_COLOR,
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
