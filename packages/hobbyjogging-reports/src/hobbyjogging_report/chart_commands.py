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
    include_review: bool = False,
) -> None:
    """Render weekly running volume with distance-average lines."""
    from .analysis import (
        average_warmup_days,
        distance_averages,
        week_bounds,
        weekly_run_distance,
    )
    from .charts import plot_volume

    chart_start, chart_end = week_bounds(start, end)
    warmup_days = average_warmup_days(windows)

    display_activities, activities = warmup_reviewed(
        source,
        chart_start,
        chart_end,
        warmup_days,
        include_review,
    )

    points = distance_averages(
        activities,
        chart_start,
        chart_end,
        windows=windows,
        warmup_days=warmup_days,
    )

    path = plot_volume(
        weekly_run_distance(display_activities),
        output=output,
        distance_points=points,
        windows=windows,
        ylabel="km / week",
    )

    print(path)


def run_time_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    windows: AverageWindows,
    zones: int,
    zone_window: str,
    *,
    include_review: bool = False,
) -> None:
    """Render weekly running time stacked by HR zone."""
    from .analysis import (
        RUN_TYPES,
        average_warmup_days,
        time_averages,
        week_bounds,
        weekly_time_by_zone,
        zone_time_averages,
    )
    from .charts import plot_time

    chart_start, chart_end = week_bounds(start, end)
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
        and not activity.hr_zone_times
    )
    print_count_note(
        unzoned,
        "activity",
        "activities",
        "no HR zone data (shown as unzoned)",
    )

    weeks = weekly_time_by_zone(
        display_activities,
        chart_start,
        chart_end,
        zone_count=zones,
    )
    points = time_averages(
        activities,
        chart_start,
        chart_end,
        windows=windows,
        warmup_days=warmup_days,
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

    path = plot_time(
        weeks,
        output=output,
        time_points=points,
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
) -> None:
    """Render HRV, resting HR, and sleep trends."""
    from .analysis import recovery_trends
    from .charts import plot_recovery

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

    path = plot_recovery(
        points,
        output=output,
        window_days=window_days,
    )

    print(path)


def run_subt_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    heart_rate: bool = False,
    *,
    include_review: bool = False,
) -> None:
    """Render subT and LT1 work interval pace or HR for the given range."""
    from .analysis import (
        activity_sort_key,
        is_lt1_activity,
        is_subt_activity,
        subt_session_point,
    )
    from .charts import plot_subt_hr, plot_subt_paces

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

    plot = plot_subt_hr if heart_rate else plot_subt_paces
    path = plot(points, output=output)

    print(path)


def run_load_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    windows: AverageWindows,
    *,
    include_review: bool = False,
) -> None:
    """Render daily load and its base/fitness/fatigue EWMA lines."""
    from .analysis import average_warmup_days, load_metrics
    from .charts import plot_load

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

    points = load_metrics(
        activities,
        start,
        end,
        windows=windows,
        warmup_days=warmup_days,
    )

    path = plot_load(points, output=output, windows=windows)
    print(path)


def run_recovery_command(parsed, source, include_review):
    """Recovery has a trailing scalars argument, so no positional forwarding."""
    output, start, end, window_days = parsed
    run_recovery_chart(
        output,
        start,
        end,
        source,
        window_days,
    )
    return None


def run_volume_command(parsed, source, include_review):
    output, start, end, windows = parsed
    run_volume_chart(
        output,
        start,
        end,
        source,
        windows,
        include_review=include_review,
    )
    return None


def run_load_command(parsed, source, include_review):
    output, start, end, windows = parsed
    run_load_chart(
        output,
        start,
        end,
        source,
        windows,
        include_review=include_review,
    )
    return None


def run_time_command(parsed, source, include_review):
    output, start, end, windows, zones, zone_window = parsed
    run_time_chart(
        output,
        start,
        end,
        source,
        windows,
        zones,
        zone_window,
        include_review=include_review,
    )
    return None


def run_recovery_command(parsed, source, include_review):
    output, start, end, window_days = parsed
    run_recovery_chart(
        output,
        start,
        end,
        source,
        window_days,
    )
    return None


def run_subt_pace_command(parsed, source, include_review):
    output, start, end = parsed
    run_subt_chart(
        output,
        start,
        end,
        source,
        heart_rate=False,
        include_review=include_review,
    )
    return None


def run_subt_hr_command(parsed, source, include_review):
    output, start, end = parsed
    run_subt_chart(
        output,
        start,
        end,
        source,
        heart_rate=True,
        include_review=include_review,
    )
    return None
