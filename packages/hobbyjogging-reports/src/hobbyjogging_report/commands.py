"""Command registry and handlers for the report CLI."""

from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial
from typing import Callable

from hobbyjogging_core.datasource import DataSource

from .cli import (
    parse_chart_args,
    parse_classify_args,
    parse_load_args,
    parse_recovery_args,
    parse_report_args,
    parse_time_args,
)
from .model import AverageWindows
from .reports import (
    daily,
    debug,
    period_report,
    session_report,
    subt_report,
    summary,
)
from .review import exclude_review, review_note


@dataclass(frozen=True)
class Command:
    """One CLI command: help text, optional parser, and handler."""

    name: str
    summary: str
    usage: str
    examples: tuple[str, ...] = ()
    parse: Callable[[list[str]], object] | None = None
    run: Callable[[object, DataSource | None, bool], str | None] = None
    needs_source: bool = True


def _print_missing_load_note(activities) -> None:
    missing_load = sum(
        1
        for activity in activities
        if activity.training_load is None
    )

    if not missing_load:
        return

    unit = "activity" if missing_load == 1 else "activities"
    verb = "has" if missing_load == 1 else "have"

    print(
        f"note: {missing_load} {unit} {verb} no training load "
        "(treated as 0)"
    )


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
        distance_averages,
        average_warmup_days,
        week_bounds,
        weekly_run_distance,
    )
    from .charts import plot_volume

    chart_start, chart_end = week_bounds(start, end)
    warmup_days = average_warmup_days(windows)
    warm_start = chart_start - timedelta(days=warmup_days)

    all_activities = source.activities(warm_start, chart_end)

    display_activities, excluded = exclude_review(
        [
            activity
            for activity in all_activities
            if chart_start <= activity.date <= chart_end
        ],
        include_review=include_review,
    )

    note = review_note(excluded)
    if note:
        print(f"note: {note}")

    activities, _ = exclude_review(
        all_activities,
        include_review=include_review,
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
    warm_start = chart_start - timedelta(days=warmup_days)

    all_activities = source.activities(warm_start, chart_end)

    display_activities, excluded = exclude_review(
        [
            activity
            for activity in all_activities
            if chart_start <= activity.date <= chart_end
        ],
        include_review=include_review,
    )

    note = review_note(excluded)
    if note:
        print(f"note: {note}")

    unzoned = sum(
        1
        for activity in display_activities
        if activity.type in RUN_TYPES
        and (activity.duration_s or 0) > 0
        and not activity.hr_zone_times
    )
    if unzoned:
        unit = "activity" if unzoned == 1 else "activities"
        verb = "has" if unzoned == 1 else "have"
        print(
            f"note: {unzoned} {unit} {verb} no HR zone data "
            "(shown as unzoned)"
        )

    activities, _ = exclude_review(
        all_activities,
        include_review=include_review,
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

    activities, excluded = exclude_review(
        source.activities(start, end),
        include_review=include_review,
    )
    activities = sorted(activities, key=activity_sort_key)

    note = review_note(excluded)
    if note:
        print(f"note: {note}")

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
    from .analysis import load_metrics, average_warmup_days
    from .charts import plot_load

    warmup_days = average_warmup_days(windows)
    warm_start = start - timedelta(days=warmup_days)

    all_activities = source.activities(warm_start, end)

    display_activities, excluded = exclude_review(
        [
            activity
            for activity in all_activities
            if start <= activity.date <= end
        ],
        include_review=include_review,
    )

    note = review_note(excluded)
    if note:
        print(f"note: {note}")

    _print_missing_load_note(display_activities)

    activities, _ = exclude_review(
        all_activities,
        include_review=include_review,
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


def run_classify(
    start: date,
    end: date,
    source: DataSource,
    *,
    include_review: bool = False,
) -> None:
    """Print the category of activities in the given range."""
    from .analysis import activity_sort_key, is_subt_activity
    from .classify import classify

    activities, excluded = exclude_review(
        source.activities(start, end),
        include_review=include_review,
    )

    note = review_note(excluded)
    if note:
        print(f"note: {note}")

    for activity in sorted(activities, key=activity_sort_key):
        intervals = []

        if is_subt_activity(activity):
            intervals = source.activity_intervals(activity.id)

        category = classify(activity, intervals)
        rpe = "-" if activity.rpe is None else f"{activity.rpe:g}"

        print(
            f"{activity.date} "
            f"{activity.duration_s / 60:5.0f}min "
            f"rpe={rpe} "
            f"{category.path:36s} "
            f"{activity.name}"
        )


# --- handlers -------------------------------------------------------------


def _run_daily(parsed, source, include_review):
    return daily(source, include_review=include_review)


def _summary_handler(period):
    def run(parsed, source, include_review):
        return summary(
            period,
            source,
            include_review=include_review,
        )

    return run


def _run_all(parsed, source, include_review):
    report = daily(source, include_review=include_review)
    report += "\n\n"
    report += summary("weekly", source, include_review=include_review)
    report += "\n\n"
    report += summary("monthly", source, include_review=include_review)
    report += "\n\n"
    report += summary("yearly", source, include_review=include_review)
    return report


def _run_session(parsed, source, include_review):
    return session_report(
        parsed,
        source,
        include_review=include_review,
    )


def _run_report(parsed, source, include_review):
    start, end = parsed
    return period_report(
        start,
        end,
        "Custom Training Report",
        source,
        include_review=include_review,
    )


def _run_subt_report(parsed, source, include_review):
    start, end = parsed
    return subt_report(
        start,
        end,
        "subT Report",
        source,
        include_review=include_review,
    )


def _run_classify(parsed, source, include_review):
    start, end = parsed
    run_classify(
        start,
        end,
        source,
        include_review=include_review,
    )
    return None


def _run_volume(parsed, source, include_review):
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


def _run_load(parsed, source, include_review):
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


def _run_time(parsed, source, include_review):
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


def _run_recovery(parsed, source, include_review):
    output, start, end, window_days = parsed
    run_recovery_chart(
        output,
        start,
        end,
        source,
        window_days,
    )
    return None


def _run_subt_pace(parsed, source, include_review):
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


def _run_subt_hr(parsed, source, include_review):
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


def _run_debug(parsed, source, include_review):
    debug(parsed or "all")
    return None


def _parse_session(argv: list[str]):
    if len(argv) > 1:
        raise ValueError(
            "usage: python -m hobbyjogging_report session "
            "[YYYY-MM-DD|ACTIVITY_ID|last]"
        )
    return argv[0] if argv else None


def _parse_debug(argv: list[str]):
    if len(argv) > 1:
        raise ValueError(
            "usage: python -m hobbyjogging_report debug "
            "[activities|wellness|events|intervals]"
        )
    return argv[0] if argv else "all"


COMMANDS = {
    "daily": Command(
        "daily",
        "Daily training report",
        "daily",
        ("reports.sh", "reports.sh daily"),
        run=_run_daily,
    ),
    "weekly": Command(
        "weekly",
        "Weekly training report",
        "weekly",
        ("reports.sh weekly",),
        run=_summary_handler("weekly"),
    ),
    "monthly": Command(
        "monthly",
        "Monthly training report",
        "monthly",
        ("reports.sh monthly",),
        run=_summary_handler("monthly"),
    ),
    "yearly": Command(
        "yearly",
        "Yearly training report",
        "yearly",
        ("reports.sh yearly",),
        run=_summary_handler("yearly"),
    ),
    "all": Command(
        "all",
        "Daily, weekly, monthly, and yearly reports",
        "all",
        ("reports.sh all",),
        run=_run_all,
    ),
    "report": Command(
        "report",
        "Custom range report",
        "report [--days N] [--from DATE] [--to DATE]",
        (
            "reports.sh report --days 90",
            "reports.sh report --from 2026-01-01 --to 2026-03-31",
        ),
        parse=parse_report_args,
        run=_run_report,
    ),
    "subt-report": Command(
        "subt-report",
        "subT and LT1 work-block report",
        "subt-report [--days N] [--from DATE] [--to DATE]",
        ("reports.sh subt-report --days 90",),
        parse=partial(parse_report_args, default_days=90),
        run=_run_subt_report,
    ),
    "session": Command(
        "session",
        "Detailed single-session report",
        "session [YYYY-MM-DD|ACTIVITY_ID|last]",
        (
            "reports.sh session",
            "reports.sh session last",
            "reports.sh session 2026-10-22",
            "reports.sh session <activity-id>",
        ),
        parse=_parse_session,
        run=_run_session,
    ),
    "classify": Command(
        "classify",
        "Print workout categories",
        "classify [days] [--days N] [--from DATE] [--to DATE]",
        ("reports.sh classify", "reports.sh classify --days 90"),
        parse=parse_classify_args,
        run=_run_classify,
    ),
    "volume": Command(
        "volume",
        "Weekly running volume and distance averages",
        "volume [output.png] [--days N] [--from DATE] [--to DATE] "
        "[--base-days N] [--fitness-days N] [--fatigue-days N]",
        ("charts.sh volume --days 90",),
        parse=partial(
            parse_load_args,
            default_output="volume.png",
            default_days=90,
        ),
        run=_run_volume,
    ),
    "load": Command(
        "load",
        "Daily load with base, fitness, and fatigue averages",
        "load [output.png] [--days N] [--from DATE] [--to DATE] "
        "[--base-days N] [--fitness-days N] [--fatigue-days N]",
        ("charts.sh load --days 180",),
        parse=partial(
            parse_load_args,
            default_output="load.png",
            default_days=180,
        ),
        run=_run_load,
    ),
    "time": Command(
        "time",
        "Weekly running time stacked by HR zone",
        "time [output.png] [--days N] [--from DATE] [--to DATE] "
        "[--zones N] [--zone-window base|fitness|fatigue]",
        (
            "charts.sh time --days 90",
            "charts.sh time --zones 4 --zone-window base",
        ),
        parse=partial(
            parse_time_args,
            default_output="time.png",
            default_days=90,
        ),
        run=_run_time,
    ),
    "recovery": Command(
        "recovery",
        "HRV, resting HR, and sleep trends",
        "recovery [output.png] [--days N] [--from DATE] [--to DATE] "
        "[--window N]",
        (
            "charts.sh recovery --days 90",
            "charts.sh recovery --window 14",
        ),
        parse=partial(
            parse_recovery_args,
            default_output="recovery.png",
            default_days=90,
        ),
        run=_run_recovery,
    ),
    "subt-pace": Command(
        "subt-pace",
        "subT and LT1 work-interval pace chart",
        "subt-pace [output.png] [--days N] [--from DATE] [--to DATE]",
        ("charts.sh subt-pace --days 365",),
        parse=partial(
            parse_chart_args,
            default_output="subt-pace.png",
            default_days=365,
        ),
        run=_run_subt_pace,
    ),
    "subt-hr": Command(
        "subt-hr",
        "subT and LT1 work-interval HR chart",
        "subt-hr [output.png] [--days N] [--from DATE] [--to DATE]",
        ("charts.sh subt-hr --days 365",),
        parse=partial(
            parse_chart_args,
            default_output="subt-hr.png",
            default_days=365,
        ),
        run=_run_subt_hr,
    ),
    "debug": Command(
        "debug",
        "Dump raw Intervals.icu payloads",
        "debug [activities|wellness|events|intervals|all]",
        ("python -m hobbyjogging_report debug activities",),
        parse=_parse_debug,
        run=_run_debug,
        needs_source=False,
    ),
}


def usage() -> str:
    """Return the global CLI usage text."""
    lines = [
        "usage: python -m hobbyjogging_report "
        "[--source database|intervals] <command> [args...]",
        "",
        "commands:",
    ]

    for command in COMMANDS.values():
        lines.append(f"  {command.name:<14} {command.summary}")

    lines.extend([
        "",
        "date ranges: --days N, --from YYYY-MM-DD, --to YYYY-MM-DD",
        "source: --source database (default) or --source intervals",
        "--include-review: show activities with open review items",
        "",
        "Use '<command> --help' for command-specific help.",
    ])

    return "\n".join(lines)


def command_help(command: Command) -> str:
    """Return per-command help text."""
    lines = [
        f"usage: python -m hobbyjogging_report {command.usage}",
        "",
        command.summary,
    ]

    if command.examples:
        lines.extend(["", "examples:"])
        lines.extend(f"  {example}" for example in command.examples)

    if command.needs_source:
        lines.extend([
            "",
            "global options:",
            "  --source database|intervals",
            "  --include-review",
        ])
    else:
        lines.extend([
            "",
            "requires INTERVALS_ATHLETE_ID and INTERVALS_API_KEY",
        ])

    return "\n".join(lines)
