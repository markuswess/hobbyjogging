"""Command registry and per-command help."""

from dataclasses import dataclass, field
from functools import partial
from typing import Callable

from hobbyjogging_core.datasource import DataSource

from .chart_commands import (
    run_compare_chart_command,
    run_load_command,
    run_pace_hr_command,
    run_overview_chart_command,
    run_recovery_command,
    run_subt_command,
    run_time_command,
    run_vo2max_command,
    run_volume_command,
)
from .cli import (
    parse_chart_args,
    parse_classify_args,
    parse_compare_args,
    parse_compare_chart_args,
    parse_dashboard_args,
    parse_demo_args,
    parse_load_args,
    parse_overview_args,
    parse_overview_chart_args,
    parse_planned_args,
    parse_recovery_args,
    parse_report_args,
    parse_time_args,
)
from .activity_list import (
    COLUMNS,
    DEFAULT_COLUMNS,
    parse_activities_args,
)
from .report_commands import (
    run_activities_command,
    run_all_command,
    run_classify_command,
    run_compare_command,
    run_daily_command,
    run_equipment_command,
    run_race_command,
    run_races_command,
    run_dashboard_command,
    run_demo_command,
    run_debug_command,
    run_overview_command,
    run_planned_command,
    run_recovery_report_command,
    run_report_command,
    run_session_command,
    run_subt_ewma_report_command,
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
    notes: tuple[str, ...] = ()
    standalone_note: str = (
        "this command manages its own files and does not open the "
        "canonical database"
    )


def _parse_race(argv: list[str]):
    if len(argv) != 1:
        raise ValueError(
            "usage: python -m hobbyjogging_report race ACTIVITY_ID"
        )
    return argv[0]


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
    "overview": Command(
        "overview",
        "Training overview with 7/42/182-day EWMAs",
        "overview [--future-days N]",
        ("reports.sh overview", "reports.sh overview --future-days 21"),
        parse=parse_overview_args,
        run=run_overview_command,
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
    "dashboard": Command(
        "dashboard",
        "Generate the static HTML dashboard",
        "dashboard [--output DIR] [--days N] [--activities N] "
        "[--chart-days N] [--future-days N]",
        (
            "dashboard.sh",
            "dashboard.sh --days 30 --activities 100",
            "dashboard.sh --chart-days 90 --future-days 21",
            "dashboard.sh --output /tmp/dashboard",
        ),
        parse=parse_dashboard_args,
        run=run_dashboard_command,
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
    "compare": Command(
        "compare",
        "Compare training by year or month",
        "compare years|months [--days N] [--from DATE] [--to DATE]",
        (
            "reports.sh compare years",
            "reports.sh compare months",
            "reports.sh compare months --from 2025-01-01 --to 2025-12-31",
        ),
        parse=parse_compare_args,
        run=run_compare_command,
    ),
    "subt-report": Command(
        "subt-report",
        "subT and LT1 work-block report",
        "subt-report [--days N] [--from DATE] [--to DATE]",
        ("reports.sh subt-report --days 90",),
        parse=partial(parse_report_args, default_days=90),
        run=run_subt_report_command,
    ),
    "races": Command(
        "races",
        "Race results, PBs, upcoming races, and Riegel estimates",
        "races",
        ("reports.sh races",),
        run=run_races_command,
    ),
    "race": Command(
        "race",
        "Race-day report with splits and plan execution",
        "race ACTIVITY_ID",
        ("reports.sh race <activity-id>",),
        parse=_parse_race,
        run=run_race_command,
    ),
    "equipment": Command(
        "equipment",
        "Gear mileage, coverage, wear, and retirement candidates",
        "equipment",
        ("reports.sh equipment",),
        run=run_equipment_command,
    ),
    "recovery-report": Command(
        "recovery-report",
        "Recovery report with 7/42/182-day moving averages",
        "recovery-report",
        ("reports.sh recovery-report",),
        run=run_recovery_report_command,
    ),
    "subt-ewma-report": Command(
        "subt-ewma-report",
        "subT/LT1 work pace and HR with 7/42/182-day EWMAs",
        "subt-ewma-report",
        ("reports.sh subt-ewma-report",),
        run=run_subt_ewma_report_command,
    ),
    "planned": Command(
        "planned",
        "Upcoming planned workouts",
        "planned [--days N] [--from DATE] [--to DATE]",
        (
            "reports.sh planned",
            "reports.sh planned --days 56",
        ),
        parse=parse_planned_args,
        run=run_planned_command,
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
        "[--planned-days N] [--base-days N] [--fitness-days N] "
        "[--fatigue-days N]",
        ("charts.sh volume --days 90",),
        parse=partial(
            parse_load_args,
            default_output="volume.png",
            default_days=90,
        ),
        run=run_volume_command,
    ),
    "compare-chart": Command(
        "compare-chart",
        "Year-over-year EWMA comparison chart",
        "compare-chart [output.png] [--metric volume|time|load|runs] "
        "[--window N]",
        (
            "charts.sh compare",
            "charts.sh compare --metric load --window 7",
        ),
        parse=parse_compare_chart_args,
        run=run_compare_chart_command,
    ),
    "overview-chart": Command(
        "overview-chart",
        "Main training overview chart",
        "overview-chart [output.png] [--chart-days N] [--future-days N]",
        (
            "charts.sh overview",
            "charts.sh overview --chart-days 90 --future-days 21",
        ),
        parse=parse_overview_chart_args,
        run=run_overview_chart_command,
    ),
    "load": Command(
        "load",
        "Daily load with base, fitness, and fatigue averages",
        "load [output.png] [--days N] [--from DATE] [--to DATE] "
        "[--planned-days N] [--base-days N] [--fitness-days N] "
        "[--fatigue-days N]",
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
        "Weekly running time stacked by pace zone",
        "time [output.png] [--days N] [--from DATE] [--to DATE] "
        "[--planned-days N] [--zones N] [--zone-window base|fitness|fatigue]",
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
        "[--planned-days N] [--window N]",
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
    "pace-hr": Command(
        "pace-hr",
        "Average pace vs average heart rate for each run",
        "pace-hr [output.png] [--days N] [--from DATE] [--to DATE]",
        (
            "charts.sh pace-hr",
            "charts.sh pace-hr --days 365",
        ),
        parse=partial(
            parse_chart_args,
            default_output="pace-hr.png",
            default_days=365,
        ),
        run=run_pace_hr_command,
    ),
    "subt": Command(
        "subt",
        "subT and LT1 work-interval pace and HR chart",
        "subt [output.png] [--days N] [--from DATE] [--to DATE]",
        (
            "charts.sh subt --days 365",
            "charts.sh subt --from 2026-01-01 --to 2026-06-30",
        ),
        parse=partial(
            parse_chart_args,
            default_output="subt.png",
            default_days=365,
        ),
        run=run_subt_command,
    ),
    "vo2max": Command(
        "vo2max",
        "Garmin running VO2max with 7- and 42-day averages",
        "vo2max [output.png] [--days N] [--from DATE] [--to DATE]",
        ("charts.sh vo2max --days 365",),
        parse=partial(
            parse_chart_args,
            default_output="vo2max.png",
            default_days=365,
        ),
        run=run_vo2max_command,
    ),
    "activities": Command(
        "activities",
        "Table of recent activities with selectable columns",
        "activities [--limit N] [--days N] [--from DATE] [--to DATE] "
        "[--columns LIST] [--add LIST]",
        (
            "reports.sh activities",
            "reports.sh activities --limit 50",
            "reports.sh activities --days 30 --add id,category",
            "reports.sh activities --columns date,name,distance",
        ),
        parse=parse_activities_args,
        run=run_activities_command,
        notes=(
            f"default columns: {', '.join(DEFAULT_COLUMNS)}",
            f"available columns: {', '.join(COLUMNS)}",
        ),
    ),
    "debug": Command(
        "debug",
        "Dump raw payloads stored in the database",
        "debug [activities|wellness|events|intervals|all]",
        ("python -m hobbyjogging_report debug activities",),
        parse=_parse_debug,
        run=run_debug_command,
        needs_source=False,
        standalone_note=(
            "requires INTERVALS_ATHLETE_ID and INTERVALS_API_KEY"
        ),
    ),
    "demo-db": Command(
        "demo-db",
        "Write a deterministic synthetic demo database",
        "demo-db --out PATH [--months N] [--seed N] [--today DATE] "
        "[--with-review-items] [--force]",
        (
            "python -m hobbyjogging_report demo-db --out build/demo.db",
            "python -m hobbyjogging_report demo-db --out build/demo.db "
            "--months 12 --seed 7",
        ),
        parse=parse_demo_args,
        run=run_demo_command,
        needs_source=False,
        standalone_note=(
            "writes a new SQLite file; it never reads the canonical "
            "database"
        ),
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

    if command.notes:
        lines.extend(["", "notes:"])
        lines.extend(f"  {note}" for note in command.notes)

    if command.needs_source:
        lines.extend([
            "",
            "global options:",
            "  --source database|intervals",
            "  --include-review",
        ])
    else:
        lines.extend(["", command.standalone_note])

    return "\n".join(lines)
