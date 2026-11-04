import os
import sys
from datetime import date

from hobbyjogging_core.datasource import DataSource

from .cli import (
    extract_source,
    parse_chart_args,
    parse_classify_args,
    parse_report_args,
)
from .mdpretty import render_markdown
from .review import exclude_review, review_note
from .reports import (
    daily,
    debug,
    period_report,
    session_report,
    subt_report,
    summary,
)
from .sources import create_source

MODES = {
    "daily",
    "weekly",
    "monthly",
    "yearly",
    "all",
    "report",
    "subt-report",
    "session",
    "chart",
    "subt-chart",
    "subt-hr-chart",
    "classify",
}


def usage() -> str:
    return (
        "usage: python -m hobbyjogging_report "
        "[--source database|intervals] "
        "daily|weekly|monthly|yearly|debug|all"
        "|session [YYYY-MM-DD|ACTIVITY_ID|last]|report [--days N]"
        "|subt-report [--days N]"
        "|chart [output.png]"
        "|subt-chart [output.png]|subt-hr-chart [output.png]"
        "|classify [days]"
        "\n       date ranges: [--days N] [--from YYYY-MM-DD] "
        "[--to YYYY-MM-DD]"
        "\n       source: --source database (default) or --source intervals"
        "\n       --include-review: show activities with open review items"
    )


def run_chart(
    output: str,
    start: date,
    end: date,
    source: DataSource,
    *,
    include_review: bool = False,
) -> None:
    """Render a weekly running distance chart for the given range."""
    from .analysis import weekly_run_distance
    from .charts import plot_weekly_bars

    activities, excluded = exclude_review(
        source.activities(start, end),
        include_review=include_review,
    )

    note = review_note(excluded)
    if note:
        print(f"note: {note}")

    path = plot_weekly_bars(
        weekly_run_distance(activities),
        ylabel="km",
        output=output,
        title="Weekly running distance",
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


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    source_name, include_review, argv = extract_source(argv)

    mode = argv[0] if argv else "daily"
    args = argv[1:]

    if mode in ("-h", "--help"):
        print(usage())
        return

    if mode == "debug":
        debug()
        return

    if mode not in MODES:
        raise SystemExit(usage())

    try:
        source = create_source(source_name)
    except Exception as exc:
        raise SystemExit(
            f"could not open {source_name} source: {exc}"
        ) from exc

    with source:
        if mode == "daily":
            report = daily(source, include_review=include_review)

        elif mode == "all":
            report = daily(source, include_review=include_review)
            report += "\n\n"
            report += summary("weekly", source, include_review=include_review)
            report += "\n\n"
            report += summary("monthly", source, include_review=include_review)
            report += "\n\n"
            report += summary("yearly", source, include_review=include_review)

        elif mode in ("weekly", "monthly", "yearly"):
            report = summary(mode, source, include_review=include_review)

        elif mode == "session":
            if len(args) > 1:
                raise SystemExit(
                    "usage: python -m hobbyjogging_report session "
                    "[YYYY-MM-DD|ACTIVITY_ID|last]"
                )

            report = session_report(
                args[0] if args else None,
                source,
                include_review=include_review,
            )

        elif mode == "report":
            try:
                start, end = parse_report_args(args)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc

            report = period_report(
                start,
                end,
                "Custom Training Report",
                source,
                include_review=include_review,
            )

        elif mode == "subt-report":
            try:
                start, end = parse_report_args(args, default_days=90)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc

            report = subt_report(
                start,
                end,
                "subT Report",
                source,
                include_review=include_review,
            )

        elif mode == "chart":
            try:
                output, start, end = parse_chart_args(
                    args,
                    default_output="chart.png",
                    default_days=90,
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc

            run_chart(
                output,
                start,
                end,
                source,
                include_review=include_review,
            )
            return

        elif mode in ("subt-chart", "subt-hr-chart"):
            is_hr_chart = mode == "subt-hr-chart"
            default_output = (
                "subt-hr-chart.png" if is_hr_chart else "subt-chart.png"
            )

            try:
                output, start, end = parse_chart_args(
                    args,
                    default_output=default_output,
                    default_days=365,
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc

            run_subt_chart(
                output,
                start,
                end,
                source,
                heart_rate=is_hr_chart,
                include_review=include_review,
            )
            return

        elif mode == "classify":
            try:
                start, end = parse_classify_args(args)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc

            run_classify(
                start,
                end,
                source,
                include_review=include_review,
            )
            return

    if sys.stdout.isatty() and os.environ.get("NO_PRETTY") != "1":
        print(render_markdown(report))
    else:
        print(report)


if __name__ == "__main__":
    main()
