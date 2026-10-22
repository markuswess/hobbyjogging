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
    ax.legend(
        loc="best",
        fontsize=9,
        title=f"dots = sessions; lines = {window}-session rolling mean",
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
    """Scatter + rolling mean of work paces, color-coded by session type."""
    return _plot_subt_metric(
        points,
        output,
        value=lambda p: p.pace_s_per_km,
        ylabel="pace (min/km)",
        title=title,
        window=window,
        invert_yaxis=True,
        tick_formatter=FuncFormatter(_pace_tick),
    )


def plot_subt_hr(
    points: list[SubtPoint],
    output: str,
    window: int = 5,
    title: str = "subT and LT1 work interval heart rate",
) -> str:
    """Scatter + rolling mean of work-interval HR, by session type."""
    return _plot_subt_metric(
        points,
        output,
        value=lambda p: p.avg_hr,
        ylabel="heart rate (bpm)",
        title=title,
        window=window,
    )
