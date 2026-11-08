"""Chart command handlers."""

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .command_support import (
    print_count_note,
    reviewed_range,
    warmup_reviewed,
)
from .model import AverageWindows


def run_volume_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    windows: AverageWindows,
    *,
    planned_end: date | None = None,
    include_review: bool = False,
) -> None:
    """Render weekly running volume with distance-average lines."""
    from .analysis import (
        average_warmup_days,
        distance_averages,
        week_bounds,
        weekly_planned_distance,
        weekly_run_distance,
    )
    from .charts import plot_volume

    planned_end = planned_end or end
    chart_start, chart_end = week_bounds(start, end)
    _, planned_chart_end = week_bounds(start, planned_end)
    planned_chart_end = max(chart_end, planned_chart_end)
    warmup_days = average_warmup_days(windows)

    display_activities, activities = warmup_reviewed(
        source,
        chart_start,
        chart_end,
        warmup_days,
        include_review,
    )

    events = source.events(chart_start, planned_chart_end)

    points = distance_averages(
        activities,
        chart_start,
        chart_end,
        windows=windows,
        warmup_days=warmup_days,
        events=events,
        projected_end=planned_chart_end,
        projection_start=end,
    )

    path = plot_volume(
        weekly_run_distance(display_activities),
        output=output,
        distance_points=points,
        planned_distance=weekly_planned_distance(
            events,
            chart_start,
            planned_chart_end,
        ),
        windows=windows,
        ylabel="km / week",
    )

    print(path)


def _planned_zone_label(kinds: set[str]) -> str:
    """Legend label for the planned zone stack."""
    if len(kinds) == 1:
        kind = next(iter(kinds))
        name = {"hr": "HR"}.get(kind, kind)
        return f"planned {name} zones"
    return "planned zones"


TIME_ZONE_KIND = "pace"


def run_time_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    windows: AverageWindows,
    zones: int,
    zone_window: str,
    *,
    planned_end: date | None = None,
    include_review: bool = False,
) -> None:
    """Render weekly running time stacked by pace zone."""
    from .analysis import (
        RUN_TYPES,
        average_warmup_days,
        time_averages,
        week_bounds,
        weekly_planned_time,
        weekly_planned_time_by_zone,
        weekly_time_by_zone,
        zone_time_averages,
    )
    from .charts import plot_time

    planned_end = planned_end or end
    chart_start, chart_end = week_bounds(start, end)
    _, planned_chart_end = week_bounds(start, planned_end)
    planned_chart_end = max(chart_end, planned_chart_end)
    warmup_days = average_warmup_days(windows)

    display_activities, activities = warmup_reviewed(
        source,
        chart_start,
        chart_end,
        warmup_days,
        include_review,
    )

    unzoned = sum(
        1
        for activity in display_activities
        if activity.type in RUN_TYPES
        and (activity.duration_s or 0) > 0
        and not activity.pace_zone_times
    )
    print_count_note(
        unzoned,
        "activity",
        "activities",
        "no pace zone data (shown as unzoned)",
    )

    weeks = weekly_time_by_zone(
        display_activities,
        chart_start,
        chart_end,
        zone_count=zones,
    )
    events = source.events(chart_start, planned_chart_end)

    points = time_averages(
        activities,
        chart_start,
        chart_end,
        windows=windows,
        warmup_days=warmup_days,
        events=events,
        projected_end=planned_chart_end,
        projection_start=end,
    )
    zone_window_days = getattr(windows, zone_window)
    zone_points = zone_time_averages(
        activities,
        chart_start,
        chart_end,
        window_days=zone_window_days,
        warmup_days=warmup_days,
        zone_count=zones,
    )
    planned_zone_weeks = weekly_planned_time_by_zone(
        events,
        chart_start,
        planned_chart_end,
        kind=TIME_ZONE_KIND,
        zone_count=zones,
    )
    planned_zone_label = _planned_zone_label({TIME_ZONE_KIND})

    path = plot_time(
        weeks,
        output=output,
        time_points=points,
        planned_time=weekly_planned_time(
            events,
            chart_start,
            planned_chart_end,
        ),
        planned_zone_weeks=planned_zone_weeks,
        planned_zone_label=planned_zone_label,
        zone_points=zone_points,
        zone_window_days=zone_window_days,
        windows=windows,
    )

    print(path)


def run_recovery_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    window_days: int,
    *,
    planned_end: date | None = None,
) -> None:
    """Render HRV, resting HR, and sleep trends."""
    from .analysis import planned_workout_dates, recovery_trends
    from .charts import plot_recovery

    planned_end = planned_end or end
    wellness = source.wellness(
        start - timedelta(days=window_days - 1),
        end,
    )
    points = recovery_trends(
        wellness,
        start,
        end,
        window_days=window_days,
    )

    events = source.events(start, planned_end)

    path = plot_recovery(
        points,
        output=output,
        planned_dates=planned_workout_dates(events, start, planned_end),
        window_days=window_days,
    )

    print(path)


def run_subt_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    *,
    include_review: bool = False,
) -> None:
    """Render subT and LT1 work interval pace and HR for the given range."""
    from .analysis import (
        activity_sort_key,
        is_lt1_activity,
        is_subt_activity,
        subt_session_point,
    )
    from .charts import plot_subt

    activities = reviewed_range(
        source,
        start,
        end,
        include_review,
    )
    activities = sorted(activities, key=activity_sort_key)

    points = []

    for activity in activities:
        if is_lt1_activity(activity):
            category = "lt1"
        elif is_subt_activity(activity):
            category = None
        else:
            continue

        point = subt_session_point(
            activity,
            source.activity_intervals(activity.id),
            category=category,
        )
        if point is not None:
            points.append(point)

    path = plot_subt(points, output=output)

    print(path)


def run_load_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    windows: AverageWindows,
    *,
    planned_end: date | None = None,
    include_review: bool = False,
) -> None:
    """Render daily load and its base/fitness/fatigue EWMA lines."""
    from .analysis import (
        average_warmup_days,
        daily_planned_load,
        load_metrics,
    )
    from .charts import plot_load

    planned_end = planned_end or end
    warmup_days = average_warmup_days(windows)

    display_activities, activities = warmup_reviewed(
        source,
        start,
        end,
        warmup_days,
        include_review,
    )

    missing_load = sum(
        1
        for activity in display_activities
        if activity.training_load is None
    )
    print_count_note(
        missing_load,
        "activity",
        "activities",
        "no training load (treated as 0)",
    )

    events = source.events(start, planned_end)

    points = load_metrics(
        activities,
        start,
        end,
        windows=windows,
        warmup_days=warmup_days,
        events=events,
        projected_end=planned_end,
    )

    path = plot_load(
        points,
        output=output,
        planned_load=daily_planned_load(events, start, planned_end),
        windows=windows,
    )
    print(path)


def run_volume_command(parsed, source, include_review):
    output, start, end, planned_end, windows = parsed
    run_volume_chart(
        output,
        start,
        end,
        source,
        windows,
        planned_end=planned_end,
        include_review=include_review,
    )
    return None


def run_load_command(parsed, source, include_review):
    output, start, end, planned_end, windows = parsed
    run_load_chart(
        output,
        start,
        end,
        source,
        windows,
        planned_end=planned_end,
        include_review=include_review,
    )
    return None


def run_time_command(parsed, source, include_review):
    (
        output,
        start,
        end,
        planned_end,
        windows,
        zones,
        zone_window,
    ) = parsed
    run_time_chart(
        output,
        start,
        end,
        source,
        windows,
        zones,
        zone_window,
        planned_end=planned_end,
        include_review=include_review,
    )
    return None


def run_recovery_command(parsed, source, include_review):
    """Recovery has a trailing scalars argument, so no positional forwarding."""
    output, start, end, planned_end, window_days = parsed
    run_recovery_chart(
        output,
        start,
        end,
        source,
        window_days,
        planned_end=planned_end,
    )
    return None


def run_subt_command(parsed, source, include_review):
    output, start, end = parsed
    run_subt_chart(
        output,
        start,
        end,
        source,
        include_review=include_review,
    )
    return None
