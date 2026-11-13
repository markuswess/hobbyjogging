"""Small CLI helpers shared by the report commands."""

import argparse
from datetime import date, timedelta

from .demo import DEFAULT_MONTHS, DEFAULT_SEED
from .model import AverageWindows
from .recovery_report import WINDOWS as RECOVERY_WINDOWS

DEFAULT_PLANNED_DAYS = 28


def date_arg(value: str) -> date:
    """Parse a YYYY-MM-DD command-line date."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def resolve_range(
    days: int,
    start: date | None = None,
    end: date | None = None,
    today: date | None = None,
) -> tuple[date, date]:
    """Resolve an inclusive date range from --days / --from / --to."""
    if days < 0:
        raise ValueError("--days must be zero or greater")

    today = today or date.today()

    if start is not None and end is not None:
        if start > end:
            raise ValueError("--from must not be after --to")
        return start, end

    if start is not None:
        if start > today:
            raise ValueError("--from must not be after today")
        return start, today

    if end is not None:
        return end - timedelta(days=days), end

    return today - timedelta(days=days), today


def resolve_forward_range(
    days: int,
    start: date | None = None,
    end: date | None = None,
    today: date | None = None,
) -> tuple[date, date]:
    """Resolve an inclusive forward-looking range from --days/--from/--to."""
    if days < 0:
        raise ValueError("--days must be zero or greater")

    today = today or date.today()

    if start is not None and end is not None:
        if start > end:
            raise ValueError("--from must not be after --to")
        return start, end

    if start is not None:
        return start, start + timedelta(days=days)

    if end is not None:
        if end < today:
            raise ValueError("--to must not be before today")
        return today, end

    return today, today + timedelta(days=days)


def extract_globals(argv: list[str]) -> tuple[bool, list[str]]:
    """Remove global options and return (include_review, remaining)."""
    if "--source" in argv:
        raise SystemExit(
            "--source was removed; reports read the canonical database only"
        )

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument(
        "--include-review",
        dest="include_review",
        action="store_true",
        help="show activities with open import review items",
    )
    args, remaining = parser.parse_known_args(argv)
    return args.include_review, remaining


def range_parser() -> argparse.ArgumentParser:
    """Base parser for commands with a date range."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--days", dest="days_option", type=int)
    parser.add_argument("--from", dest="start", type=date_arg)
    parser.add_argument("--to", dest="end", type=date_arg)
    return parser


def parse_classify_args(
    argv: list[str],
    default_days: int = 30,
    today: date | None = None,
) -> tuple[date, date]:
    """Parse the optional lookback and explicit range for `classify`."""
    parser = range_parser()
    parser.add_argument("days", nargs="?", type=int)
    args = parser.parse_args(argv)

    days = (
        args.days_option
        if args.days_option is not None
        else args.days
    )
    if days is None:
        days = default_days

    return resolve_range(days, args.start, args.end, today=today)


def parse_report_args(
    argv: list[str],
    default_days: int = 30,
    today: date | None = None,
) -> tuple[date, date]:
    """Parse a date range for the custom period report."""
    parser = range_parser()
    args = parser.parse_args(argv)

    days = (
        args.days_option
        if args.days_option is not None
        else default_days
    )

    return resolve_range(days, args.start, args.end, today=today)


def parse_races_args(
    argv: list[str],
) -> tuple[str | None, date | None, date | None, int | None]:
    """Parse bucket, date, and limit filters for the races report."""
    from .analysis import BUCKET_ORDER

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--bucket", choices=BUCKET_ORDER)
    parser.add_argument("--year", type=int)
    parser.add_argument("--from", dest="start", type=date_arg)
    parser.add_argument("--to", dest="end", type=date_arg)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    if (
        args.year is not None
        and (args.start is not None or args.end is not None)
    ):
        raise ValueError("--year cannot be combined with --from/--to")

    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")

    start = args.start
    end = args.end

    if args.year is not None:
        try:
            start = date(args.year, 1, 1)
            end = date(args.year, 12, 31)
        except ValueError as exc:
            raise ValueError(f"invalid year: {args.year}") from exc

    if start is not None and end is not None and start > end:
        raise ValueError("--from must not be after --to")

    return args.bucket, start, end, args.limit


def parse_planned_args(
    argv: list[str],
    default_days: int = DEFAULT_PLANNED_DAYS,
    today: date | None = None,
) -> tuple[date, date]:
    """Parse a forward-looking date range for the planned-workouts report."""
    parser = range_parser()
    args = parser.parse_args(argv)

    days = (
        args.days_option
        if args.days_option is not None
        else default_days
    )

    return resolve_forward_range(days, args.start, args.end, today=today)


def _months_before(day: date, months: int) -> date:
    """First day of the month ``months`` before ``day``."""
    index = day.year * 12 + day.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def parse_compare_args(
    argv: list[str],
    today: date | None = None,
) -> tuple[str, date | None, date]:
    """Parse a comparison mode and range.

    ``years`` defaults to ``start=None`` so the report can begin at the
    first year present in the source. ``months`` defaults to the last 12
    calendar months.
    """
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("mode", choices=("years", "months"))
    parser.add_argument("--days", dest="days_option", type=int)
    parser.add_argument("--from", dest="start", type=date_arg)
    parser.add_argument("--to", dest="end", type=date_arg)
    args = parser.parse_args(argv)
    today = today or date.today()
    end = args.end or today

    if args.days_option is not None and args.days_option < 0:
        raise ValueError("--days must be zero or greater")

    if args.start is not None:
        if args.start > end:
            raise ValueError("--from must not be after --to")
        return args.mode, args.start, end

    if args.days_option is not None:
        return (
            args.mode,
            end - timedelta(days=args.days_option),
            end,
        )

    if args.mode == "years":
        return args.mode, None, end

    return args.mode, _months_before(end, 11), end


def parse_dashboard_args(
    argv: list[str],
) -> tuple[
    str | None,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    tuple[str, ...],
    str | None,
]:
    """Parse dashboard output, windows, chart ranges, and reports."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--output")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--activities", type=int, default=50)
    parser.add_argument("--chart-days", type=int, default=182)
    parser.add_argument("--future-days", type=int, default=14)
    parser.add_argument(
        "--recovery-days",
        type=int,
        default=RECOVERY_WINDOWS[-1],
    )
    parser.add_argument("--analysis-days", type=int, default=731)
    parser.add_argument("--compare-window", type=int, default=182)
    parser.add_argument("--timing", action="store_true")
    parser.add_argument("--reports")
    parser.add_argument("--demo-label")
    args = parser.parse_args(argv)

    if args.days <= 0:
        raise ValueError("--days must be positive")
    if args.activities <= 0:
        raise ValueError("--activities must be positive")
    if args.chart_days <= 0:
        raise ValueError("--chart-days must be positive")
    if args.future_days < 0:
        raise ValueError("--future-days must be zero or greater")
    if args.recovery_days <= 0:
        raise ValueError("--recovery-days must be positive")
    if args.analysis_days <= 0:
        raise ValueError("--analysis-days must be positive")
    if args.compare_window <= 0:
        raise ValueError("--compare-window must be positive")

    reports = tuple(
        part.strip()
        for part in (args.reports or "").split(",")
        if part.strip()
    )
    from .dashboard.reports import REPORT_NAMES

    unknown = [name for name in reports if name not in REPORT_NAMES]

    if unknown:
        raise ValueError(
            f"unknown report(s): {', '.join(unknown)} "
            f"(available: {', '.join(REPORT_NAMES)})"
        )

    return (
        args.output,
        args.days,
        args.activities,
        args.chart_days,
        args.future_days,
        args.recovery_days,
        args.analysis_days,
        args.compare_window,
        args.timing,
        reports,
        args.demo_label,
    )


def parse_demo_args(
    argv: list[str],
) -> tuple[str, int, int, date | None, bool, bool]:
    """Parse output, size, seed, build date, review, and overwrite flags."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--out")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--today", type=date_arg)
    parser.add_argument("--with-review-items", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if not args.out:
        raise ValueError("--out is required")
    if args.months <= 0:
        raise ValueError("--months must be positive")
    if args.months > 60:
        raise ValueError("--months must be 60 or less")

    return (
        args.out,
        args.months,
        args.seed,
        args.today,
        args.with_review_items,
        args.force,
    )


def parse_overview_args(
    argv: list[str],
    today: date | None = None,
) -> tuple[int, date]:
    """Parse the optional planned horizon for the overview report."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--future-days", type=int, default=14)
    args = parser.parse_args(argv)

    if args.future_days < 0:
        raise ValueError("--future-days must be zero or greater")

    return args.future_days, today or date.today()


def parse_overview_chart_args(
    argv: list[str],
    default_output: str = "overview.png",
    today: date | None = None,
) -> tuple[str, int, int, date]:
    """Parse output and ranges for the main overview chart."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("output", nargs="?")
    parser.add_argument("--output", dest="output_option")
    parser.add_argument("--chart-days", type=int, default=182)
    parser.add_argument("--future-days", type=int, default=14)
    args = parser.parse_args(argv)

    if args.chart_days <= 0:
        raise ValueError("--chart-days must be positive")
    if args.future_days < 0:
        raise ValueError("--future-days must be zero or greater")

    output = args.output_option or args.output or default_output
    return output, args.chart_days, args.future_days, today or date.today()


def parse_chart_args(
    argv: list[str],
    default_output: str,
    default_days: int,
    today: date | None = None,
) -> tuple[str, date, date]:
    """Parse output and date range options for a chart command."""
    parser = range_parser()
    parser.add_argument("output", nargs="?")
    parser.add_argument("--output", dest="output_option")
    args = parser.parse_args(argv)

    days = (
        args.days_option
        if args.days_option is not None
        else default_days
    )
    start, end = resolve_range(days, args.start, args.end, today=today)
    output = args.output_option or args.output or default_output

    return output, start, end


def parse_compare_chart_args(
    argv: list[str],
    default_output: str = "compare.png",
    today: date | None = None,
) -> tuple[str, str, int, date]:
    """Parse output, metric, and EWMA window for the compare chart."""
    from .analysis import COMPARE_METRICS

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("output", nargs="?")
    parser.add_argument("--output", dest="output_option")
    parser.add_argument(
        "--metric",
        choices=COMPARE_METRICS,
        default="volume",
    )
    parser.add_argument("--window", type=int, default=182)
    args = parser.parse_args(argv)

    if args.window <= 0:
        raise ValueError("--window must be positive")

    output = args.output_option or args.output or default_output
    return output, args.metric, args.window, today or date.today()


def _window_parser() -> argparse.ArgumentParser:
    """Parser shared by charts with EWMA window options."""
    parser = range_parser()
    parser.add_argument("output", nargs="?")
    parser.add_argument("--output", dest="output_option")
    parser.add_argument("--base-days", type=int, default=182)
    parser.add_argument("--fitness-days", type=int, default=42)
    parser.add_argument("--fatigue-days", type=int, default=7)
    parser.add_argument(
        "--planned-days",
        type=int,
        default=DEFAULT_PLANNED_DAYS,
        help="extend the chart this many days into the future for planned "
        "workouts (ignored with --to)",
    )
    return parser


def _window_options(args) -> AverageWindows:
    windows = AverageWindows(
        base=args.base_days,
        fitness=args.fitness_days,
        fatigue=args.fatigue_days,
    )

    if min(windows.base, windows.fitness, windows.fatigue) <= 0:
        raise ValueError("average windows must be positive")

    return windows


def _planned_end(args, end: date) -> date:
    """Extend the chart end for planned workouts unless --to was given."""
    if args.planned_days < 0:
        raise ValueError("--planned-days must be zero or greater")

    if args.end is not None:
        return end

    return end + timedelta(days=args.planned_days)


def _range_output(
    args,
    default_output: str,
    default_days: int,
    today: date | None,
) -> tuple[str, date, date, date]:
    days = (
        args.days_option
        if args.days_option is not None
        else default_days
    )
    start, end = resolve_range(days, args.start, args.end, today=today)
    output = args.output_option or args.output or default_output

    return output, start, end, _planned_end(args, end)


def parse_load_args(
    argv: list[str],
    default_output: str = "load.png",
    default_days: int = 180,
    today: date | None = None,
) -> tuple[str, date, date, date, AverageWindows]:
    """Parse output, range, EWMA windows, and planned horizon."""
    parser = _window_parser()
    args = parser.parse_args(argv)
    windows = _window_options(args)
    output, start, end, planned_end = _range_output(
        args,
        default_output,
        default_days,
        today,
    )

    return output, start, end, planned_end, windows


def parse_time_args(
    argv: list[str],
    default_output: str = "time.png",
    default_days: int = 90,
    today: date | None = None,
) -> tuple[str, date, date, date, AverageWindows, int, str]:
    """Parse output, range, planned horizon, windows, zones, zone window."""
    parser = _window_parser()
    parser.add_argument("--zones", type=int, default=4)
    parser.add_argument(
        "--zone-window",
        choices=("base", "fitness", "fatigue"),
        default="fitness",
    )
    args = parser.parse_args(argv)
    windows = _window_options(args)

    if args.zones <= 0:
        raise ValueError("--zones must be positive")

    output, start, end, planned_end = _range_output(
        args,
        default_output,
        default_days,
        today,
    )

    return (
        output,
        start,
        end,
        planned_end,
        windows,
        args.zones,
        args.zone_window,
    )


def parse_recovery_args(
    argv: list[str],
    default_output: str = "recovery.png",
    default_days: int = 90,
    today: date | None = None,
) -> tuple[str, date, date, date, int]:
    """Parse output, range, planned horizon, and rolling window."""
    parser = range_parser()
    parser.add_argument("output", nargs="?")
    parser.add_argument("--output", dest="output_option")
    parser.add_argument("--window", type=int, default=7)
    parser.add_argument(
        "--planned-days",
        type=int,
        default=DEFAULT_PLANNED_DAYS,
        help="extend the chart this many days into the future for planned "
        "workouts (ignored with --to)",
    )
    args = parser.parse_args(argv)

    if args.window <= 0:
        raise ValueError("--window must be positive")

    output, start, end, planned_end = _range_output(
        args,
        default_output,
        default_days,
        today,
    )

    return output, start, end, planned_end, args.window
