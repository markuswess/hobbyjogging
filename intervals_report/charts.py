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


def plot_subt_paces(
    points: list[SubtPoint],
    output: str,
    window: int = 5,
    title: str = "subT work interval pace",
) -> str:
    """Scatter + rolling mean of subT paces, one panel per category."""
    if not points:
        raise ValueError("no data to plot")

    fig, axes = plt.subplots(
        3, 1,
        figsize=(10, 9),
        sharex=True,
    )

    for ax, category in zip(axes, SUBT_CATEGORIES):
        data = sorted(
            (p for p in points if p.category == category),
            key=lambda p: p.date,
        )

        ax.set_title(f"{category} ({len(data)} sessions)")
        ax.grid(True, alpha=0.3)
        ax.set_ylabel("pace (min/km)")

        if not data:
            ax.text(
                0.5, 0.5, "no data",
                transform=ax.transAxes,
                ha="center", va="center",
            )
            ax.set_yticks([])
            continue

        dates = [p.date for p in data]
        paces = [p.pace_s_per_km for p in data]

        ax.scatter(dates, paces, s=30, label="session")

        if len(data) >= 2:
            ax.plot(
                dates,
                _rolling_mean(paces, window),
                color="tab:orange",
                label=f"rolling mean ({window})",
            )

        # Faster paces (lower seconds/km) point upwards.
        ax.invert_yaxis()
        ax.yaxis.set_major_formatter(FuncFormatter(_pace_tick))
        ax.legend(loc="best", fontsize=8)

    axes[-1].set_xlabel("date")
    fig.suptitle(title)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)

    return output
