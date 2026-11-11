"""Report command handlers."""

from .activity_list import activities_report
from .command_support import reviewed_range
from .compare import compare_report
from .daily import daily
from .dashboard import build_dashboard
from .debug import debug
from .overview import overview_report
from .period_report import period_report, summary
from .planned import planned_report
from .recovery_report import recovery_report
from .subt_ewma_report import subt_ewma_report
from .subt_report import subt_report
from .sessions import session_report


def run_daily_command(parsed, source, include_review):
    return daily(source, include_review=include_review)


def run_overview_command(parsed, source, include_review):
    future_days, today = parsed
    return overview_report(
        source,
        future_days=future_days,
        today=today,
        include_review=include_review,
    )


def summary_handler(period):
    def run(parsed, source, include_review):
        return summary(
            period,
            source,
            include_review=include_review,
        )

    return run


def run_all_command(parsed, source, include_review):
    report = daily(source, include_review=include_review)
    report += "\n\n"
    report += summary("weekly", source, include_review=include_review)
    report += "\n\n"
    report += summary("monthly", source, include_review=include_review)
    report += "\n\n"
    report += summary("yearly", source, include_review=include_review)
    return report


def run_session_command(parsed, source, include_review):
    return session_report(
        parsed,
        source,
        include_review=include_review,
    )


def run_report_command(parsed, source, include_review):
    start, end = parsed
    return period_report(
        start,
        end,
        "Custom Training Report",
        source,
        include_review=include_review,
    )


def run_compare_command(parsed, source, include_review):
    mode, start, end = parsed
    return compare_report(
        mode,
        start,
        end,
        source,
        include_review=include_review,
    )


def run_dashboard_command(parsed, source, include_review):
    (
        output,
        days,
        activity_limit,
        chart_days,
        future_days,
        recovery_days,
        analysis_days,
        reports,
    ) = parsed
    path = build_dashboard(
        source,
        output,
        days=days,
        activity_limit=activity_limit,
        chart_days=chart_days,
        future_days=future_days,
        recovery_days=recovery_days,
        analysis_days=analysis_days,
        reports=reports,
        include_review=include_review,
    )
    print(path)
    return None


def run_subt_report_command(parsed, source, include_review):
    start, end = parsed
    return subt_report(
        start,
        end,
        "subT Report",
        source,
        include_review=include_review,
    )


def run_recovery_report_command(parsed, source, include_review):
    return recovery_report(source)


def run_subt_ewma_report_command(parsed, source, include_review):
    return subt_ewma_report(source, include_review=include_review)


def run_planned_command(parsed, source, include_review):
    start, end = parsed
    return planned_report(start, end, source)


def run_classify_command(parsed, source, include_review):
    """Print the category of activities in the given range."""
    from .analysis import activity_sort_key, is_subt_activity
    from .classify import classify

    start, end = parsed
    activities = reviewed_range(
        source,
        start,
        end,
        include_review,
    )

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

    return None


def run_debug_command(parsed, source, include_review):
    debug(parsed or "all")
    return None


def run_activities_command(parsed, source, include_review):
    return activities_report(
        source,
        parsed,
        include_review=include_review,
    )
