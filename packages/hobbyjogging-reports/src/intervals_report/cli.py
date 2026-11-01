"""Small CLI helpers shared by the report commands."""

import argparse
from datetime import date, timedelta

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


def extract_source(argv: list[str]) -> tuple[str, list[str]]:
    """Remove the global --source option and return the remaining arguments."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument(
        "--source",
        choices=SOURCE_CHOICES,
        default=DEFAULT_SOURCE,
    )
    args, remaining = parser.parse_known_args(argv)
    return args.source, remaining


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
