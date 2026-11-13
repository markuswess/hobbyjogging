"""Chart command handlers."""

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .command_support import (
    activity_start,
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
    hard_points = time_averages(
        activities,
        chart_start,
        chart_end,
        windows=windows,
        warmup_days=warmup_days,
        zones=(3, 4),
    )
    zone_window_days = getattr(windows, zone_window)
    zone_points = zone_time_averages(
        activities,
        chart_start,
        chart_end,
        window_days=zone_window_days,
        warmup_days=warmup_days,
        zone_count=zones,
        events=events,
        projected_end=planned_chart_end,
        projection_start=end,
        kind=TIME_ZONE_KIND,
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
        hard_points=hard_points,
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
    baseline_start = end - timedelta(days=364)
    wellness = source.wellness(
        baseline_start - timedelta(days=window_days - 1),
        end,
    )
    baseline_points = recovery_trends(
        wellness,
        baseline_start,
        end,
        window_days=window_days,
    )
    points = [
        point
        for point in baseline_points
        if start <= point.date <= end
    ]

    events = source.events(end, planned_end)

    path = plot_recovery(
        points,
        output=output,
        planned_dates=planned_workout_dates(events, end, planned_end),
        window_days=window_days,
        baseline_points=baseline_points,
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
    from .charts import plot_subt
    from .command_support import subt_session_points

    activities = reviewed_range(
        source,
        start,
        end,
        include_review,
    )
    points = subt_session_points(source, activities)

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
        rpe_metrics,
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
        rpe_points=rpe_metrics(
            activities,
            start,
            end,
            windows=windows,
            warmup_days=warmup_days,
        ),
    )
    print(path)


def run_vo2max_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    *,
    include_review: bool = False,
) -> None:
    """Render Garmin running VO2max with 7- and 42-day EWMA lines."""
    from .analysis import RUN_TYPES, VO2MAX_WARMUP_DAYS, vo2max_points
    from .charts import plot_vo2max

    display_activities, activities = warmup_reviewed(
        source,
        start,
        end,
        VO2MAX_WARMUP_DAYS,
        include_review,
    )

    non_running = sum(
        1
        for activity in display_activities
        if activity.type not in RUN_TYPES and activity.vo2max_garmin
    )
    print_count_note(
        non_running,
        "activity",
        "activities",
        "non-running Garmin VO2max (ignored)",
    )

    points = vo2max_points(activities, start, end)

    path = plot_vo2max(points, output=output)
    print(path)


def run_overview_chart(
    output: str,
    today: date,
    source: DataSource,
    chart_days: int = 70,
    future_days: int = 14,
    *,
    include_review: bool = False,
) -> None:
    """Render the main overview chart as a PNG."""
    from .analysis import average_warmup_days, vo2max_points
    from .charts import plot_overview
    from .zone_groups import (
        daily_zone_groups,
        planned_bars_without_actual,
        zone_group_series,
    )

    chart_start = today - timedelta(days=chart_days - 1)
    chart_end = today + timedelta(days=future_days)
    windows = AverageWindows()
    warmup_days = average_warmup_days(windows)
    _, activities = warmup_reviewed(
        source,
        chart_start,
        chart_end,
        warmup_days,
        include_review,
    )
    events = [
        event
        for event in source.events(today, chart_end)
        if event.type
    ]
    volume_bars = daily_zone_groups(activities, chart_start, today)
    planned_bars = planned_bars_without_actual(
        events,
        volume_bars,
        today,
        chart_end,
    )
    zone_series = zone_group_series(
        activities,
        events,
        chart_start - timedelta(days=warmup_days),
        chart_end,
        chart_start=chart_start,
        projection_start=today,
        windows=windows,
    )
    vo2max = vo2max_points(
        activities,
        chart_start - timedelta(days=warmup_days),
        chart_end,
    )

    path = plot_overview(
        volume_bars,
        planned_bars,
        zone_series,
        output=output,
        start=chart_start,
        end=chart_end,
        today=today,
        vo2max_points=vo2max,
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


def run_overview_chart_command(parsed, source, include_review):
    output, chart_days, future_days, today = parsed
    run_overview_chart(
        output,
        today,
        source,
        chart_days,
        future_days,
        include_review=include_review,
    )
    return None


def run_vo2max_command(parsed, source, include_review):
    output, start, end = parsed
    run_vo2max_chart(
        output,
        start,
        end,
        source,
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


def run_pace_hr_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    *,
    include_review: bool = False,
) -> None:
    """Render the per-run pace vs heart-rate scatter."""
    from .analysis import (
        EFFICIENCY_UNIT,
        RESTING_HR_WINDOW_DAYS,
        pace_hr_efficiency_lines,
        pace_hr_points,
        pace_hr_trends,
        resting_hr_baselines,
    )
    from .charts import plot_pace_hr

    activities = reviewed_range(source, start, end, include_review)
    wellness = source.wellness(
        start - timedelta(days=RESTING_HR_WINDOW_DAYS),
        end,
    )
    points = pace_hr_points(
        activities,
        start,
        end,
        resting_hr_baseline=resting_hr_baselines(wellness),
    )

    for trend in pace_hr_trends(points):
        print(
            f"note: {trend.label}: HR = {trend.intercept:.1f} + "
            f"{trend.slope:.2f}*speed, r={trend.correlation:.2f} "
            f"(n={trend.points})"
        )

    for line in pace_hr_efficiency_lines(points):
        print(
            f"note: {line.label} efficiency: E = {line.efficiency:.2f} "
            f"{EFFICIENCY_UNIT}, RHR {line.resting_hr:.0f} bpm "
            f"(n={line.points})"
        )

    path = plot_pace_hr(points, output=output)
    print(path)


def run_compare_chart(
    output: str,
    metric: str,
    window: int,
    today: date,
    source: DataSource,
    *,
    include_review: bool = False,
) -> None:
    """Render the year-over-year EWMA comparison chart."""
    from .analysis import compare_year_ewma, compare_year_planned_ewma
    from .charts import plot_compare
    from .command_support import resting_hr_lookup

    start = activity_start(source, today)
    activities = reviewed_range(source, start, today, include_review)
    events = source.events(start, today + timedelta(days=366))
    series = compare_year_ewma(
        activities,
        metric,
        window,
        today=today,
        resting_hr=resting_hr_lookup(source, start, today),
    )

    path = plot_compare(
        series,
        output=output,
        metric=metric,
        window=window,
        today=today,
        title=f"Year comparison — {metric}, {window}-day EWMA",
        planned_series=compare_year_planned_ewma(
            events,
            metric,
            window,
            today=today,
        ),
    )
    print(path)


def run_pace_hr_command(parsed, source, include_review):
    output, start, end = parsed
    run_pace_hr_chart(
        output,
        start,
        end,
        source,
        include_review=include_review,
    )
    return None


def run_compare_chart_command(parsed, source, include_review):
    output, metric, window, today = parsed
    run_compare_chart(
        output,
        metric,
        window,
        today,
        source,
        include_review=include_review,
    )
    return None
