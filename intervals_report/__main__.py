import sys

from .reports import daily, debug, summary


def run_chart(output: str) -> None:
    """Render a weekly running distance chart for the last 90 days."""
    from datetime import date, timedelta

    from .analysis import weekly_run_distance
    from .charts import plot_weekly_bars
    from .sources.intervals_api import IntervalsSource

    end = date.today()
    start = end - timedelta(days=90)

    activities = IntervalsSource().activities(start, end)

    path = plot_weekly_bars(
        weekly_run_distance(activities),
        ylabel="km",
        output=output,
        title="Weekly running distance",
    )

    print(path)


def run_subt_chart(output: str) -> None:
    """Render subT work interval paces for the last 365 days."""
    from datetime import date, timedelta

    from .analysis import is_subt_activity, subt_work_points
    from .charts import plot_subt_paces
    from .sources.intervals_api import IntervalsSource

    end = date.today()
    start = end - timedelta(days=365)

    source = IntervalsSource()
    activities = source.activities(start, end)

    points = []

    for activity in activities:
        if is_subt_activity(activity):
            points.extend(
                subt_work_points(
                    activity,
                    source.activity_intervals(activity.id),
                )
            )

    path = plot_subt_paces(points, output=output)

    print(path)


def run_classify(days: int = 30) -> None:
    """Print the category of recent activities."""
    from datetime import date, timedelta

    from .analysis import is_subt_activity
    from .classify import classify
    from .sources.intervals_api import IntervalsSource

    end = date.today()
    start = end - timedelta(days=days)

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

    elif mode == "debug":
        debug()
        sys.exit(0)

    elif mode == "chart":
        run_chart(sys.argv[2] if len(sys.argv) > 2 else "chart.png")
        sys.exit(0)

    elif mode == "subt-chart":
        run_subt_chart(
            sys.argv[2] if len(sys.argv) > 2 else "subt-chart.png"
        )
        sys.exit(0)

    elif mode == "classify":
        run_classify(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
        sys.exit(0)

    else:
        raise SystemExit(
            "usage: python -m intervals_report "
            "daily|weekly|monthly|yearly|debug|all"
            "|chart [output.png]|subt-chart [output.png]|classify [days]"
        )

    print(report)


if __name__ == "__main__":
    main()
