"""Data-health report: completeness, review queue, and yearly coverage."""

from __future__ import annotations

from datetime import date

from hobbyjogging_core.datasource import DataSource

from .analysis import yearly_coverage
from .command_support import activity_start
from .dashboard.health import collect_health
from .format import sport_label, table_text
from .review import exclude_review


def _activity_label(item) -> str:
    """The item's activity plus any review candidates, for the queue table."""
    parts = []
    label = " ".join(
        part
        for part in (
            str(item.activity_date) if item.activity_date else "",
            item.activity_name or item.sport or "",
        )
        if part
    )

    if label:
        parts.append(label)

    candidates = item.context.get("candidates")

    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            text = " ".join(
                str(part)
                for part in (
                    candidate.get("date") or "",
                    candidate.get("name") or candidate.get("sport") or "",
                )
                if part
            )

            if text:
                parts.append(text)

    return ", ".join(parts) or "-"


def _queue_rows(items) -> list[str]:
    rows = []

    for item in items:
        rows.append(
            f"| {table_text(item.severity)} | "
            f"{table_text(item.category.replace('_', ' '))} | "
            f"{table_text(item.detail or '-')} | "
            f"{table_text(_activity_label(item))} | "
            f"{item.reported_at[:10] if item.reported_at else '-'} |"
        )

    return rows


def health_report(
    source: DataSource,
    *,
    today: date | None = None,
    include_review: bool = False,
) -> str:
    """Render the Data Health tab's numbers as Markdown."""
    today = today or date.today()
    start = activity_start(source, today)
    raw = source.activities(start, today)
    activities, excluded = exclude_review(
        raw,
        include_review=include_review,
    )
    health = collect_health(
        raw,
        activities,
        start=start,
        end=today,
        include_review=include_review,
    )
    coverage = yearly_coverage(
        activities,
        {
            activity.id
            for activity in activities
            if source.activity_weather(activity.id) is not None
        },
    )
    review_items = source.review_items(status="open")

    lines = [
        "# Data Health",
        f"{start} → {today}",
    ]

    if excluded:
        lines.append(
            f"\n> {excluded} activities excluded (import review)"
        )

    lines.extend([
        "",
        f"- Activities in range: {health.activities}",
        f"- Open review items: {len(review_items)}",
        f"- Hidden by review: {health.review_hidden}",
        f"- Missing load: {health.activities_without_load}",
        f"- Runs without pace zones: {health.runs_without_pace_zones}",
        f"- Runs without average HR: {health.runs_without_hr}",
        f"- Runs without distance: {health.runs_without_distance}",
        "",
        "## Missing data",
        "",
        "| Check | Count |",
        "|---|---:|",
        f"| Activities without load | {health.activities_without_load} |",
        f"| Runs without pace zones | {health.runs_without_pace_zones} |",
        f"| Runs without average HR | {health.runs_without_hr} |",
        f"| Runs without distance | {health.runs_without_distance} |",
    ])

    if health.review_flagged:
        lines.extend([
            "",
            "## Activities with open review items",
            "",
            "| Date | Sport | Name | Status |",
            "|---|---|---|---|",
        ])

        for activity in health.review_flagged:
            lines.append(
                f"| {activity.date} | {sport_label(activity)} | "
                f"{table_text(activity.name) or '-'} | "
                f"{'included' if include_review else 'hidden'} |"
            )

    lines.extend([
        "",
        "## Review queue",
        "",
    ])

    if review_items:
        lines.extend([
            "| Severity | Category | Detail | Activity | Reported |",
            "|---|---|---|---|---|",
            *_queue_rows(review_items),
        ])
    else:
        lines.append("The review queue is empty.")

    if coverage:
        lines.extend([
            "",
            "## Data coverage",
            "",
            "| Year | Activities | Weather |",
            "|---|---:|---:|",
        ])

        for row in coverage:
            lines.append(
                f"| {row.year} | {row.activities} | "
                f"{row.weather} ({row.weather_share:.0%}) |"
            )

    return "\n".join(lines)
