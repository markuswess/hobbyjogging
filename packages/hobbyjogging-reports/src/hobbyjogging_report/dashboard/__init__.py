"""Static HTML dashboard generation."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from hobbyjogging_core.datasource import DataSource

from ..activity_list import select_activities
from ..analysis import daily_training_load, recovery_trends
from ..classify import classify
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
)
from .views import (
    actual_zone_totals,
    in_window,
    planned_summary,
    planned_zone_totals,
    summarize_window,
)

MARKER = ".hobbyjogging-dashboard"


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
    include_review: bool = False,
    today: date | None = None,
) -> Path:
    """Build the static dashboard and return its directory."""
    if days <= 0:
        raise ValueError("days must be positive")
    if activity_limit <= 0:
        raise ValueError("activity limit must be positive")

    today = today or date.today()
    start = today - timedelta(days=days - 1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)

    raw_activities = source.activities(start, today)
    activities, _ = exclude_review(
        raw_activities,
        include_review=include_review,
    )
    previous_raw = source.activities(previous_start, previous_end)
    previous_activities, _ = exclude_review(
        previous_raw,
        include_review=include_review,
    )

    summary = summarize_window(activities)
    previous = summarize_window(previous_activities)
    last7_start = max(start, today - timedelta(days=6))
    last7 = summarize_window(
        in_window(activities, last7_start, today)
    )

    event_start = today
    event_end = today + timedelta(days=6)
    events = [
        event
        for event in source.events(event_start, event_end)
        if event.type
    ]
    planned = planned_summary(events)
    planned_zones = planned_zone_totals(events, event_start, event_end)
    actual_zones, actual_unzoned_s = actual_zone_totals(
        activities,
        start,
        today,
    )
    load_series = daily_training_load(activities, start, today)

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
            start=start,
            end=today,
            days=days,
            summary=summary,
            previous=previous,
            last7=last7,
            events=events,
            planned=planned,
            actual_zones=actual_zones,
            actual_unzoned_s=actual_unzoned_s,
            planned_zones=planned_zones,
            load_series=load_series,
            detail_ids=detail_ids,
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
            start=start,
            end=today,
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
