"""Plotting helpers (matplotlib).

Charts consume plain analysis output only. They know nothing about the data
source, so they keep working when the source is swapped.
"""

from datetime import date

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from .analysis import SUBT_CATEGORIES
from .model import SubtPoint


def plot_weekly_bars(
    data: list[tuple[date, float]],
    ylabel: str,
    output: str,
    title: str = "",
) -> str:
    """Bar chart of weekly values, saved to ``output``. Returns the path."""
    if not data:
        raise ValueError("no data to plot")

    weeks = [week for week, _ in data]
    values = [value for _, value in data]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(weeks, values, width=5)
    ax.set_title(title or ylabel)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("week starting")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)

    return output


def _rolling_mean(values: list[float], window: int) -> list[float]:
    """Trailing rolling mean (includes the current value)."""
    result = []

    for i in range(len(values)):
        chunk = values[max(0, i - window + 1): i + 1]
        result.append(sum(chunk) / len(chunk))

    return result


def _pace_tick(seconds, _position):
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


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
    if not points:
        raise ValueError("no data to plot")

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
                _rolling_mean(values, window),
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
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)

    return output


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
