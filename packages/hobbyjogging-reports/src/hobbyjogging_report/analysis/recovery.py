"""Wellness recovery trends and readiness bands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import pstdev

from hobbyjogging_core.model import WellnessDay

from ..model import RecoveryPoint
from ..series import rolling_mean_by_date

# Bands compare the last four weeks of wellness.
BASELINE_DAYS = 42
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


def _baseline(points: list[RecoveryPoint], attribute: str):
    """Return ``(mean, sd)`` over the last four weeks, or ``None``."""
    cutoff = max(point.date for point in points) - timedelta(
        days=BASELINE_DAYS - 1
    )
    values = [
        value
        for point in points
        if point.date >= cutoff
        and (value := getattr(point, attribute)) is not None
    ]

    if len(values) < MIN_BASELINE_VALUES:
        return None

    return sum(values) / len(values), pstdev(values)


def recovery_bands(points: list[RecoveryPoint]) -> RecoveryBands:
    """Readiness bands relative to the last 42 days of each metric.

    HRV is green at or above its baseline, amber down to one standard
    deviation below, and red below that. Resting HR mirrors it (lower is
    better). Sleep is absolute: green 7-9 h, amber 6-7 h or 9-10 h, red
    outside that.
    """
    if not points:
        return RecoveryBands()

    bands = RecoveryBands()
    hrv = _baseline(points, "hrv")

    if hrv is not None:
        mean, sd = hrv
        bands = RecoveryBands(
            hrv=(
                RecoveryBand("normal", mean, None),
                RecoveryBand("watch", mean - sd, mean),
                RecoveryBand("alert", None, mean - sd),
            ),
            resting_hr=bands.resting_hr,
            sleep_s=bands.sleep_s,
        )

    rhr = _baseline(points, "resting_hr")

    if rhr is not None:
        mean, sd = rhr
        bands = RecoveryBands(
            hrv=bands.hrv,
            resting_hr=(
                RecoveryBand("normal", None, mean),
                RecoveryBand("watch", mean, mean + sd),
                RecoveryBand("alert", mean + sd, None),
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
