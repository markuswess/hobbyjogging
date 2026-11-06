"""Plotting helpers (matplotlib).

Charts consume plain analysis output only. They know nothing about the data
source, so they keep working when the source is swapped.
"""

from collections import defaultdict
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from .analysis import SUBT_CATEGORIES
from .format import format_pace
from .model import (
    DistancePoint,
    LoadPoint,
    AverageWindows,
    RecoveryPoint,
    SubtPoint,
    TimePoint,
    TimeZoneWeek,
    ZoneAveragePoint,
)
from .series import sma

AVERAGE_COLORS = {
    "base": "tab:blue",
    "fitness": "tab:orange",
    "fatigue": "tab:red",
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
UNZONED_COLOR = "#d9d9d9"


def _style_week_axis(ax, weeks: list[date]) -> None:
    """Align weekly bars to Monday–Sunday and label Mondays."""
    if not weeks:
        return

    ax.set_xlim(
        min(weeks),
        max(weeks) + timedelta(days=7),
    )
    interval = max(1, len(weeks) // 12)
    ax.xaxis.set_major_locator(
        mdates.WeekdayLocator(
            byweekday=mdates.MO,
            interval=interval,
        )
    )


def _require_data(*series) -> None:
    if not any(series):
        raise ValueError("no data to plot")


def _save(fig, output: str) -> str:
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)
    return output


def _weekly_bars(
    ax,
    weeks: list[date],
    values: list[float],
    *,
    color,
    label: str,
    bottom: list[float] | None = None,
    edge_width: float = 0.5,
) -> None:
    ax.bar(
        weeks,
        values,
        width=7,
        align="edge",
        bottom=bottom if bottom is not None else 0,
        color=color,
        edgecolor="white",
        linewidth=edge_width,
        label=label,
        zorder=1,
    )


def _planned_week_lines(ax, weeks, *, label: str) -> None:
    """Draw one dashed target line per planned week."""
    for index, (week, value) in enumerate(weeks):
        ax.plot(
            [week, week + timedelta(days=7)],
            [value, value],
            color="black",
            linestyle="--",
            linewidth=1.5,
            alpha=0.75,
            label=label if index == 0 else None,
            zorder=3,
        )


def _planned_bars(ax, values, *, label: str) -> None:
    """Draw outlined bars for planned totals on top of the actual bars."""
    ax.bar(
        [day for day, _ in values],
        [value for _, value in values],
        width=7,
        align="edge",
        facecolor="none",
        edgecolor="black",
        linestyle="--",
        linewidth=1.4,
        alpha=0.8,
        label=label,
        zorder=4,
    )


def _planned_rug(ax, dates: list[date], *, label: str = "planned") -> None:
    """Mark planned sessions along the bottom of an axis."""
    if not dates:
        return

    levels: dict[date, int] = defaultdict(int)

    for day in sorted(dates):
        level = levels[day]
        levels[day] += 1
        ax.vlines(
            day,
            0.01 + level * 0.03,
            0.05 + level * 0.03,
            transform=ax.get_xaxis_transform(),
            color="black",
            linewidth=2,
            alpha=0.7,
            zorder=4,
        )

    # Add a legend handle without inventing a visible data point.
    ax.plot([], [], color="black", linewidth=2, alpha=0.7, label=label)


def _plot_average_lines(ax, points, windows, *, scale: float = 1.0, label):
    dates = [point.date for point in points]

    for attribute in ("base", "fitness", "fatigue"):
        ax.plot(
            dates,
            [getattr(point, attribute) * scale for point in points],
            color=AVERAGE_COLORS[attribute],
            linewidth=2,
            label=label(attribute, getattr(windows, attribute)),
            zorder=2,
        )


def _finish_week_axis(
    fig,
    ax,
    *,
    title: str,
    ylabel: str,
    legend_fontsize: int = 9,
) -> None:
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=legend_fontsize)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()


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
) -> str:
    """Weekly running volume bars with distance-average lines.

    Daily distance averages are multiplied by ``distance_scale`` (default 7)
    so they are directly comparable to the weekly bars. Planned weekly
    distance is drawn as a dashed target line.
    """
    _require_data(data, distance_points)

    windows = windows or AverageWindows()
    fig, ax = plt.subplots(figsize=(12, 5))
    weeks = [week for week, _ in data]

    if data:
        values = [value for _, value in data]
        _weekly_bars(
            ax,
            weeks,
            values,
            color="lightgrey",
            label="weekly km",
            edge_width=0.8,
        )

    if planned_distance:
        _planned_week_lines(ax, planned_distance, label="planned km")

    if distance_points:
        _plot_average_lines(
            ax,
            distance_points,
            windows,
            scale=distance_scale,
            label=lambda attribute, days: f"{days}d avg (weekly)",
        )

    axis_weeks = sorted(
        set(weeks) | {week for week, _ in planned_distance or []}
    )

    if axis_weeks:
        _style_week_axis(ax, axis_weeks)

    ax.set_xlabel("week starting (Monday)")
    _finish_week_axis(fig, ax, title=title, ylabel=ylabel)
    return _save(fig, output)


def plot_time(
    weeks: list[TimeZoneWeek],
    output: str,
    *,
    time_points: list[TimePoint] | None = None,
    planned_time: list[tuple[date, float]] | None = None,
    zone_points: list[ZoneAveragePoint] | None = None,
    zone_window_days: int | None = None,
    windows: AverageWindows | None = None,
    time_scale: float = 7.0,
    zone_scale: float = 7.0,
    ylabel: str = "hours / week",
    title: str = "Weekly running time",
) -> str:
    """Weekly running time stacked by HR zone with zone EWMA lines.

    Planned weekly time is drawn as an outlined bar over the actual stack.
    """
    _require_data(weeks, time_points)

    windows = windows or AverageWindows()
    zone_count = (
        len(weeks[0].zones)
        if weeks
        else len(zone_points[0].zones) if zone_points else 0
    )

    if zone_points:
        fig, (ax, zone_ax) = plt.subplots(
            2,
            1,
            sharex=True,
            figsize=(12, 8),
            gridspec_kw={"height_ratios": [3, 2]},
        )
    else:
        fig, ax = plt.subplots(figsize=(12, 5))
        zone_ax = None

    if weeks:
        week_dates = [week.week for week in weeks]
        bottoms = [0.0] * len(weeks)

        for index in range(zone_count):
            values = [
                week.zones[index] / 3600
                for week in weeks
            ]
            _weekly_bars(
                ax,
                week_dates,
                values,
                color=ZONE_COLORS[index % len(ZONE_COLORS)],
                label=f"Z{index + 1}",
                bottom=bottoms,
            )
            bottoms = [
                bottom + value
                for bottom, value in zip(bottoms, values)
            ]

        unzoned = [week.unzoned / 3600 for week in weeks]

        if any(unzoned):
            _weekly_bars(
                ax,
                week_dates,
                unzoned,
                color=UNZONED_COLOR,
                label="Unzoned",
                bottom=bottoms,
            )

    if planned_time:
        _planned_bars(
            ax,
            [(week, seconds / 3600) for week, seconds in planned_time],
            label="planned",
        )

    axis_weeks = sorted(
        set(week_dates if weeks else [])
        | {week for week, _ in planned_time or []}
    )

    if axis_weeks:
        _style_week_axis(ax, axis_weeks)

    if time_points:
        _plot_average_lines(
            ax,
            time_points,
            windows,
            scale=time_scale / 3600,
            label=lambda attribute, days: f"{days}d avg (weekly)",
        )

    _finish_week_axis(fig, ax, title=title, ylabel=ylabel, legend_fontsize=8)

    if zone_ax is not None and zone_points:
        zone_dates = [point.date for point in zone_points]
        lower = [0.0] * len(zone_points)

        for index in range(zone_count - 1, -1, -1):
            values = [
                point.zones[index] * zone_scale / 3600
                for point in zone_points
            ]
            upper = [
                low + value
                for low, value in zip(lower, values)
            ]
            label = "+".join(
                f"Z{zone + 1}"
                for zone in range(index, zone_count)
            )

            zone_ax.fill_between(
                zone_dates,
                lower,
                upper,
                color=ZONE_COLORS[index % len(ZONE_COLORS)],
                alpha=0.65,
                linewidth=0,
            )
            zone_ax.plot(
                zone_dates,
                upper,
                color=ZONE_LINE_COLORS[index % len(ZONE_LINE_COLORS)],
                linewidth=1.8,
                label=label,
            )
            lower = upper

        if zone_window_days:
            zone_ax.set_title(
                f"{zone_window_days}-day EWMA stacked by zone",
                fontsize=10,
            )

        zone_ax.set_ylabel(ylabel)
        zone_ax.set_xlabel("week starting (Monday)")
        zone_ax.grid(True, alpha=0.3)
        zone_ax.legend(
            loc="best",
            fontsize=8,
            ncol=min(zone_count, 4),
        )
    elif zone_ax is not None:
        zone_ax.set_visible(False)

    if zone_ax is None:
        ax.set_xlabel("week starting (Monday)")

    return _save(fig, output)


def _pace_tick(seconds, _position):
    return format_pace(seconds)


SUBT_COLORS = {
    "short": "tab:blue",
    "medium": "tab:orange",
    "long": "tab:green",
    "lt1": "tab:purple",
}

CHART_CATEGORIES = (*SUBT_CATEGORIES, "lt1")


def _plot_subt_metric(
    points: list[SubtPoint],
    output: str,
    value,
    ylabel: str,
    title: str,
    window: int = 5,
    invert_yaxis: bool = False,
    tick_formatter=None,
    range_values=None,
    range_label: str | None = None,
    range_caps_both: bool = False,
) -> str:
    """Scatter + rolling mean of one work-interval metric."""
    _require_data(points)

    fig, ax = plt.subplots(figsize=(10, 6))
    plotted = False

    for category in CHART_CATEGORIES:
        data = sorted(
            (
                p for p in points
                if p.category == category and value(p) is not None
            ),
            key=lambda p: p.date,
        )

        if not data:
            continue

        plotted = True
        color = SUBT_COLORS[category]
        dates = [p.date for p in data]
        values = [value(p) for p in data]

        if range_values is not None:
            bands = []

            for point in data:
                band = range_values(point)
                if band is None:
                    continue

                low, high = band
                if low is not None and high is not None:
                    bands.append((point.date, low, high))

            if bands:
                ax.vlines(
                    [d for d, _, _ in bands],
                    [lo for _, lo, _ in bands],
                    [hi for _, _, hi in bands],
                    color=color,
                    alpha=0.35,
                    linewidth=1.2,
                    zorder=1,
                )
                ax.scatter(
                    [d for d, _, _ in bands],
                    [hi for _, _, hi in bands],
                    marker="_",
                    s=55,
                    color=color,
                    linewidths=1.5,
                    zorder=2,
                )

                if range_caps_both:
                    ax.scatter(
                        [d for d, _, _ in bands],
                        [lo for _, lo, _ in bands],
                        marker="_",
                        s=55,
                        color=color,
                        linewidths=1.5,
                        zorder=2,
                    )

        if len(data) >= 2:
            ax.plot(
                dates,
                sma(values, window),
                color=color,
                alpha=0.55,
                linewidth=1.8,
                zorder=2,
            )

        ax.scatter(
            dates,
            values,
            s=30,
            color=color,
            label=f"{category} ({len(data)})",
            zorder=3,
        )

    if not plotted:
        raise ValueError("no data to plot")

    if invert_yaxis:
        # Faster paces (lower seconds/km) point upwards.
        ax.invert_yaxis()

    if tick_formatter is not None:
        ax.yaxis.set_major_formatter(tick_formatter)

    ax.set_xlabel("date")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    legend_title = (
        f"dots = sessions; lines = {window}-session rolling mean"
    )
    if range_label:
        legend_title += f"\nvertical lines = {range_label}"

    ax.legend(
        loc="best",
        fontsize=9,
        title=legend_title,
        title_fontsize=8,
    )

    fig.autofmt_xdate()
    return _save(fig, output)


def plot_subt_paces(
    points: list[SubtPoint],
    output: str,
    window: int = 5,
    title: str = "subT and LT1 work interval pace",
) -> str:
    """Average pace scatter with fastest–slowest ranges, by session type."""
    return _plot_subt_metric(
        points,
        output,
        value=lambda p: p.pace_s_per_km,
        ylabel="pace (min/km)",
        title=title,
        window=window,
        invert_yaxis=True,
        tick_formatter=FuncFormatter(_pace_tick),
        range_values=lambda p: (
            p.fastest_pace_s_per_km,
            p.slowest_pace_s_per_km,
        ),
        range_label="fastest–slowest",
        range_caps_both=True,
    )


def plot_subt_hr(
    points: list[SubtPoint],
    output: str,
    window: int = 5,
    title: str = "subT and LT1 work interval heart rate",
) -> str:
    """Average HR scatter with max-HR ranges, by session type."""
    return _plot_subt_metric(
        points,
        output,
        value=lambda p: p.avg_hr,
        ylabel="heart rate (bpm)",
        title=title,
        window=window,
        range_values=lambda p: (
            p.avg_hr,
            p.max_hr,
        ),
        range_label="max HR",
    )


def plot_load(
    points: list[LoadPoint],
    output: str,
    planned_load: list[tuple[date, float]] | None = None,
    windows: AverageWindows | None = None,
    title: str = "Training load",
) -> str:
    """Daily load bars with base, fitness, and fatigue EWMA lines.

    Planned daily load is drawn as an outlined bar over the actual bar.
    """
    _require_data(points)

    windows = windows or AverageWindows()
    dates = [point.date for point in points]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(
        dates,
        [point.load for point in points],
        color="lightgrey",
        alpha=0.6,
        label="daily load",
        zorder=1,
    )

    if planned_load:
        ax.bar(
            [day for day, _ in planned_load],
            [load for _, load in planned_load],
            facecolor="none",
            edgecolor="black",
            linestyle="--",
            linewidth=1.2,
            alpha=0.8,
            label="planned",
            zorder=4,
        )

    _plot_average_lines(
        ax,
        points,
        windows,
        label=lambda attribute, days: f"{attribute.title()} ({days}d)",
    )

    ax.set_xlabel("date")
    ax.set_ylabel("training load")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.autofmt_xdate()
    return _save(fig, output)


def plot_recovery(
    points: list[RecoveryPoint],
    output: str,
    planned_dates: list[date] | None = None,
    window_days: int = 7,
    title: str = "Recovery trends",
) -> str:
    """Plot HRV, resting HR, and sleep with rolling averages.

    Planned workouts are marked along the bottom of the sleep panel.
    """
    _require_data(points)

    metrics = (
        ("hrv", "hrv_avg", "HRV", "ms", 1.0, "tab:blue"),
        (
            "resting_hr",
            "resting_hr_avg",
            "Resting HR",
            "bpm",
            1.0,
            "tab:red",
        ),
        (
            "sleep_s",
            "sleep_avg",
            "Sleep",
            "hours",
            1 / 3600,
            "tab:purple",
        ),
    )

    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(12, 9))

    for ax, (
        raw_attr,
        average_attr,
        label,
        unit,
        scale,
        color,
    ) in zip(axes, metrics):
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
            ax.scatter(
                [day for day, _ in raw],
                [value for _, value in raw],
                s=14,
                color=color,
                alpha=0.45,
                label="daily",
                zorder=2,
            )

        if average:
            ax.plot(
                [day for day, _ in average],
                [value for _, value in average],
                color=color,
                linewidth=2,
                label=f"{window_days}-day avg",
                zorder=3,
            )

        if raw or average:
            ax.legend(loc="best", fontsize=8)
        else:
            ax.text(
                0.5,
                0.5,
                "No data",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )

        ax.set_ylabel(f"{label} ({unit})")
        ax.grid(True, alpha=0.3)

    if planned_dates:
        _planned_rug(axes[-1], planned_dates)
        axes[-1].legend(loc="best", fontsize=8)

    axes[0].set_title(title)
    axes[-1].set_xlabel("date")
    fig.autofmt_xdate()
    return _save(fig, output)
