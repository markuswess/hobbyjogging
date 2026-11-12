"""Recovery report: 7/42/182-day moving averages of wellness metrics."""

from __future__ import annotations

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import WellnessDay

from .analysis import BASELINE_WINDOW_DAYS, RobustBaseline, robust_baseline
from .analysis.recovery import MIN_BASELINE_VALUES
from .format import format_nights

WINDOWS = (7, 42, 182)


def _window_mean(
    wellness: list[WellnessDay],
    day: date,
    window_days: int,
    attribute: str,
) -> float | None:
    """Mean of the measured values in the trailing calendar window."""
    cutoff = day - timedelta(days=window_days - 1)
    values = [
        value
        for other in wellness
        if cutoff <= other.date <= day
        and (value := getattr(other, attribute)) is not None
    ]

    return sum(values) / len(values) if values else None


def _hrv(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f} ms"


def _rhr(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f} bpm"


def _sleep(value: float | None) -> str:
    return "-" if value is None else f"{value / 3600:.1f} h"


def recovery_averages(
    wellness: list[WellnessDay],
    today: date,
) -> dict[str, dict[int, float | None]]:
    """Moving averages ending today for each wellness metric."""
    return {
        "HRV": {
            window: _window_mean(wellness, today, window, "hrv")
            for window in WINDOWS
        },
        "Resting HR": {
            window: _window_mean(wellness, today, window, "resting_hr")
            for window in WINDOWS
        },
        "Sleep": {
            window: _window_mean(wellness, today, window, "sleep_s")
            for window in WINDOWS
        },
    }


def recovery_baselines(
    wellness: list[WellnessDay],
    today: date,
) -> dict[str, RobustBaseline | None]:
    """Robust 365-day baselines used by the recovery chart bands.

    Sleep has no baseline: its bands are absolute.
    """
    return {
        "HRV": robust_baseline(
            ((day.date, day.hrv) for day in wellness),
            today,
            window_days=BASELINE_WINDOW_DAYS,
            min_values=MIN_BASELINE_VALUES,
        ),
        "Resting HR": robust_baseline(
            ((day.date, day.resting_hr) for day in wellness),
            today,
            window_days=BASELINE_WINDOW_DAYS,
            min_values=MIN_BASELINE_VALUES,
        ),
        "Sleep": None,
    }


def _baseline_cell(
    label: str,
    baseline: RobustBaseline | None,
) -> str:
    if label == "Sleep":
        return "7–9 h (absolute)"

    if baseline is None:
        return "-"

    unit = "ms" if label == "HRV" else "bpm"

    return (
        f"{baseline.center:.0f} ± {baseline.spread:.1f} {unit}"
    )


def recovery_report(
    source: DataSource,
    *,
    today: date | None = None,
) -> str:
    """Render the 7/42/182-day recovery moving averages as Markdown."""
    today = today or date.today()
    recent_start = today - timedelta(days=WINDOWS[-1] - 1)
    start = today - timedelta(days=BASELINE_WINDOW_DAYS - 1)
    wellness = source.wellness(start, today)
    table = recovery_averages(wellness, today)
    baselines = recovery_baselines(wellness, today)

    lines = [
        "# Recovery Report — Moving Averages",
        f"7/42/182-day averages ending {today}",
    ]

    if not any(day.date >= recent_start for day in wellness):
        lines.extend([
            "",
            f"- No wellness data in the last {WINDOWS[-1]} days.",
        ])
        return "\n".join(lines)

    lines.extend([
        "",
        "| Metric | 7-day avg | 42-day avg | 182-day avg | "
        "365-day baseline |",
        "|---|---:|---:|---:|---:|",
    ])

    formatters = {
        "HRV": _hrv,
        "Resting HR": _rhr,
        "Sleep": _sleep,
    }

    for label, values in table.items():
        cells = " | ".join(
            formatters[label](values[window]) for window in WINDOWS
        )
        baseline = _baseline_cell(label, baselines[label])
        lines.append(f"| {label} | {cells} | {baseline} |")

    lines.extend([
        "",
        "Simple calendar-day averages over the last 7, 42, and 182 days; "
        "missing days are skipped, not treated as zero.",
        "",
        "The baseline is the robust 365-day median ± 1.4826 × MAD used by "
        "the recovery chart bands. Sleep has no baseline: its bands are "
        "absolute (7–9 h green).",
    ])
    lines.extend(format_nights(wellness))

    return "\n".join(lines)
