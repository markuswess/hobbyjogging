import sys
from datetime import date

from .cli import (
    parse_chart_args,
    parse_classify_args,
    parse_report_args,
)
from .reports import (
    daily,
    debug,
    period_report,
    session_report,
    summary,
)


def run_chart(output: str, start: date, end: date) -> None:
    """Render a weekly running distance chart for the given range."""
    from .analysis import weekly_run_distance
    from .charts import plot_weekly_bars
    from .sources.intervals_api import IntervalsSource

    activities = IntervalsSource().activities(start, end)

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
    heart_rate: bool = False,
) -> None:
    """Render subT and LT1 work interval pace or HR for the given range."""
    from .analysis import (
        is_lt1_activity,
        is_subt_activity,
        subt_session_point,
    )
    from .charts import plot_subt_hr, plot_subt_paces
    from .sources.intervals_api import IntervalsSource

    source = IntervalsSource()
    activities = source.activities(start, end)

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


def run_classify(start: date, end: date) -> None:
    """Print the category of activities in the given range."""
    from .analysis import is_subt_activity
    from .classify import classify
    from .sources.intervals_api import IntervalsSource

    source = IntervalsSource()
    activities = source.activities(start, end)

    for activity in sorted(activities, key=lambda a: a.date):
        intervals = []

        if is_subt_activity(activity):
            intervals = source.activity_intervals(activity.id)

        category = classify(activity, intervals)

        print(
            f"{activity.date} "
            f"{activity.duration_s / 60:5.0f}min "
            f"rpe={activity.rpe} "
            f"{category.path:36s} "
            f"{activity.name}"
        )


def main():
    mode = sys.argv[1]

    if mode == "daily":
        report = daily()

    elif mode == "all":
        report = daily()
        report += "\n\n"
        report += summary("weekly")
        report += "\n\n"
        report += summary("monthly")
        report += "\n\n"
        report += summary("yearly")

    elif mode in ("weekly", "monthly", "yearly"):
        report = summary(mode)

    elif mode == "session":
        if len(sys.argv) < 3:
            raise SystemExit(
                "usage: python -m intervals_report session YYYY-MM-DD"
            )

        try:
            day = date.fromisoformat(sys.argv[2])
        except ValueError:
            raise SystemExit(
                "usage: python -m intervals_report session YYYY-MM-DD"
            )

        report = session_report(day)

    elif mode == "debug":
        debug()
        sys.exit(0)

    elif mode == "report":
        try:
            start, end = parse_report_args(sys.argv[2:])
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        report = period_report(start, end, "Custom Training Report")

    elif mode == "chart":
        try:
            output, start, end = parse_chart_args(
                sys.argv[2:],
                default_output="chart.png",
                default_days=90,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        run_chart(output, start, end)
        sys.exit(0)

    elif mode in ("subt-chart", "subt-hr-chart"):
        is_hr_chart = mode == "subt-hr-chart"
        default_output = (
            "subt-hr-chart.png" if is_hr_chart else "subt-chart.png"
        )

        try:
            output, start, end = parse_chart_args(
                sys.argv[2:],
                default_output=default_output,
                default_days=365,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        run_subt_chart(
            output,
            start,
            end,
            heart_rate=is_hr_chart,
        )
        sys.exit(0)

    elif mode == "classify":
        try:
            start, end = parse_classify_args(sys.argv[2:])
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        run_classify(start, end)
        sys.exit(0)

    else:
        raise SystemExit(
            "usage: python -m intervals_report "
            "daily|weekly|monthly|yearly|debug|all"
            "|session YYYY-MM-DD|report [--days N]"
            "|chart [output.png]"
            "|subt-chart [output.png]|subt-hr-chart [output.png]"
            "|classify [days]"
            "\n       date ranges: [--days N] [--from YYYY-MM-DD] "
            "[--to YYYY-MM-DD]"
        )

    print(report)


if __name__ == "__main__":
    main()
