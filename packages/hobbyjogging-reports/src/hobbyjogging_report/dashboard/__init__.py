"""Static HTML dashboard generation."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from hobbyjogging_core.datasource import DataSource

from ..activity_list import select_activities
from ..analysis import (
    average_warmup_days,
    recovery_trends,
    vo2max_points,
)
from ..classify import classify
from ..html import markdown_to_html
from ..model import AverageWindows
from ..overview import overview_report
from ..planned import planned_report
from ..recovery_report import recovery_report
from ..review import exclude_review
from .charts import plotly_js
from .health import collect_health
from .pages import (
    activity_filename,
    activity_page,
    activities_page,
    health_page,
    overview_page,
    recovery_page,
    reports_page,
)
from .reports import REPORT_NAMES, build_report
from ..zone_groups import (
    daily_zone_groups,
    planned_bars_without_actual,
    zone_group_series,
)

MARKER = ".hobbyjogging-dashboard"
RACE_DAYS = 180


def resolve_output_dir(output: str | Path | None = None) -> Path:
    """Resolve the dashboard site directory.

    ``--output`` is exact. ``HOBBYJOGGING_DASHBOARD_DIR`` names a parent
    directory and the dashboard is written to its ``dashboard`` subfolder.
    Otherwise the repo-local ``data/dashboard`` is used.
    """
    if output is not None:
        return Path(output).expanduser()

    configured = os.environ.get("HOBBYJOGGING_DASHBOARD_DIR")

    if configured:
        return Path(configured).expanduser() / "dashboard"

    return Path("data/dashboard")


def build_dashboard(
    source: DataSource,
    output: str | Path | None = None,
    *,
    days: int = 14,
    activity_limit: int = 50,
    chart_days: int = 70,
    future_days: int = 14,
    reports: tuple[str, ...] = (),
    include_review: bool = False,
    today: date | None = None,
) -> Path:
    """Build the static dashboard and return its directory."""
    if days <= 0:
        raise ValueError("days must be positive")
    if activity_limit <= 0:
        raise ValueError("activity limit must be positive")
    if chart_days <= 0:
        raise ValueError("chart days must be positive")
    if future_days < 0:
        raise ValueError("future days must be zero or greater")

    unknown_reports = [
        name for name in reports if name not in REPORT_NAMES
    ]
    if unknown_reports:
        raise ValueError(
            f"unknown report(s): {', '.join(unknown_reports)} "
            f"(available: {', '.join(REPORT_NAMES)})"
        )

    today = today or date.today()
    start = today - timedelta(days=days - 1)

    raw_activities = source.activities(start, today)
    activities, _ = exclude_review(
        raw_activities,
        include_review=include_review,
    )

    chart_start = today - timedelta(days=chart_days - 1)
    chart_end = today + timedelta(days=future_days)
    windows = AverageWindows(base=182, fitness=42, fatigue=7)
    warmup_days = average_warmup_days(windows)
    chart_activities, _ = exclude_review(
        source.activities(
            chart_start - timedelta(days=warmup_days),
            today,
        ),
        include_review=include_review,
    )
    chart_events = [
        event
        for event in source.events(today, chart_end)
        if event.type
    ]
    volume_bars = daily_zone_groups(
        chart_activities,
        chart_start,
        today,
    )
    planned_bars = planned_bars_without_actual(
        chart_events,
        volume_bars,
        today,
        chart_end,
    )
    volume_series = zone_group_series(
        chart_activities,
        chart_events,
        chart_start - timedelta(days=warmup_days),
        chart_end,
        chart_start=chart_start,
        projection_start=today,
        windows=windows,
    )

    vo2max = vo2max_points(
        chart_activities,
        chart_start - timedelta(days=warmup_days),
        chart_end,
    )

    wellness = source.wellness(
        start - timedelta(days=6),
        today,
    )
    recovery = recovery_trends(
        wellness,
        start,
        today,
        window_days=7,
    )
    recovery_html = markdown_to_html(
        recovery_report(source, today=today),
        demote=1,
    )

    overview_html = markdown_to_html(
        overview_report(
            source,
            future_days=future_days,
            today=today,
            include_review=include_review,
        ),
        demote=1,
    )
    daily_html = markdown_to_html(
        build_report(
            "daily",
            source,
            today=today,
            include_review=include_review,
        ),
        demote=1,
    )
    planned_html = markdown_to_html(
        planned_report(
            today + timedelta(days=1),
            today + timedelta(days=14),
            source,
            today=today,
        ),
        demote=1,
    )
    races = [
        event
        for event in source.events(today, today + timedelta(days=RACE_DAYS))
        if "race" in set(event.workout_methods) | set(event.workout_targets)
    ]
    report_sections = [
        markdown_to_html(
            build_report(
                name,
                source,
                today=today,
                future_days=future_days,
                include_review=include_review,
            ),
            demote=1,
        )
        for name in reports
    ]

    health = collect_health(
        raw_activities,
        activities,
        start=start,
        end=today,
        include_review=include_review,
    )

    listed_activities, listed_excluded = select_activities(
        source,
        limit=activity_limit,
        include_review=include_review,
        today=today,
    )

    detail_activities = {
        activity.id: activity
        for activity in activities
    }
    detail_activities.update(
        {activity.id: activity for activity in listed_activities}
    )
    detail_ids = set(detail_activities)

    generated_at = datetime.now().astimezone().strftime(
        "%Y-%m-%d %H:%M %Z"
    )

    pages = {
        "index.html": overview_page(
            generated_at=generated_at,
            health=health,
            include_review=include_review,
            end=today,
            overview_html=overview_html,
            daily_html=daily_html,
            planned_html=planned_html,
            races=races,
            volume_bars=volume_bars,
            planned_bars=planned_bars,
            volume_series=volume_series,
            chart_start=chart_start,
            chart_end=chart_end,
            vo2max_points=vo2max,
        ),
        "activities.html": activities_page(
            generated_at=generated_at,
            health=health,
            include_review=include_review,
            activities=listed_activities,
            excluded=listed_excluded,
        ),
        "recovery.html": recovery_page(
            generated_at=generated_at,
            health=health,
            include_review=include_review,
            points=recovery,
            report_html=recovery_html,
            start=start,
            end=today,
        ),
        "reports.html": reports_page(
            generated_at=generated_at,
            health=health,
            include_review=include_review,
            sections=report_sections,
        ),
        "health.html": health_page(
            generated_at=generated_at,
            health=health,
            include_review=include_review,
            detail_ids=detail_ids,
        ),
    }

    detail_pages = {}

    for activity in detail_activities.values():
        try:
            intervals = source.activity_intervals(activity.id)
        except Exception:
            intervals = []

        detail_pages[
            f"activity/{activity_filename(activity.id)}"
        ] = activity_page(
            generated_at=generated_at,
            health=health,
            include_review=include_review,
            activity=activity,
            intervals=intervals,
            category=classify(activity, intervals).path,
        )

    target = resolve_output_dir(output)
    _write_site(target, pages | detail_pages)

    return target


def _check_target(target: Path) -> None:
    if target.resolve() in {
        Path.cwd().resolve(),
        Path.home().resolve(),
    }:
        raise ValueError(
            "refusing to replace the current or home directory"
        )

    if target.exists() and not target.is_dir():
        raise ValueError(f"{target} exists and is not a directory")

    if target.exists() and not (target / MARKER).exists():
        if any(target.iterdir()):
            raise ValueError(
                f"{target} is not empty and is not a dashboard directory; "
                "remove it or choose another output"
            )


def _write_site(target: Path, pages: dict[str, str]) -> None:
    _check_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}-",
            dir=target.parent,
        )
    )
    backup = target.with_name(f".{target.name}.old")
    moved = False

    try:
        (temporary / "activity").mkdir()
        (temporary / MARKER).write_text(
            "hobbyjogging static dashboard\n",
            encoding="utf-8",
        )
        (temporary / "plotly.min.js").write_text(
            plotly_js(),
            encoding="utf-8",
        )

        for relative, content in pages.items():
            path = temporary / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        if target.exists():
            if backup.exists():
                shutil.rmtree(backup)
            target.rename(backup)
            moved = True

        temporary.rename(target)

        if moved and backup.exists():
            shutil.rmtree(backup)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)

        if moved and backup.exists() and not target.exists():
            backup.rename(target)

        raise
