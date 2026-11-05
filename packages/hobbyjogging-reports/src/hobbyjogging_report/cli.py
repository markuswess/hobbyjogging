"""Small CLI helpers shared by the report commands."""

import argparse
from datetime import date, timedelta

from .model import AverageWindows
from .sources import DEFAULT_SOURCE, SOURCE_CHOICES


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


def extract_source(argv: list[str]) -> tuple[str, bool, list[str]]:
    """Remove global options and return (source, include_review, remaining)."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument(
        "--source",
        choices=SOURCE_CHOICES,
        default=DEFAULT_SOURCE,
    )
    parser.add_argument(
        "--include-review",
        dest="include_review",
        action="store_true",
        help="show activities with open import review items",
    )
    args, remaining = parser.parse_known_args(argv)
    return args.source, args.include_review, remaining


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


def _window_parser() -> argparse.ArgumentParser:
    """Parser shared by charts with EWMA window options."""
    parser = range_parser()
    parser.add_argument("output", nargs="?")
    parser.add_argument("--output", dest="output_option")
    parser.add_argument("--base-days", type=int, default=182)
    parser.add_argument("--fitness-days", type=int, default=42)
    parser.add_argument("--fatigue-days", type=int, default=7)
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


def _range_output(
    args,
    default_output: str,
    default_days: int,
    today: date | None,
) -> tuple[str, date, date]:
    days = (
        args.days_option
        if args.days_option is not None
        else default_days
    )
    start, end = resolve_range(days, args.start, args.end, today=today)
    output = args.output_option or args.output or default_output

    return output, start, end


def parse_load_args(
    argv: list[str],
    default_output: str = "load.png",
    default_days: int = 180,
    today: date | None = None,
) -> tuple[str, date, date, AverageWindows]:
    """Parse output, range, and EWMA windows for the load chart."""
    parser = _window_parser()
    args = parser.parse_args(argv)
    windows = _window_options(args)
    output, start, end = _range_output(
        args,
        default_output,
        default_days,
        today,
    )

    return output, start, end, windows


def parse_time_args(
    argv: list[str],
    default_output: str = "time.png",
    default_days: int = 90,
    today: date | None = None,
) -> tuple[str, date, date, AverageWindows, int, str]:
    """Parse output, range, windows, zone count, and zone window."""
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

    output, start, end = _range_output(
        args,
        default_output,
        default_days,
        today,
    )

    return (
        output,
        start,
        end,
        windows,
        args.zones,
        args.zone_window,
    )


def parse_recovery_args(
    argv: list[str],
    default_output: str = "recovery.png",
    default_days: int = 90,
    today: date | None = None,
) -> tuple[str, date, date, int]:
    """Parse output, range, and rolling window for the recovery chart."""
    parser = range_parser()
    parser.add_argument("output", nargs="?")
    parser.add_argument("--output", dest="output_option")
    parser.add_argument("--window", type=int, default=7)
    args = parser.parse_args(argv)

    if args.window <= 0:
        raise ValueError("--window must be positive")

    output, start, end = _range_output(
        args,
        default_output,
        default_days,
        today,
    )

    return output, start, end, args.window
