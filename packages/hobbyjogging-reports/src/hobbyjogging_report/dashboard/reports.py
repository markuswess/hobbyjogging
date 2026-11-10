"""Markdown reports selectable for the static dashboard."""

from __future__ import annotations

from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from ..compare import compare_report
from ..daily import daily
from ..overview import overview_report
from ..period_report import period_report, summary
from ..planned import planned_report
from ..recovery_report import recovery_report
from ..subt_report import subt_report

REPORT_NAMES = (
    "overview",
    "recovery-report",
    "daily",
    "weekly",
    "monthly",
    "yearly",
    "report",
    "planned",
    "subt-report",
    "compare-years",
    "compare-months",
)


def _months_before(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def build_report(
    name: str,
    source: DataSource,
    *,
    today: date,
    future_days: int = 14,
    include_review: bool = False,
) -> str:
    """Render one selected Markdown report for the dashboard."""
    if name == "overview":
        return overview_report(
            source,
            future_days=future_days,
            today=today,
            include_review=include_review,
        )
    if name == "daily":
        return daily(
            source,
            include_review=include_review,
            today=today,
        )
    if name == "recovery-report":
        return recovery_report(source, today=today)
    if name in ("weekly", "monthly", "yearly"):
        return summary(
            name,
            source,
            include_review=include_review,
            today=today,
        )
    if name == "report":
        return period_report(
            today - timedelta(days=29),
            today,
            "Custom Training Report",
            source,
            include_review=include_review,
        )
    if name == "planned":
        return planned_report(
            today,
            today + timedelta(days=27),
            source,
            today=today,
        )
    if name == "subt-report":
        return subt_report(
            today - timedelta(days=89),
            today,
            "subT Report",
            source,
            include_review=include_review,
        )
    if name == "compare-years":
        return compare_report(
            "years",
            None,
            today,
            source,
            include_review=include_review,
        )
    if name == "compare-months":
        return compare_report(
            "months",
            _months_before(today, 11),
            today,
            source,
            include_review=include_review,
        )

    raise ValueError(
        f"unknown report: {name} "
        f"(available: {', '.join(REPORT_NAMES)})"
    )
