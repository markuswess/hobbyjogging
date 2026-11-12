"""Wellness recovery trends and readiness bands.

Bands use a robust 365-day baseline (median centre, 1.4826 x MAD spread)
computed at the end of the displayed range. Both failure modes matter:

- A short window slowly becomes a long illness. In March 2026 the 42-day
  RHR mean was 58.4 because the window was full of elevated values, so an
  RHR of 58 read green; the one-year median of 51 flags it red.
- A short window also collapses when the athlete is stable. In November
  2026 the 42-day SD was 1.5, so a 2 bpm rise read red; the one-year band
  (median 50, spread ~3) calls the same rise amber.

The trade-off is a slow adaptation to a genuinely new normal. That is the
right bias for a readiness flag: a false all-clear is worse than a slow
adjustment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hobbyjogging_core.model import WellnessDay

from ..model import RecoveryPoint
from ..series import rolling_mean_by_date
from .baseline import BASELINE_WINDOW_DAYS, robust_baseline

# Bands compare a year of wellness: a short window becomes a long illness
# and collapses to a hair-trigger band when the athlete is stable.
BASELINE_DAYS = BASELINE_WINDOW_DAYS
MIN_BASELINE_VALUES = 7

SLEEP_NORMAL = (7 * 3600, 9 * 3600)
SLEEP_WATCH = ((6 * 3600, 7 * 3600), (9 * 3600, 10 * 3600))


@dataclass(frozen=True)
class RecoveryBand:
    """One horizontal readiness band in a metric's native units."""

    level: str
    low: float | None
    high: float | None


@dataclass(frozen=True)
class RecoveryBands:
    """Readiness bands for the three recovery metrics."""

    hrv: tuple[RecoveryBand, ...] = ()
    resting_hr: tuple[RecoveryBand, ...] = ()
    sleep_s: tuple[RecoveryBand, ...] = ()


def _baseline(
    points: list[RecoveryPoint],
    attribute: str,
    day: date,
):
    """Return the robust year-long baseline, or ``None``."""
    return robust_baseline(
        (
            (point.date, getattr(point, attribute))
            for point in points
        ),
        day,
        window_days=BASELINE_DAYS,
        min_values=MIN_BASELINE_VALUES,
    )


def recovery_bands(points: list[RecoveryPoint]) -> RecoveryBands:
    """Readiness bands relative to a robust year-long baseline.

    The center is the 365-day median and the spread is 1.4826 x MAD, so an
    illness cannot become the baseline and a stable period does not produce
    a hair-trigger band. HRV is green at or above its center, amber down to
    one spread below, and red below that. Resting HR mirrors it (lower is
    better). Sleep is absolute: green 7-9 h, amber 6-7 h or 9-10 h, red
    outside that.

    One band set is computed at the end of the displayed range: the window
    defines the current normal.
    """
    if not points:
        return RecoveryBands()

    bands = RecoveryBands()
    last_day = max(point.date for point in points)
    hrv = _baseline(points, "hrv", last_day)

    if hrv is not None:
        bands = RecoveryBands(
            hrv=(
                RecoveryBand("normal", hrv.center, None),
                RecoveryBand("watch", hrv.center - hrv.spread, hrv.center),
                RecoveryBand("alert", None, hrv.center - hrv.spread),
            ),
            resting_hr=bands.resting_hr,
            sleep_s=bands.sleep_s,
        )

    rhr = _baseline(points, "resting_hr", last_day)

    if rhr is not None:
        bands = RecoveryBands(
            hrv=bands.hrv,
            resting_hr=(
                RecoveryBand("normal", None, rhr.center),
                RecoveryBand("watch", rhr.center, rhr.center + rhr.spread),
                RecoveryBand("alert", rhr.center + rhr.spread, None),
            ),
            sleep_s=bands.sleep_s,
        )

    sleep_bands = [
        RecoveryBand("normal", *SLEEP_NORMAL),
        *[
            RecoveryBand("watch", low, high)
            for low, high in SLEEP_WATCH
        ],
        RecoveryBand("alert", None, SLEEP_WATCH[0][0]),
        RecoveryBand("alert", SLEEP_WATCH[1][1], None),
    ]

    return RecoveryBands(
        hrv=bands.hrv,
        resting_hr=bands.resting_hr,
        sleep_s=tuple(sleep_bands),
    )



def recovery_trends(
    wellness: list[WellnessDay],
    start: date,
    end: date,
    *,
    window_days: int = 7,
) -> list[RecoveryPoint]:
    """Return wellness points in range with rolling calendar-day averages."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")

    ordered = sorted(wellness, key=lambda day: day.date)

    if not ordered:
        return []

    hrv_avg = rolling_mean_by_date(
        [(day.date, day.hrv) for day in ordered],
        window_days,
    )
    rhr_avg = rolling_mean_by_date(
        [(day.date, day.resting_hr) for day in ordered],
        window_days,
    )
    sleep_avg = rolling_mean_by_date(
        [(day.date, day.sleep_s) for day in ordered],
        window_days,
    )

    points = []

    for index, day in enumerate(ordered):
        if not (start <= day.date <= end):
            continue

        points.append(
            RecoveryPoint(
                date=day.date,
                hrv=day.hrv,
                resting_hr=day.resting_hr,
                sleep_s=day.sleep_s,
                hrv_avg=hrv_avg[index],
                resting_hr_avg=rhr_avg[index],
                sleep_avg=sleep_avg[index],
            )
        )

    return points
