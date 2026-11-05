import os
import sys
from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .cli import (
    extract_source,
    parse_chart_args,
    parse_classify_args,
    parse_load_args,
    parse_report_args,
)
from .mdpretty import render_markdown
from .model import LoadWindows
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
    "volume",
    "subt-pace",
    "subt-hr",
    "load",
    "classify",
}


def usage() -> str:
    return (
        "usage: python -m hobbyjogging_report "
        "[--source database|intervals] "
        "daily|weekly|monthly|yearly|debug|all"
        "|session [YYYY-MM-DD|ACTIVITY_ID|last]|report [--days N]"
        "|subt-report [--days N]"
        "|volume [output.png]"
        "|subt-pace [output.png]|subt-hr [output.png]"
        "|load [output.png]"
        "|classify [days]"
        "\n       date ranges: [--days N] [--from YYYY-MM-DD] "
        "[--to YYYY-MM-DD]"
        "\n       source: --source database (default) or --source intervals"
        "\n       --include-review: show activities with open review items"
    )


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
    windows: LoadWindows,
    *,
    include_review: bool = False,
) -> None:
    """Render weekly running volume with distance-average lines."""
    from .analysis import (
        distance_averages,
        load_warmup_days,
        weekly_run_distance,
    )
    from .charts import plot_volume

    warmup_days = load_warmup_days(windows)
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

    activities, _ = exclude_review(
        all_activities,
        include_review=include_review,
    )

    points = distance_averages(
        activities,
        start,
        end,
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
    windows: LoadWindows,
    *,
    include_review: bool = False,
) -> None:
    """Render daily load and its base/fitness/fatigue EWMA lines."""
    from .analysis import load_metrics, load_warmup_days
    from .charts import plot_load

    warmup_days = load_warmup_days(windows)
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

        elif mode == "load":
            try:
                output, start, end, windows = parse_load_args(
                    args,
                    default_output="load.png",
                    default_days=180,
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc

            run_load_chart(
                output,
                start,
                end,
                source,
                windows,
                include_review=include_review,
            )
            return

        elif mode == "volume":
            try:
                output, start, end, windows = parse_load_args(
                    args,
                    default_output="volume.png",
                    default_days=90,
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc

            run_volume_chart(
                output,
                start,
                end,
                source,
                windows,
                include_review=include_review,
            )
            return

        elif mode in ("subt-pace", "subt-hr"):
            is_hr_chart = mode == "subt-hr"
            default_output = (
                "subt-hr.png" if is_hr_chart else "subt-pace.png"
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
