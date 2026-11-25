"""Gear, threshold and recording-device charts."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go

from ..analysis import (
    DeviceStat,
    EquipmentStat,
    group_equipment,
    RacePacePoint,
    ThresholdPoint,
)
from ..format import format_pace
from ..style import EQUIPMENT_CATEGORY_COLORS

from .common import (
    _crosshair,
    _fade,
    _legend_below,
    _render,
    _require_data,
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

        sixty = [
            point
            for point in races
            if point.pace_60_s_per_km is not None
        ]

        if sixty:
            figure.add_trace(
                go.Scatter(
                    x=[point.date for point in sixty],
                    y=[point.pace_60_s_per_km for point in sixty],
                    mode="markers",
                    name="Race 60 min pace",
                    yaxis="y2",
                    marker={
                        "symbol": "circle-open",
                        "size": 9,
                        "color": "#9467bd",
                        "line": {"color": "#9467bd", "width": 2},
                    },
                    text=[
                        f"{point.name} "
                        f"({point.distance_m / 1000:.1f} km)"
                        for point in sixty
                    ],
                    customdata=[
                        format_pace(point.pace_60_s_per_km)
                        for point in sixty
                    ],
                    hovertemplate=(
                        "%{x}<br>%{text}<br>60 min "
                        "%{customdata}<extra></extra>"
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
            race_values += [
                point.pace_60_s_per_km
                for point in races
                if point.pace_60_s_per_km is not None
            ]
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


def plot_devices(
    stats: list[DeviceStat],
    output: str,
    title: str = "Device timeline",
    as_html: bool = False,
) -> str:
    """Horizontal timelines for the recording devices and their activity counts."""
    _require_data(stats)
    figure = go.Figure()

    for stat in stats:
        start = stat.start or stat.first_used
        end = stat.end or stat.last_used

        if start is None:
            continue
        if end is None or end < start:
            end = start

        period = (
            f"{start} → {end}" if start != end else str(start)
        )
        figure.add_trace(
            go.Scatter(
                x=[start, end],
                y=[stat.label, stat.label],
                mode="lines+markers",
                line={"width": 12, "color": "#1f77b4"},
                marker={"size": 6},
                showlegend=False,
                text=[period, period],
                customdata=[
                    f"{stat.activities} activities · {stat.device.id}"
                ] * 2,
                hovertemplate=(
                    "%{y}<br>%{text}<br>%{customdata}<extra></extra>"
                ),
            )
        )

    figure.update_xaxes(title_text="date")
    figure.update_layout(
        template="plotly_white",
        title=title,
        height=max(350, 70 * len(stats) + 180),
        margin={"l": 60, "r": 30, "t": 70, "b": 100},
        hovermode="closest",
    )
    _crosshair(figure)

    return _render(
        figure,
        output,
        as_html=as_html,
        width=1650,
        height=900,
    )
