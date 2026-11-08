"""Source-agnostic analysis.

Functions here take model objects (see ``hobbyjogging_core.model``) and return
plain Python structures. They never touch the API, a database, or plotting.
"""

from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from hobbyjogging_core.model import Activity, Event, Interval, WellnessDay
from hobbyjogging_core.sports import RUN_SPORTS

from .model import (
    DistancePoint,
    LoadPoint,
    AverageWindows,
    RecoveryPoint,
    SubtBlock,
    SubtPoint,
    SubtSummary,
    TimePoint,
    TimeZoneWeek,
    ZoneAveragePoint,
)
from .series import (
    alpha_from_time_constant,
    daily_sums,
    date_range,
    ewma,
    rolling_mean_by_date,
)

RUN_TYPES = RUN_SPORTS

CATEGORY_SHORT = "short"
CATEGORY_MEDIUM = "medium"
CATEGORY_LONG = "long"
SUBT_CATEGORIES = (CATEGORY_SHORT, CATEGORY_MEDIUM, CATEGORY_LONG)

LT1_WORDS = ("lt1", "lt 1")

# Average rep duration thresholds (seconds), matching the report logic.
SHORT_MAX_S = 240
MEDIUM_MAX_S = 420

SUBT_CATEGORY_ORDER = (*SUBT_CATEGORIES, "lt1")

DEFAULT_AVERAGE_WINDOWS = AverageWindows()
AVERAGE_WARMUP_FACTOR = 5

DEFAULT_ZONE_COUNT = 4

# Work interval filtering. Older Intervals.icu activities mark warm-up,
# cool-down and recovery jogs as WORK; work reps form the fast pace cluster.
WORK_MIN_DURATION_S = 60


def activity_sort_key(activity: Activity) -> tuple[date, str]:
    """Order activities chronologically, including same-day sessions."""
    return (activity.date, activity.started_at_utc)
WORK_MIN_DISTANCE_M = 100
WORK_PACE_BAND = 1.20
WORK_MIN_HR_SHARE = 0.85
WORK_SLOW_PACE_BAND = 1.10


def week_start(d: date) -> date:
    """Monday of the week containing ``d``."""
    return d - timedelta(days=d.weekday())


def week_end(d: date) -> date:
    """Sunday of the week containing ``d``."""
    return week_start(d) + timedelta(days=6)


def week_bounds(start: date, end: date) -> tuple[date, date]:
    """Expand a date range to whole Monday–Sunday weeks."""
    return week_start(start), week_end(end)


def weekly_run_distance(activities: list[Activity]) -> list[tuple[date, float]]:
    """Run distance (km) per week, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for a in activities:
        if a.type in RUN_TYPES:
            totals[week_start(a.date)] += a.distance_m

    return [(week, totals[week] / 1000) for week in sorted(totals)]


def _planned_events(
    events: list[Event],
    start: date,
    end: date,
    *,
    running_only: bool = False,
):
    """Yield planned events in range, skipping undated notes without a sport."""
    for event in events:
        if not (start <= event.date <= end):
            continue
        if not event.type:
            continue
        if running_only and event.type not in RUN_TYPES:
            continue
        yield event


def weekly_planned_distance(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned running distance (km) per week, oldest first.

    Events without a planned distance are skipped.
    """
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end, running_only=True):
        if event.distance_m:
            totals[week_start(event.date)] += event.distance_m

    return [(week, totals[week] / 1000) for week in sorted(totals)]


def weekly_planned_time(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned running time (seconds) per week, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end, running_only=True):
        if event.duration_s:
            totals[week_start(event.date)] += event.duration_s

    return [(week, totals[week]) for week in sorted(totals)]


def daily_planned_distance(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned running distance (km) per day, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end, running_only=True):
        if event.distance_m:
            totals[event.date] += event.distance_m / 1000

    return sorted(totals.items())


def daily_planned_time(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned running time (seconds) per day, oldest first."""
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end, running_only=True):
        if event.duration_s:
            totals[event.date] += event.duration_s

    return sorted(totals.items())


def daily_planned_load(
    events: list[Event],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Planned training load per day, oldest first.

    All sports are included; days without planned load are skipped.
    """
    totals: dict[date, float] = defaultdict(float)

    for event in _planned_events(events, start, end):
        if event.training_load:
            totals[event.date] += event.training_load

    return sorted(totals.items())


def planned_workout_dates(
    events: list[Event],
    start: date,
    end: date,
) -> list[date]:
    """One date per planned workout, oldest first.

    Events without a sport type are notes (illness, travel) and are skipped.
    Multiple workouts on one day produce repeated dates.
    """
    return sorted(
        event.date
        for event in _planned_events(events, start, end)
    )


def is_subt_activity(a: Activity) -> bool:
    """True if the name marks the session as a subT workout.

    Only the name is used: descriptions often mention alternatives
    ("did 3x10@LT1 instead of subT") and would pull LT1 sessions in.
    """
    return "subt" in a.name.lower()


def is_lt1_activity(a: Activity) -> bool:
    """True if the name marks the session as an LT1 workout."""
    text = a.name.lower()
    return any(word in text for word in LT1_WORDS)


def classify_interval(duration_s: float) -> str:
    """Classify an interval by its (average rep) duration."""
    if duration_s <= SHORT_MAX_S:
        return CATEGORY_SHORT
    if duration_s <= MEDIUM_MAX_S:
        return CATEGORY_MEDIUM
    return CATEGORY_LONG


def pace_s_per_km(duration_s: float, distance_m: float) -> float | None:
    """Average pace in seconds per km."""
    if duration_s <= 0 or distance_m <= 0:
        return None
    return duration_s / distance_m * 1000


def work_intervals(intervals: list[Interval]) -> list[Interval]:
    """Return the intervals that are actual work reps.

    Older Intervals.icu data labels warm-up, cool-down and recovery jogs as
    WORK as well. Work reps are the fast pace cluster; everything else is
    slower. Strides and GPS artifacts are ignored. When there is not enough
    pace data to separate the clusters, all WORK intervals are returned.
    """
    work = [
        i for i in intervals
        if i.type == "WORK" and i.duration_s > 0
    ]

    paced = [
        i for i in work
        if i.duration_s >= WORK_MIN_DURATION_S
        and i.distance_m >= WORK_MIN_DISTANCE_M
    ]

    if len(paced) < 3:
        return work

    def pace(i: Interval) -> float:
        return i.duration_s / i.distance_m * 1000

    ordered = sorted(paced, key=pace)

    # Use the fastest third as the reference so a single flier cannot pull
    # the band down, while recovery jogs cannot pull it up.
    fastest = ordered[:max(1, len(ordered) // 3)]
    reference = median(pace(i) for i in fastest)

    reps = [
        i for i in paced
        if pace(i) <= reference * WORK_PACE_BAND
    ]

    if not reps:
        return work

    # Warm-ups can sit just inside the pace band, but their heart rate is
    # still clearly below the work reps. Only drop slow, low-HR intervals so
    # short reps with heart-rate lag are kept.
    hrs = [i.avg_hr for i in reps if i.avg_hr is not None]

    if not hrs:
        return reps

    median_pace = median(pace(i) for i in reps)
    min_hr = max(hrs) * WORK_MIN_HR_SHARE

    filtered = [
        i for i in reps
        if not (
            i.avg_hr is not None
            and i.avg_hr < min_hr
            and pace(i) > median_pace * WORK_SLOW_PACE_BAND
        )
    ]

    return filtered or reps


def _subt_point(
    activity: Activity,
    intervals: list[Interval],
    category: str | None = None,
) -> SubtPoint | None:
    """Aggregate a list of work reps into one pace point."""
    total_time = sum(i.duration_s for i in intervals)
    total_distance = sum(i.distance_m for i in intervals)

    pace = pace_s_per_km(total_time, total_distance)
    if pace is None:
        return None

    # Time-weighted average heart rate.
    hr_pairs = [
        (i.avg_hr, i.duration_s)
        for i in intervals
        if i.avg_hr is not None
    ]

    avg_hr = None
    if hr_pairs:
        avg_hr = (
            sum(hr * t for hr, t in hr_pairs)
            / sum(t for _, t in hr_pairs)
        )

    max_hr = max(
        (i.max_hr for i in intervals if i.max_hr is not None),
        default=None,
    )

    rep_paces = []
    for interval in intervals:
        rep_pace = pace_s_per_km(interval.duration_s, interval.distance_m)
        if rep_pace is not None:
            rep_paces.append(rep_pace)

    return SubtPoint(
        date=activity.date,
        category=category or classify_interval(total_time / len(intervals)),
        pace_s_per_km=pace,
        count=len(intervals),
        avg_hr=avg_hr,
        max_hr=max_hr,
        avg_rep_s=total_time / len(intervals),
        fastest_pace_s_per_km=min(rep_paces) if rep_paces else None,
        slowest_pace_s_per_km=max(rep_paces) if rep_paces else None,
    )


def _paced_work(intervals: list[Interval]) -> list[Interval]:
    return [
        i for i in work_intervals(intervals)
        if i.duration_s and i.distance_m
    ]


def subt_work_points(
    activity: Activity,
    intervals: list[Interval],
) -> list[SubtPoint]:
    """One point per WORK interval group (set of reps) in an activity."""
    work = _paced_work(intervals)

    groups: dict[str, list[Interval]] = {}

    for index, interval in enumerate(work):
        key = interval.group_id or f"interval-{index}"
        groups.setdefault(key, []).append(interval)

    points = []

    for group in groups.values():
        point = _subt_point(activity, group)
        if point is not None:
            points.append(point)

    return points


def subt_session_point(
    activity: Activity,
    intervals: list[Interval],
    category: str | None = None,
) -> SubtPoint | None:
    """One point per activity, aggregating all of its work reps.

    ``category`` can override the rep-length category, e.g. for LT1.
    """
    work = _paced_work(intervals)

    if not work:
        return None

    return _subt_point(activity, work, category=category)


def _combine_points(
    activity: Activity,
    category: str,
    points: list[SubtPoint],
) -> SubtBlock | None:
    """Merge same-category points from one session into one report block."""
    count = sum(point.count for point in points)

    if count <= 0:
        return None

    total_time = sum(
        point.count * point.avg_rep_s
        for point in points
    )
    total_distance = sum(
        (point.count * point.avg_rep_s) / point.pace_s_per_km * 1000
        for point in points
    )
    block_pace = pace_s_per_km(total_time, total_distance)

    if block_pace is None:
        return None

    hr_pairs = [
        (point.avg_hr, point.count * point.avg_rep_s)
        for point in points
        if point.avg_hr is not None
    ]
    hr_time = sum(time for _, time in hr_pairs)

    avg_hr = (
        sum(hr * time for hr, time in hr_pairs) / hr_time
        if hr_time
        else None
    )

    max_hrs = [
        point.max_hr
        for point in points
        if point.max_hr is not None
    ]
    fastest = [
        point.fastest_pace_s_per_km
        for point in points
        if point.fastest_pace_s_per_km is not None
    ]
    slowest = [
        point.slowest_pace_s_per_km
        for point in points
        if point.slowest_pace_s_per_km is not None
    ]

    return SubtBlock(
        date=activity.date,
        activity_id=activity.id,
        activity_name=activity.name,
        category=category,
        count=count,
        avg_rep_s=total_time / count,
        total_time_s=total_time,
        total_distance_m=total_distance,
        pace_s_per_km=block_pace,
        fastest_pace_s_per_km=min(fastest) if fastest else None,
        slowest_pace_s_per_km=max(slowest) if slowest else None,
        avg_hr=avg_hr,
        max_hr=max(max_hrs) if max_hrs else None,
    )


def subt_blocks(
    activity: Activity,
    intervals: list[Interval],
) -> list[SubtBlock]:
    """Return one block per work category within a subT or LT1 session."""
    if not (is_subt_activity(activity) or is_lt1_activity(activity)):
        return []

    points = subt_work_points(activity, intervals)

    if not points:
        return []

    grouped: dict[str, list[SubtPoint]] = {}

    for point in points:
        category = "lt1" if is_lt1_activity(activity) else point.category
        grouped.setdefault(category, []).append(point)

    blocks = []

    for category, category_points in grouped.items():
        block = _combine_points(activity, category, category_points)
        if block is not None:
            blocks.append(block)

    return blocks


def subt_report_blocks(
    activities: list[Activity],
    intervals_by_id: dict[str, list[Interval]],
) -> list[SubtBlock]:
    """Collect report blocks for subT/LT1 sessions, grouped and sorted."""
    blocks = []

    for activity in activities:
        blocks.extend(
            subt_blocks(
                activity,
                intervals_by_id.get(activity.id, []),
            )
        )

    order = {
        category: index
        for index, category in enumerate(SUBT_CATEGORY_ORDER)
    }

    return sorted(
        blocks,
        key=lambda block: (
            order.get(block.category, len(order)),
            block.date,
            block.activity_name,
            block.activity_id,
        ),
    )


def _summary_from_blocks(
    category: str,
    blocks: list[SubtBlock],
) -> SubtSummary:
    total_time = sum(block.total_time_s for block in blocks)
    total_distance = sum(block.total_distance_m for block in blocks)

    hr_pairs = [
        (block.avg_hr, block.total_time_s)
        for block in blocks
        if block.avg_hr is not None
    ]
    hr_time = sum(time for _, time in hr_pairs)

    max_hrs = [
        block.max_hr
        for block in blocks
        if block.max_hr is not None
    ]

    return SubtSummary(
        category=category,
        sessions=len({block.activity_id for block in blocks}),
        reps=sum(block.count for block in blocks),
        total_time_s=total_time,
        total_distance_m=total_distance,
        pace_s_per_km=pace_s_per_km(total_time, total_distance),
        avg_hr=(
            sum(hr * time for hr, time in hr_pairs) / hr_time
            if hr_time
            else None
        ),
        max_hr=max(max_hrs) if max_hrs else None,
    )


def subt_report_summary(
    blocks: list[SubtBlock],
) -> tuple[list[SubtSummary], SubtSummary]:
    """Return per-category summaries (including empty ones) and a total."""
    by_category: dict[str, list[SubtBlock]] = {
        category: []
        for category in SUBT_CATEGORY_ORDER
    }

    for block in blocks:
        by_category.setdefault(block.category, []).append(block)

    summaries = [
        _summary_from_blocks(category, by_category.get(category, []))
        for category in SUBT_CATEGORY_ORDER
    ]

    return summaries, _summary_from_blocks("total", blocks)


def average_warmup_days(windows: AverageWindows | None = None) -> int:
    """Days of history needed before a load chart's display range."""
    windows = windows or DEFAULT_AVERAGE_WINDOWS
    return AVERAGE_WARMUP_FACTOR * max(
        windows.base,
        windows.fitness,
        windows.fatigue,
    )


def daily_training_load(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Sum training load per day, filling rest days with zero."""
    by_day: dict[date, float] = {}

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        by_day[activity.date] = (
            by_day.get(activity.date, 0.0)
            + (activity.training_load or 0.0)
        )

    return daily_sums(by_day, start, end)


def daily_run_distance(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    """Sum running distance (km) per day, filling rest days with zero."""
    by_day: dict[date, float] = {}

    for activity in activities:
        if not (start <= activity.date <= end):
            continue

        if activity.type not in RUN_TYPES:
            continue

        by_day[activity.date] = (
            by_day.get(activity.date, 0.0)
            + activity.distance_m / 1000
        )

    return daily_sums(by_day, start, end)


def _ewma_columns(
    series: list[tuple[date, float]],
    windows: AverageWindows,
) -> tuple[list[float], list[float], list[float]]:
    """Return the base, fitness, and fatigue EWMA columns."""
    values = [value for _, value in series]

    return (
        ewma(values, alpha_from_time_constant(windows.base)),
        ewma(values, alpha_from_time_constant(windows.fitness)),
        ewma(values, alpha_from_time_constant(windows.fatigue)),
    )


def _average_rows(
    series: list[tuple[date, float]],
    start: date,
    windows: AverageWindows,
    *,
    projected_start: date | None = None,
) -> list[tuple[date, float, float, float, float, bool]]:
    """Return ``(date, value, base, fitness, fatigue, projected)`` rows."""
    base, fitness, fatigue = _ewma_columns(series, windows)

    return [
        (
            day,
            value,
            base_value,
            fitness_value,
            fatigue_value,
            projected_start is not None and day > projected_start,
        )
        for (day, value), base_value, fitness_value, fatigue_value in zip(
            series,
            base,
            fitness,
            fatigue,
        )
        if day >= start
    ]


def _extend_series(
    series: list[tuple[date, float]],
    planned: list[tuple[date, float]],
    projected_end: date,
) -> list[tuple[date, float]]:
    """Continue a daily series with planned values, zero-filling rest days."""
    next_day = series[-1][0] + timedelta(days=1)
    return series + daily_sums(dict(planned), next_day, projected_end)


def load_metrics(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    windows: AverageWindows | None = None,
    warmup_days: int | None = None,
    events: list[Event] | None = None,
    projected_end: date | None = None,
    projection_start: date | None = None,
) -> list[LoadPoint]:
    """Return daily load with base, fitness, and fatigue EWMAs.

    ``activities`` must include the warm-up range before ``start`` so the
    long average does not begin at zero mid-report. When ``events`` and
    ``projected_end`` are given, the averages continue through planned
    load; those points are marked ``projected``.
    """
    windows = windows or DEFAULT_AVERAGE_WINDOWS

    if warmup_days is None:
        warmup_days = average_warmup_days(windows)

    projection_start = projection_start or end
    projected = (
        events is not None
        and projected_end is not None
        and projected_end > projection_start
    )
    series_end = projection_start if projected else end

    warm_start = start - timedelta(days=warmup_days)
    series = daily_training_load(activities, warm_start, series_end)

    if projected:
        series = _extend_series(
            series,
            daily_planned_load(
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
        LoadPoint(
            date=day,
            load=value,
            base=base,
            fitness=fitness,
            fatigue=fatigue,
            projected=projected_value,
        )
        for day, value, base, fitness, fatigue, projected_value in rows
    ]


def distance_averages(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    windows: AverageWindows | None = None,
    warmup_days: int | None = None,
    events: list[Event] | None = None,
    projected_end: date | None = None,
    projection_start: date | None = None,
) -> list[DistancePoint]:
    """Return daily running distance with its three EWMAs.

    ``activities`` must include the warm-up range before ``start``. When
    ``events`` and ``projected_end`` are given, the averages continue
    through planned distance; those points are marked ``projected``.
    """
    windows = windows or DEFAULT_AVERAGE_WINDOWS

    if warmup_days is None:
        warmup_days = average_warmup_days(windows)

    projection_start = projection_start or end
    projected = (
        events is not None
        and projected_end is not None
        and projected_end > projection_start
    )
    series_end = projection_start if projected else end

    warm_start = start - timedelta(days=warmup_days)
    series = daily_run_distance(activities, warm_start, series_end)

    if projected:
        series = _extend_series(
            series,
            daily_planned_distance(
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
        DistancePoint(
            date=day,
            distance_km=value,
            base=base,
            fitness=fitness,
            fatigue=fatigue,
            projected=projected_value,
        )
        for day, value, base, fitness, fatigue, projected_value in rows
    ]


def _normalized_zone_times(
    activity: Activity,
    zone_count: int,
) -> list[float]:
    """Return HR zone seconds padded/folded to ``zone_count`` zones."""
    if zone_count <= 0:
        raise ValueError("zone_count must be positive")

    total = activity.duration_s or 0.0
    zones = list(activity.hr_zone_times or [])

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
) -> list[TimePoint]:
    """Return daily running time with its three EWMAs.

    ``activities`` must include the warm-up range before ``start``. When
    ``events`` and ``projected_end`` are given, the averages continue
    through planned time; those points are marked ``projected``.
    """
    windows = windows or DEFAULT_AVERAGE_WINDOWS

    if warmup_days is None:
        warmup_days = average_warmup_days(windows)

    projection_start = projection_start or end
    projected = (
        events is not None
        and projected_end is not None
        and projected_end > projection_start
    )
    series_end = projection_start if projected else end

    warm_start = start - timedelta(days=warmup_days)
    series = daily_run_time(activities, warm_start, series_end)

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
    """Daily running seconds per HR zone, zero-filled."""
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


def zone_time_averages(
    activities: list[Activity],
    start: date,
    end: date,
    *,
    window_days: int,
    warmup_days: int | None = None,
    zone_count: int = DEFAULT_ZONE_COUNT,
) -> list[ZoneAveragePoint]:
    """Return one EWMA series per HR zone for the selected window."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")

    if warmup_days is None:
        warmup_days = AVERAGE_WARMUP_FACTOR * window_days

    warm_start = start - timedelta(days=warmup_days)
    series = daily_zone_time(
        activities,
        warm_start,
        end,
        zone_count=zone_count,
    )
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
    """Aggregate weekly running time by HR zone.

    Activities without HR zone data, or time outside the recorded zones,
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
    kind: str = "hr",
    zone_count: int = DEFAULT_ZONE_COUNT,
    running_only: bool = True,
) -> list[TimeZoneWeek]:
    """Aggregate planned running time by zone for one zone kind.

    Only events whose ``zone_kind`` matches ``kind`` and that carry usable
    zone times are included. Extra zones fold into the last displayed zone;
    ``SS`` buckets are ignored.
    """
    weeks: dict[date, TimeZoneWeek] = {}

    for event in _planned_events(events, start, end, running_only=running_only):
        if event.zone_kind != kind:
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


def _event_zone_index(zone) -> int | None:
    """Return an event zone's 1-based index, or ``None`` for ``SS``."""
    index = zone.zone_index

    if index is not None:
        return index

    label = (zone.zone_label or "").strip().upper()

    if not label.startswith("Z"):
        return None

    try:
        return int(label[1:])
    except ValueError:
        return None


def event_zone_seconds(
    event: Event,
    zone_count: int = DEFAULT_ZONE_COUNT,
) -> list[float] | None:
    """Normalize an event's planned zone times to ``zone_count`` buckets.

    Zones past ``zone_count`` fold into the last bucket so planned totals are
    preserved. ``SS`` and unparseable labels are ignored. Returns ``None``
    when the event has no usable zone times.
    """
    if zone_count <= 0:
        raise ValueError("zone_count must be positive")

    if not event.zone_times:
        return None

    result = [0.0] * zone_count
    found = False

    for zone in event.zone_times:
        index = _event_zone_index(zone)

        if index is None or index < 1 or (zone.seconds or 0) <= 0:
            continue

        result[min(index, zone_count) - 1] += zone.seconds
        found = True

    return result if found else None


def event_zone_time(
    event: Event,
    zone_indices: tuple[int, ...],
) -> float | None:
    """Sum planned seconds in the given 1-based zones.

    ``SS`` and unparseable labels are ignored. Returns ``None`` when the
    event has no usable zone times; otherwise returns the sum, which may be
    zero when the requested zones are empty.
    """
    if not event.zone_times:
        return None

    wanted = set(zone_indices)
    total = 0.0
    found = False

    for zone in event.zone_times:
        index = _event_zone_index(zone)

        if index is None or index < 1 or (zone.seconds or 0) <= 0:
            continue

        found = True

        if index in wanted:
            total += zone.seconds

    return total if found else None


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
