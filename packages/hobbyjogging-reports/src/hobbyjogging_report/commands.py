"""Command registry and per-command help."""

from dataclasses import dataclass, field
from functools import partial
from typing import Callable

from hobbyjogging_core.datasource import DataSource

from .chart_commands import (
    run_load_command,
    run_recovery_command,
    run_subt_hr_command,
    run_subt_pace_command,
    run_time_command,
    run_volume_command,
)
from .cli import (
    parse_chart_args,
    parse_classify_args,
    parse_load_args,
    parse_recovery_args,
    parse_report_args,
    parse_time_args,
)
from .report_commands import (
    run_all_command,
    run_classify_command,
    run_daily_command,
    run_debug_command,
    run_report_command,
    run_session_command,
    run_subt_report_command,
    summary_handler,
)


@dataclass(frozen=True)
class Command:
    """One CLI command: help text, optional parser, and handler."""

    name: str
    summary: str
    usage: str
    examples: tuple[str, ...] = ()
    parse: Callable[[list[str]], object] | None = None
    run: Callable[[object, DataSource | None, bool], str | None] = field(
        kw_only=True
    )
    needs_source: bool = True


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
            "[activities|wellness|events|intervals|all]"
        )
    return argv[0] if argv else "all"


COMMANDS = {
    "daily": Command(
        "daily",
        "Daily training report",
        "daily",
        ("reports.sh", "reports.sh daily"),
        run=run_daily_command,
    ),
    "weekly": Command(
        "weekly",
        "Weekly training report",
        "weekly",
        ("reports.sh weekly",),
        run=summary_handler("weekly"),
    ),
    "monthly": Command(
        "monthly",
        "Monthly training report",
        "monthly",
        ("reports.sh monthly",),
        run=summary_handler("monthly"),
    ),
    "yearly": Command(
        "yearly",
        "Yearly training report",
        "yearly",
        ("reports.sh yearly",),
        run=summary_handler("yearly"),
    ),
    "all": Command(
        "all",
        "Daily, weekly, monthly, and yearly reports",
        "all",
        ("reports.sh all",),
        run=run_all_command,
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
        run=run_report_command,
    ),
    "subt-report": Command(
        "subt-report",
        "subT and LT1 work-block report",
        "subt-report [--days N] [--from DATE] [--to DATE]",
        ("reports.sh subt-report --days 90",),
        parse=partial(parse_report_args, default_days=90),
        run=run_subt_report_command,
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
        run=run_session_command,
    ),
    "classify": Command(
        "classify",
        "Print workout categories",
        "classify [days] [--days N] [--from DATE] [--to DATE]",
        ("reports.sh classify", "reports.sh classify --days 90"),
        parse=parse_classify_args,
        run=run_classify_command,
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
        run=run_volume_command,
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
        run=run_load_command,
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
        run=run_time_command,
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
        run=run_recovery_command,
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
        run=run_subt_pace_command,
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
        run=run_subt_hr_command,
    ),
    "debug": Command(
        "debug",
        "Dump raw Intervals.icu payloads",
        "debug [activities|wellness|events|intervals|all]",
        ("python -m hobbyjogging_report debug activities",),
        parse=_parse_debug,
        run=run_debug_command,
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
