"""Effective VO2max from pace and heart rate, and the methods comparison.

The estimate is the lab's promoted HR/economy metric: the ACSM running
oxygen cost ``3.5 + 0.2 * speed_m_min`` divided by the fraction of maximum
heart rate the session was run at. It needs no streams, uses the running
max-HR snapshot in force on the day, and is guarded to a physiological
fraction and a running speed.

The daily value is the mean of that day's runs, carried forward between run
days so the 42- and 182-day EWMAs describe the metric's standing value.
Garmin and Runalyze values are comparison series, never blended in: both are
smoothed with the same 42/182-day EWMAs, while Garmin keeps its raw readings
as well.

Runalyze stores its effective VO2max with a 0.93 correction already applied;
its stored values are smoothed as they are. Race VDOT uses Daniels' formula
on an official road-race pair.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from hobbyjogging_core.model import Activity, AthleteThreshold, Device

from ..model import (
    GarminVo2maxDevice,
    Vo2maxMeasurement,
    Vo2maxMethods,
    Vo2maxPoint,
    Vo2maxSample,
)
from ..series import alpha_from_time_constant, date_range, ewma
from .common import RUN_TYPES
from .devices import device_label
from .races import RaceResult, official_pair

VO2MAX_SHORT_DAYS = 42
VO2MAX_LONG_DAYS = 182
VO2MAX_WARMUP_DAYS = 5 * VO2MAX_LONG_DAYS
VO2MAX_DISPLAY_START = date(2023, 1, 1)
VO2MAX_MIN_FRACTION = 0.5
VO2MAX_MAX_FRACTION = 0.95
VO2MAX_MIN_SPEED_M_S = 1.5
VO2MAX_MAX_SPEED_M_S = 6.0
# Runalyze stores its effective VO2max with this correction applied.
RUNALYZE_STORED_CORRECTION = 0.93


def threshold_max_hr(
    thresholds: Iterable[AthleteThreshold],
    day: date,
) -> float | None:
    """Running max HR in force on ``day``.

    The latest snapshot on or before the day wins; a day before the first
    running snapshot uses that first one, because the athlete's maximum does
    not move much and the early log has no other value.
    """
    runs = sorted(
        (
            threshold
            for threshold in thresholds
            if threshold.sport == "run" and threshold.max_hr
        ),
        key=lambda threshold: threshold.effective_from,
    )

    if not runs:
        return None

    current = None

    for threshold in runs:
        if threshold.effective_from <= day:
            current = threshold.max_hr
        else:
            break

    return current or runs[0].max_hr


def effective_vo2max(
    activity: Activity,
    max_hr: float | None,
) -> float | None:
    """Effective VO2max for one activity, or ``None`` when it cannot."""
    if activity.type not in RUN_TYPES or not max_hr or max_hr <= 0:
        return None
    if not activity.duration_s or not activity.distance_m:
        return None
    if activity.avg_hr is None:
        return None

    speed = activity.distance_m / activity.duration_s

    if not (VO2MAX_MIN_SPEED_M_S <= speed <= VO2MAX_MAX_SPEED_M_S):
        return None

    fraction = activity.avg_hr / max_hr

    if not (VO2MAX_MIN_FRACTION <= fraction <= VO2MAX_MAX_FRACTION):
        return None

    return (3.5 + 0.2 * speed * 60) / fraction


def vo2max_samples(
    activities: Iterable[Activity],
    thresholds: Iterable[AthleteThreshold],
) -> list[Vo2maxSample]:
    """One effective estimate per qualifying run."""
    thresholds = list(thresholds)
    samples = []

    for activity in activities:
        value = effective_vo2max(
            activity,
            threshold_max_hr(thresholds, activity.date),
        )

        if value is not None:
            samples.append(Vo2maxSample(date=activity.date, value=value))

    return samples


def _ewma_pair(values: list[float]) -> tuple[list[float], list[float]]:
    """The 42- and 182-day EWMAs of one carried daily series."""
    return (
        ewma(
            values,
            alpha_from_time_constant(VO2MAX_SHORT_DAYS),
            initial=values[0],
        ),
        ewma(
            values,
            alpha_from_time_constant(VO2MAX_LONG_DAYS),
            initial=values[0],
        ),
    )


def _carried_series(
    values_by_day: dict[date, list[float]],
    end: date,
) -> tuple[dict[date, float], list[date], list[float]] | None:
    """Daily mean plus the last value carried forward to ``end``."""
    if not values_by_day:
        return None

    daily = {
        day: sum(values) / len(values)
        for day, values in values_by_day.items()
    }
    days = date_range(min(daily), end)
    carried = []
    state = None

    for day in days:
        if day in daily:
            state = daily[day]

        carried.append(state)

    return daily, days, carried


def vo2max_points(
    samples: Iterable[Vo2maxSample],
    start: date,
    end: date,
) -> list[Vo2maxPoint]:
    """Daily estimate with its 42- and 182-day EWMAs from ``start`` to ``end``.

    Days without a run carry the previous value forward, so the averages
    describe the metric's standing value rather than a zero-filled gap.
    """
    if start > end:
        return []

    by_day: dict[date, list[float]] = defaultdict(list)

    for sample in samples:
        if sample.date <= end:
            by_day[sample.date].append(sample.value)

    series = _carried_series(by_day, end)

    if series is None:
        return []

    daily, days, carried = series
    short, long = _ewma_pair(carried)

    return [
        Vo2maxPoint(
            date=day,
            value=daily.get(day),
            avg_42=short[index],
            avg_182=long[index],
        )
        for index, day in enumerate(days)
        if day >= start
    ]


def vo2max_measurements(
    activities: Iterable[Activity],
    start: date,
    end: date,
) -> list[Vo2maxMeasurement]:
    """Raw Garmin VO2max readings, one per activity, without averaging."""
    return sorted(
        (
            Vo2maxMeasurement(
                date=activity.date,
                value=activity.vo2max_garmin,
            )
            for activity in activities
            if activity.type in RUN_TYPES
            and activity.vo2max_garmin is not None
            and activity.vo2max_garmin > 0
            and start <= activity.date <= end
        ),
        key=lambda measurement: (measurement.date, measurement.value),
    )


def garmin_vo2max_devices(
    activities: Iterable[Activity],
    devices: Iterable[Device],
    start: date,
    end: date,
) -> list[GarminVo2maxDevice]:
    """Garmin readings grouped by recording device, oldest device first."""
    labels = {device.id: device_label(device) for device in devices}
    grouped: dict[str, list[Vo2maxMeasurement]] = defaultdict(list)

    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue

        value = activity.vo2max_garmin

        if value is None or value <= 0 or activity.date > end:
            continue

        grouped[activity.device_id].append(
            Vo2maxMeasurement(date=activity.date, value=value)
        )

    series = []

    for device_id, measurements in grouped.items():
        measurements.sort(key=lambda measurement: measurement.date)
        visible = [
            measurement
            for measurement in measurements
            if measurement.date >= start
        ]

        if not visible:
            continue

        by_day: dict[date, list[float]] = defaultdict(list)

        for measurement in measurements:
            by_day[measurement.date].append(measurement.value)

        _, days, carried = _carried_series(by_day, end)
        short, long = _ewma_pair(carried)
        series.append(
            GarminVo2maxDevice(
                device_id=device_id,
                label=labels.get(device_id, device_id or "Unknown device"),
                measurements=visible,
                avg_42=[
                    (day, short[index])
                    for index, day in enumerate(days)
                    if day >= start
                ],
                avg_182=[
                    (day, long[index])
                    for index, day in enumerate(days)
                    if day >= start
                ],
            )
        )

    return sorted(series, key=lambda item: item.measurements[0].date)


def runalyze_vo2max_points(
    activities: Iterable[Activity],
    start: date,
    end: date,
) -> list[Vo2maxPoint]:
    """Runalyze's stored estimate with its 42- and 182-day EWMAs."""
    by_day: dict[date, list[float]] = defaultdict(list)

    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue

        value = activity.vo2max_runalyze

        if value is None or value <= 0 or activity.date > end:
            continue

        by_day[activity.date].append(value)

    series = _carried_series(by_day, end)

    if series is None:
        return []

    _, days, carried = series
    short, long = _ewma_pair(carried)

    return [
        Vo2maxPoint(
            date=day,
            avg_42=short[index],
            avg_182=long[index],
        )
        for index, day in enumerate(days)
        if day >= start
    ]


def race_vdot(distance_m: float, time_s: float) -> float | None:
    """Daniels' VDOT for one road-race performance."""
    if distance_m <= 0 or time_s <= 0:
        return None

    velocity = distance_m / (time_s / 60.0)
    oxygen = -4.60 + 0.182258 * velocity + 0.000104 * velocity ** 2
    minutes = time_s / 60.0
    fraction = (
        0.8
        + 0.1894393 * math.exp(-0.012778 * minutes)
        + 0.2989558 * math.exp(-0.1932605 * minutes)
    )

    return oxygen / fraction if fraction else None


def race_vdots(
    results: Iterable[RaceResult],
) -> list[tuple[date, float]]:
    """Race VDOT from official road results, oldest first."""
    points = []

    for result in results:
        if result.activity.type != "run":
            continue
        if not official_pair(result.official):
            continue

        value = race_vdot(
            result.official.official_distance_m or 0,
            result.official.official_time_s or 0,
        )

        if value is not None:
            points.append((result.activity.date, value))

    return sorted(points)


def vo2max_methods(
    activities: Iterable[Activity],
    thresholds: Iterable[AthleteThreshold],
    devices: Iterable[Device],
    results: Iterable[RaceResult],
    start: date,
    end: date,
) -> Vo2maxMethods:
    """Assemble every series the methods chart compares."""
    thresholds = list(thresholds)
    activities = list(activities)

    return Vo2maxMethods(
        all_runs=vo2max_points(
            vo2max_samples(activities, thresholds),
            start,
            end,
        ),
        garmin=garmin_vo2max_devices(activities, devices, start, end),
        runalyze=runalyze_vo2max_points(activities, start, end),
        races=[
            (day, value)
            for day, value in race_vdots(results)
            if day >= start
        ],
    )
