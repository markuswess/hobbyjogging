"""Yearly and monthly training comparisons."""

from datetime import date, timedelta

from hobbyjogging_core.model import Activity, Event

from ..model import ComparePeriod
from ..series import alpha_from_time_constant, ewma
from .common import RUN_TYPES
from .efficiency import activity_efficiency, excess_beats

COMPARE_MODES = ("years", "months")


def _period_starts(mode: str, start: date, end: date) -> list[date]:
    """Return the first day of every year or month in the range."""
    if start > end:
        return []

    if mode == "years":
        cursor = date(start.year, 1, 1)
        last = date(end.year, 1, 1)
        step = lambda day: date(day.year + 1, 1, 1)
    elif mode == "months":
        cursor = date(start.year, start.month, 1)
        last = date(end.year, end.month, 1)
        step = lambda day: (
            date(day.year + 1, 1, 1)
            if day.month == 12
            else date(day.year, day.month + 1, 1)
        )
    else:
        raise ValueError(f"unknown compare mode: {mode}")

    periods = []

    while cursor <= last:
        periods.append(cursor)
        cursor = step(cursor)

    return periods


def _period_key(day: date, mode: str) -> date:
    if mode == "years":
        return date(day.year, 1, 1)
    if mode == "months":
        return date(day.year, day.month, 1)
    raise ValueError(f"unknown compare mode: {mode}")


def _label(period: date, mode: str) -> str:
    if mode == "years":
        return str(period.year)
    return f"{period.year:04d}-{period.month:02d}"


def compare_periods(
    activities: list[Activity],
    mode: str,
    start: date,
    end: date,
    *,
    resting_hr_baseline=None,
) -> list[ComparePeriod]:
    """Aggregate basic run and cross-training data by year or month."""
    rows = {
        period: {
            "runs": 0,
            "cross_sessions": 0,
            "run_time_s": 0.0,
            "cross_time_s": 0.0,
            "run_distance_m": 0.0,
            "pace_time_s": 0.0,
            "pace_distance_m": 0.0,
            "hr_sum": 0.0,
            "hr_count": 0,
            "efficiency_distance_m": 0.0,
            "efficiency_beats": 0.0,
        }
        for period in _period_starts(mode, start, end)
    }

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        key = _period_key(activity.date, mode)
        row = rows.get(key)

        if row is None:
            continue

        duration = activity.duration_s or 0
        distance = activity.distance_m or 0

        if activity.type in RUN_TYPES:
            row["runs"] += 1
            row["run_time_s"] += duration
            row["run_distance_m"] += distance

            if duration > 0 and distance > 0:
                row["pace_time_s"] += duration
                row["pace_distance_m"] += distance

            if activity.avg_hr is not None:
                row["hr_sum"] += activity.avg_hr
                row["hr_count"] += 1

            beats = excess_beats(
                activity.duration_s,
                activity.avg_hr,
                (
                    resting_hr_baseline(activity.date)
                    if resting_hr_baseline is not None
                    else None
                ),
            )

            if beats is not None and activity.distance_m:
                row["efficiency_distance_m"] += activity.distance_m
                row["efficiency_beats"] += beats
        else:
            row["cross_sessions"] += 1
            row["cross_time_s"] += duration

    result = []

    for period in sorted(rows):
        row = rows[period]
        pace = (
            row["pace_time_s"] * 1000 / row["pace_distance_m"]
            if row["pace_distance_m"]
            else None
        )
        avg_hr = (
            row["hr_sum"] / row["hr_count"]
            if row["hr_count"]
            else None
        )

        efficiency = (
            row["efficiency_distance_m"] / row["efficiency_beats"]
            if row["efficiency_beats"] > 0
            else None
        )

        result.append(
            ComparePeriod(
                label=_label(period, mode),
                runs=row["runs"],
                cross_sessions=row["cross_sessions"],
                run_time_s=row["run_time_s"],
                cross_time_s=row["cross_time_s"],
                run_distance_m=row["run_distance_m"],
                pace_s_per_km=pace,
                avg_hr=avg_hr,
                efficiency=efficiency,
            )
        )

    return result


def compare_year_planned_ewma(
    events: list[Event],
    metric: str,
    window: int,
    *,
    today: date | None = None,
) -> list[tuple[int, list[tuple[date, float]]]]:
    """Planned volume/time EWMA per calendar year.

    Each year's line starts on its first planned run and ends on the last
    one, so incomplete historical planning is not padded with months of
    zeros. When ``today`` is supplied, only the current and future years are
    returned; older event imports are often incomplete.
    """
    if metric not in ("volume", "time"):
        return []
    if window <= 0:
        raise ValueError("window must be positive")

    runs = [
        event
        for event in events
        if event.type in RUN_TYPES
        and (
            (event.distance_m or 0) > 0
            if metric == "volume"
            else (event.duration_s or 0) > 0
        )
    ]
    by_year: dict[int, list[Event]] = {}

    for event in runs:
        by_year.setdefault(event.date.year, []).append(event)

    series = []

    for year in sorted(by_year):
        if today is not None and year < today.year:
            continue

        year_events = sorted(by_year[year], key=lambda event: event.date)
        first = year_events[0].date
        last = year_events[-1].date
        daily = _daily_event_metric(year_events, metric, first, last)
        values = [value for _, value in daily]
        smoothed = ewma(
            values,
            alpha_from_time_constant(window),
            initial=values[0],
        )

        series.append(
            (year, list(zip([day for day, _ in daily], smoothed)))
        )

    return series


COMPARE_METRICS = ("volume", "time", "load", "runs", "efficiency")
# A year needs enough HR-backed runs for its efficiency line to mean
# something; sparse years would only show a carried-forward flat line.
EFFICIENCY_MIN_RUNS = 20


def _daily_event_metric(
    events: list[Event],
    metric: str,
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Daily planned totals for volume or time, zero-filled for rest days."""
    if metric not in ("volume", "time"):
        raise ValueError(f"no planned compare metric: {metric}")

    by_day: dict[date, float] = {}

    for event in events:
        if event.type not in RUN_TYPES:
            continue
        if not (start <= event.date <= end):
            continue

        if metric == "volume":
            value = (event.distance_m or 0.0) / 1000
        else:
            value = (event.duration_s or 0.0) / 3600

        by_day[event.date] = by_day.get(event.date, 0.0) + value

    return [(day, by_day.get(day, 0.0)) for day in _date_range(start, end)]


def _daily_metric(
    activities: list[Activity],
    metric: str,
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Daily totals for one compare metric, zero-filled for rest days."""
    by_day: dict[date, float] = {}

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        if metric == "load":
            value = activity.training_load or 0.0
        elif activity.type not in RUN_TYPES:
            continue
        elif metric == "runs":
            value = 1.0
        elif metric == "volume":
            value = (activity.distance_m or 0.0) / 1000
        elif metric == "time":
            value = (activity.duration_s or 0.0) / 3600
        else:
            raise ValueError(f"unknown compare metric: {metric}")

        by_day[activity.date] = by_day.get(activity.date, 0.0) + value

    return [(day, by_day.get(day, 0.0)) for day in _date_range(start, end)]


def _daily_efficiency(
    activities: list[Activity],
    start: date,
    end: date,
    resting_hr: Callable[[date], float | None],
) -> list[tuple[date, float | None]]:
    """Daily weighted m/excess beat with rest days carrying the last value."""
    by_day: dict[date, tuple[float, float]] = {}

    for activity in activities:
        if activity.type not in RUN_TYPES:
            continue
        if not (start <= activity.date <= end):
            continue

        total_beats = excess_beats(
            activity.duration_s,
            activity.avg_hr,
            resting_hr(activity.date),
        )

        if not activity.distance_m or total_beats is None:
            continue

        distance, day_beats = by_day.get(activity.date, (0.0, 0.0))
        by_day[activity.date] = (
            distance + activity.distance_m,
            day_beats + total_beats,
        )

    series = []
    carried = None

    for day in _date_range(start, end):
        if day in by_day:
            distance, day_beats = by_day[day]
            carried = distance / day_beats if day_beats > 0 else carried

        series.append((day, carried))

    return series


def _date_range(start: date, end: date) -> list[date]:
    return [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
    ]


def compare_year_ewma(
    activities: list[Activity],
    metric: str,
    window: int,
    *,
    today: date | None = None,
    resting_hr: Callable[[date], float | None] | None = None,
) -> list[tuple[int, list[tuple[date, float]]]]:
    """One EWMA series per year, each from Jan 1 to Dec 31 (or today).

    The EWMA is computed once over the whole history and then sliced by
    year, so every year starts with the value the previous year ended on.
    The caller aligns the dates onto a single reference year for plotting.
    """
    if metric not in COMPARE_METRICS:
        raise ValueError(f"unknown compare metric: {metric}")
    if window <= 0:
        raise ValueError("window must be positive")

    today = today or date.today()
    years = sorted({activity.date.year for activity in activities})

    if not years:
        return []

    start = date(years[0], 1, 1)

    if metric == "efficiency":
        daily = (
            [
                row
                for row in _daily_efficiency(
                    activities,
                    start,
                    today,
                    resting_hr,
                )
                if row[1] is not None
            ]
            if resting_hr is not None
            else []
        )
    else:
        daily = _daily_metric(activities, metric, start, today)

    if not daily:
        return []

    values = [value for _, value in daily]
    smoothed = ewma(
        values,
        alpha_from_time_constant(window),
        initial=values[0],
    )
    by_year: dict[int, list[tuple[date, float]]] = {}

    for (day, _), value in zip(daily, smoothed):
        by_year.setdefault(day.year, []).append((day, value))

    # Start each year exactly on the previous year's closing value, so the
    # year lines meet at the axis edges. Carry through every year before
    # filtering, so dropped years still feed the next kept year's start.
    series = []
    close = None

    for year, points in sorted(by_year.items()):
        if close is not None:
            points = [(points[0][0], close), *points[1:]]

        series.append((year, points))
        close = points[-1][1]

    if metric == "efficiency":
        eligible = _efficiency_run_counts(activities, resting_hr)
        series = [
            (year, points)
            for year, points in series
            if eligible.get(year, 0) >= EFFICIENCY_MIN_RUNS
        ]

    return series


def _efficiency_run_counts(
    activities: list[Activity],
    resting_hr: Callable[[date], float | None],
) -> dict[int, int]:
    """Runs per year with the distance, duration, and HR efficiency needs."""
    counts: dict[int, int] = {}

    for activity in activities:
        if activity_efficiency(
            activity,
            resting_hr(activity.date),
        ) is None:
            continue

        counts[activity.date.year] = counts.get(activity.date.year, 0) + 1

    return counts
