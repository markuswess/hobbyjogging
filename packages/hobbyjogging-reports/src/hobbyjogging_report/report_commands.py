"""Report command handlers."""

from hobbyjogging_core.datasource import DataSource

from .activity_list import activities_report
from .command_support import reviewed_range
from .reports import (
    daily,
    debug,
    period_report,
    session_report,
    subt_report,
    summary,
)


def run_daily_command(parsed, source, include_review):
    return daily(source, include_review=include_review)


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


def run_subt_report_command(parsed, source, include_review):
    start, end = parsed
    return subt_report(
        start,
        end,
        "subT Report",
        source,
        include_review=include_review,
    )


def run_classify_command(parsed, source, include_review):
    start, end = parsed
    _run_classify(
        start,
        end,
        source,
        include_review=include_review,
    )
    return None


def _run_classify(
    start,
    end,
    source: DataSource,
    *,
    include_review: bool = False,
) -> None:
    """Print the category of activities in the given range."""
    from .analysis import activity_sort_key, is_subt_activity
    from .classify import classify

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


def run_debug_command(parsed, source, include_review):
    debug(parsed or "all")
    return None


def run_activities_command(parsed, source, include_review):
    return activities_report(
        source,
        parsed,
        include_review=include_review,
    )
