"""Pace-zone series, planned zone time, and zone averages."""

from __future__ import annotations

from datetime import date, timedelta

from hobbyjogging_core.model import Activity, Event

from .averages import (
    AVERAGE_WARMUP_FACTOR,
    DEFAULT_AVERAGE_WINDOWS,
    _average_rows,
    _extend_series,
    average_warmup_days,
)
from .common import (
    DEFAULT_ZONE_COUNT,
    RUN_TYPES,
    _planned_events,
    event_zone_seconds,
    week_start,
)
from ..model import AverageWindows, TimePoint, TimeZoneWeek, ZoneAveragePoint
from .planned import daily_planned_time
from ..series import (
    alpha_from_time_constant,
    daily_sums,
    date_range,
    ewma,
)


def _normalized_zone_times(
    activity: Activity,
    zone_count: int,
) -> list[float]:
    """Return pace zone seconds padded/folded to ``zone_count`` zones."""
    if zone_count <= 0:
        raise ValueError("zone_count must be positive")

    total = activity.duration_s or 0.0
    zones = list(activity.pace_zone_times or [])

    if total <= 0 or not zones:
        return [0.0] * zone_count

    zoned_total = sum(zones)

    if zoned_total <= 0:
        return [0.0] * zone_count

    if zoned_total > total:
        scale = total / zoned_total
        zones = [value * scale for value in zones]

    result = [0.0] * zone_count

    for index, seconds in enumerate(zones):
        result[min(index, zone_count - 1)] += seconds

    return result


def daily_run_time(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Sum running time (seconds) per day, filling rest days with zero."""
    by_day: dict[date, float] = {}

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        if activity.type not in RUN_TYPES:
            continue

        by_day[activity.date] = (
            by_day.get(activity.date, 0.0)
            + (activity.duration_s or 0.0)
        )

    return daily_sums(by_day, start, end)


def time_averages(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    windows: AverageWindows | None = None,
    warmup_days: int | None = None,
    events: list[Event] | None = None,
    projected_end: date | None = None,
    projection_start: date | None = None,
    zones: tuple[int, ...] | None = None,
) -> list[TimePoint]:
    """Return daily running time with its three EWMAs.

    ``activities`` must include the warm-up range before ``start``. When
    ``events`` and ``projected_end`` are given, the averages continue
    through planned time; those points are marked ``projected``. Pass
    ``zones`` (1-based) to average only those pace zones, e.g. ``(3, 4)``
    for hard running; such series are not projected.
    """
    windows = windows or DEFAULT_AVERAGE_WINDOWS

    if warmup_days is None:
        warmup_days = average_warmup_days(windows)

    projection_start = projection_start or end
    projected = (
        events is not None
        and projected_end is not None
        and projected_end > projection_start
        and zones is None
    )
    series_end = projection_start if projected else end

    warm_start = start - timedelta(days=warmup_days)

    if zones is None:
        series = daily_run_time(activities, warm_start, series_end)
    else:
        zone_series = daily_zone_time(
            activities,
            warm_start,
            series_end,
            zone_count=max(zones),
        )
        series = [
            (day, sum(values[index - 1] for index in zones))
            for day, values in zone_series
        ]

    if projected:
        series = _extend_series(
            series,
            daily_planned_time(
                events,
                series_end + timedelta(days=1),
                projected_end,
            ),
            projected_end,
        )
    else:
        projection_start = None

    rows = _average_rows(
        series,
        start,
        windows,
        projected_start=projection_start,
    )

    return [
        TimePoint(
            date=day,
            time_s=value,
            base=base,
            fitness=fitness,
            fatigue=fatigue,
            projected=projected_value,
        )
        for day, value, base, fitness, fatigue, projected_value in rows
    ]


def daily_zone_time(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    zone_count: int = DEFAULT_ZONE_COUNT,
) -> list[tuple[date, list[float]]]:
    """Daily running seconds per pace zone, zero-filled."""
    by_day: dict[date, list[float]] = {}

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        if activity.type not in RUN_TYPES:
            continue

        zones = _normalized_zone_times(activity, zone_count)

        if not any(zones):
            continue

        row = by_day.setdefault(activity.date, [0.0] * zone_count)

        for index, seconds in enumerate(zones):
            row[index] += seconds

    return [
        (day, by_day.get(day, [0.0] * zone_count))
        for day in date_range(start, end)
    ]


def daily_planned_zone_time(
    events: list[Event],
    start: date,
    end: date,
    *,
    kind: str | None = "pace",
    zone_count: int = DEFAULT_ZONE_COUNT,
) -> list[tuple[date, list[float]]]:
    """Planned running seconds per zone, zero-filled, for events in range."""
    by_day: dict[date, list[float]] = {}

    for event in _planned_events(events, start, end, running_only=True):
        if kind is not None and event.zone_kind != kind:
            continue

        zones = event_zone_seconds(event, zone_count)

        if zones is None:
            continue

        row = by_day.setdefault(event.date, [0.0] * zone_count)

        for index, seconds in enumerate(zones):
            row[index] += seconds

    return [
        (day, by_day.get(day, [0.0] * zone_count))
        for day in date_range(start, end)
    ]


def zone_time_averages(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    window_days: int,
    warmup_days: int | None = None,
    zone_count: int = DEFAULT_ZONE_COUNT,
    events: list[Event] | None = None,
    projected_end: date | None = None,
    projection_start: date | None = None,
    kind: str | None = "pace",
) -> list[ZoneAveragePoint]:
    """Return one EWMA series per pace zone for the selected window.

    When ``events`` and ``projected_end`` are given, the averages continue
    through planned zone time; those points are marked ``projected``.
    """
    if window_days <= 0:
        raise ValueError("window_days must be positive")

    if warmup_days is None:
        warmup_days = AVERAGE_WARMUP_FACTOR * window_days

    projection_start = projection_start or end
    projected = (
        events is not None
        and projected_end is not None
        and projected_end > projection_start
    )
    series_end = projection_start if projected else end

    warm_start = start - timedelta(days=warmup_days)
    series = daily_zone_time(
        activities,
        warm_start,
        series_end,
        zone_count=zone_count,
    )

    if projected:
        series = series + daily_planned_zone_time(
            events,
            series_end + timedelta(days=1),
            projected_end,
            kind=kind,
            zone_count=zone_count,
        )
    else:
        projection_start = None

    alpha = alpha_from_time_constant(window_days)

    columns = [
        ewma(
            [zones[index] for _, zones in series],
            alpha,
        )
        for index in range(zone_count)
    ]

    points = []

    for row_index, (day, _) in enumerate(series):
        if day < start:
            continue

        points.append(
            ZoneAveragePoint(
                date=day,
                zones=[column[row_index] for column in columns],
                projected=(
                    projection_start is not None
                    and day > projection_start
                ),
            )
        )

    return points


def weekly_time_by_zone(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    zone_count: int = DEFAULT_ZONE_COUNT,
) -> list[TimeZoneWeek]:
    """Aggregate weekly running time by pace zone.

    Activities without pace zone data, or time outside the recorded zones,
    become an ``unzoned`` remainder so the stack still equals running time.
    """
    weeks: dict[date, TimeZoneWeek] = {}

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        if activity.type not in RUN_TYPES:
            continue

        total = activity.duration_s or 0.0

        if total <= 0:
            continue

        week = week_start(activity.date)
        row = weeks.get(week)

        if row is None:
            row = weeks[week] = TimeZoneWeek(
                week=week,
                zones=[0.0] * zone_count,
            )

        zoned = _normalized_zone_times(activity, zone_count)
        zoned_total = sum(zoned)

        if zoned_total <= 0:
            row.unzoned += total
            continue

        for index, seconds in enumerate(zoned):
            row.zones[index] += seconds

        row.unzoned += max(total - zoned_total, 0.0)

    return [weeks[week] for week in sorted(weeks)]


def weekly_planned_time_by_zone(
    events: list[Event],
    start: date,
    end: date,
    *,
    kind: str | None = "hr",
    zone_count: int = DEFAULT_ZONE_COUNT,
    running_only: bool = True,
) -> list[TimeZoneWeek]:
    """Aggregate planned running time by zone.

    With a ``kind``, only events whose ``zone_kind`` matches it are included.
    With ``kind=None``, every event carrying usable zone times is included,
    regardless of kind. Extra zones fold into the last displayed zone;
    ``SS`` buckets are ignored.
    """
    weeks: dict[date, TimeZoneWeek] = {}

    for event in _planned_events(events, start, end, running_only=running_only):
        if kind is not None and event.zone_kind != kind:
            continue

        zones = event_zone_seconds(event, zone_count)

        if zones is None:
            continue

        week = week_start(event.date)
        row = weeks.get(week)

        if row is None:
            row = weeks[week] = TimeZoneWeek(
                week=week,
                zones=[0.0] * zone_count,
            )

        for index, seconds in enumerate(zones):
            row.zones[index] += seconds

    return [weeks[week] for week in sorted(weeks)]
