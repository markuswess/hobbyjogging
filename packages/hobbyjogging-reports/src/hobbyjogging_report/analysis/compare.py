"""Yearly and monthly training comparisons."""

from datetime import date, timedelta

from hobbyjogging_core.model import Activity

from ..model import ComparePeriod
from ..series import alpha_from_time_constant, ewma
from .common import RUN_TYPES

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
            )
        )

    return result


COMPARE_METRICS = ("volume", "time", "load", "runs")


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
) -> list[tuple[int, list[tuple[date, float]]]]:
    """One EWMA series per year, each from Jan 1 to Dec 31 (or today).

    The series are aligned by day of year; the caller normalizes the dates
    onto a single reference year for plotting.
    """
    if metric not in COMPARE_METRICS:
        raise ValueError(f"unknown compare metric: {metric}")
    if window <= 0:
        raise ValueError("window must be positive")

    today = today or date.today()
    alpha = alpha_from_time_constant(window)
    series = []

    for year in sorted({activity.date.year for activity in activities}):
        start = date(year, 1, 1)
        end = min(date(year, 12, 31), today)

        if start > end:
            continue

        daily = _daily_metric(activities, metric, start, end)

        if not daily:
            continue

        values = [value for _, value in daily]
        smoothed = ewma(values, alpha, initial=values[0])
        series.append((year, list(zip([day for day, _ in daily], smoothed))))

    return series
