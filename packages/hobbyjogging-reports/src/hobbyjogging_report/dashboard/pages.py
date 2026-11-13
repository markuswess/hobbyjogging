"""HTML page builders for the static dashboard."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from hobbyjogging_core.model import Activity, Event, ReviewItem

from ..analysis import RUN_TYPES
from ..format import (
    fmt_time,
    format_feel,
    format_methods,
    format_targets,
    pace,
    sport_label,
)
from ..charts import plot_overview, plot_recovery
from ..html import card, chart, esc, link, page, stat_grid, table
from ..model import RecoveryPoint, Vo2maxPoint
from .analysis import AnalysisSection
from .compare import CompareSection
from .docs import DocsSection
from .gear import GearSection
from .lab import LabSection
from .health import DataHealth, banner
from .nsa import NsaSection
from ..zone_groups import ZoneGroupSeries


def activity_filename(activity_id: str) -> str:
    return f"{quote(str(activity_id), safe='')}.html"


def activity_href(activity_id: str) -> str:
    return f"activity/{activity_filename(activity_id)}"


def _km_cell(distance_m: float) -> str:
    return f"{distance_m / 1000:,.1f}" if distance_m else "-"


def _pace_cell(activity: Activity) -> str:
    return pace(activity) if activity.type in RUN_TYPES else "-"


def _hr(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def _event_load(event) -> str:
    return "-" if event.training_load is None else f"{event.training_load:.0f}"


def _races_card(races: list[Event]) -> str:
    rows = [
        [
            esc(event.date),
            esc(event.name or "-"),
            esc(
                f"{event.distance_m / 1000:.1f} km"
                if event.distance_m
                else "-"
            ),
            esc(
                "-"
                if event.training_load is None
                else f"{event.training_load:.0f}"
            ),
            esc(event.zone_kind.title() if event.zone_kind else "-"),
        ]
        for event in races
    ]

    return card(
        "Upcoming races",
        table(
            ["Date", "Race", "Distance", "Load", "Zone kind"],
            rows,
            numeric=(2, 3),
            empty="No upcoming races.",
        ),
    )


def overview_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    end: date,
    overview_html: str,
    daily_html: str,
    planned_html: str,
    races: list[Event],
    volume_bars: list[tuple[date, float, float, float]],
    planned_bars: list[tuple[date, float, float, float]],
    volume_series: ZoneGroupSeries,
    chart_start: date,
    chart_end: date,
    vo2max_points: list[Vo2maxPoint],
) -> str:
    future_days = (chart_end - end).days

    volume_html = chart(
        plot_overview(
            volume_bars,
            planned_bars,
            volume_series,
            output="",
            start=chart_start,
            end=chart_end,
            today=end,
            vo2max_points=vo2max_points,
            title="",
            as_html=True,
        )
    )
    volume_days = (end - chart_start).days + 1
    range_text = (
        f"the last {volume_days} days and next {future_days} days"
        if future_days
        else f"the last {volume_days} days"
    )
    volume_html += (
        f'<p class="muted">Daily running minutes over {range_text}, stacked '
        "hard → easy → unzoned; lines are 7/42/182-day EWMAs for hard and "
        "total running, plus the black Garmin VO2max line on the right "
        "axis. Planned workouts appear as hatched bars on days "
        "without a recorded run; lighter line segments are projected.</p>"
    )

    body = (
        card(None, f'<div class="report">{overview_html}</div>')
        + card("Daily running minutes", volume_html)
        + card(None, f'<div class="report">{daily_html}</div>')
        + (_races_card(races) if races else "")
        + card(None, f'<div class="report">{planned_html}</div>')
        + f'<p>{link("activities.html", "All activities →")}</p>'
    )

    return page(
        title="Training overview",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="overview",
        plotly=True,
    )


def activities_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    activities: list[Activity],
    excluded: int,
) -> str:
    rows = []

    for activity in activities:
        href = activity_href(activity.id)
        name = activity.name or sport_label(activity)
        rows.append([
            link(href, str(activity.date)),
            esc(sport_label(activity)),
            link(href, name),
            esc(format_methods(activity)),
            esc(format_targets(activity)),
            esc(fmt_time(activity.duration_s)),
            esc(_km_cell(activity.distance_m)),
            esc(_pace_cell(activity)),
            esc(_hr(activity.avg_hr)),
            esc(_event_load(activity)),
            esc(format_feel(activity.feel)),
        ])

    body = table(
        ["Date", "Sport", "Name", "Methods", "Targets", "Time", "Distance",
         "Pace", "Avg HR", "Load", "Feel"],
        rows,
        numeric=(5, 6, 7, 8, 9),
        empty="No activities found.",
    )

    if excluded:
        body += (
            f'<p class="muted">{excluded} activities are hidden by import '
            f'review. {link("health.html", "Details")}</p>'
        )

    body += f'<p>{link("index.html", "← Overview")}</p>'

    return page(
        title="Activities",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="activities",
    )


def activity_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    activity: Activity,
    report_html: str,
) -> str:
    """Render one activity as the same session report the CLI prints."""
    body = (
        f'<p>{link("../activities.html", "← All activities")}</p>'
        + card(None, f'<div class="report">{report_html}</div>')
    )

    return page(
        title=f"Session {activity.date}",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            root="../",
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="activities",
        root="../",
    )


def recovery_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    points: list[RecoveryPoint],
    report_html: str,
    start: date,
    end: date,
    baseline_points: list[RecoveryPoint] | None = None,
) -> str:
    if points:
        chart_html = chart(
            plot_recovery(
                points,
                output="",
                as_html=True,
                baseline_points=baseline_points,
            )
        )
    else:
        chart_html = '<p class="muted">No wellness data in this window.</p>'

    total_days = (end - start).days + 1
    completeness = (
        f"{len(points)} of {total_days} days have wellness data."
    )

    body = (
        card(None, f'<div class="report">{report_html}</div>')
        + card("Recovery trends", chart_html)
        + card(
            "Data completeness",
            f'<p class="muted">{esc(completeness)}</p>'
            '<p class="muted">Daily values are points; lines are 7-day '
            "calendar-day averages. Missing values are skipped.</p>"
            '<p class="muted">Bands compare a robust 365-day baseline '
            "(median centre, 1.4826 \u00d7 MAD spread) computed at the end "
            "of this window: HRV is green at or above the centre, amber "
            "within one spread below, red below that; resting HR is mirrored; "
            "sleep is green 7\u20139 h, amber 6\u20137 h or 9\u201310 h, "
            "red outside.</p>",
        )
    )

    return page(
        title=f"Recovery and Health · {start} → {end}",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="recovery",
        plotly=True,
    )


def nsa_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    section: NsaSection,
    start: date,
    end: date,
) -> str:
    """Render the NSA tab: the EWMA report, the subT chart, and the report."""
    body = (
        card(
            None,
            f'<div class="report">{section.ewma_report_html}</div>',
        )
        + card("subT and LT1 intervals", section.subt_html)
        + card(
            None,
            f'<div class="report">{section.subt_report_html}</div>',
        )
    )

    return page(
        title=f"NSA · {start} → {end}",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="nsa",
        plotly=True,
    )


def compare_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    section: CompareSection,
) -> str:
    """Render the compare tab: year chart plus the year/month reports."""
    body = (
        card(None, section.volume_html)
        + card(None, section.time_html)
        + card(None, section.efficiency_html)
        + card(None, section.vo2max_html)
        + card(None, section.pace_hr_html)
        + card(
            None,
            f'<div class="report">{section.years_report_html}</div>',
        )
        + card(
            None,
            f'<div class="report">{section.months_report_html}</div>',
        )
    )

    return page(
        title="Compare",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="compare",
        plotly=True,
    )


def analysis_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    section: AnalysisSection,
    start: date,
    end: date,
) -> str:
    """Render the analysis tab: volume, time, and load charts."""
    body = (
        card("Weekly running volume", section.volume_html)
        + card("Weekly running time by pace zone", section.time_html)
        + card("Training load and session RPE", section.load_html)
        + card("Pace vs heart rate", section.pace_hr_html)
    )

    return page(
        title=f"Analysis · {start} → {end}",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="analysis",
        plotly=True,
    )


def health_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    detail_ids: set[str],
    review_items: list[ReviewItem],
) -> str:
    stats = [
        ("Activities in window", str(health.activities), ""),
        ("Open review items", str(len(review_items)), ""),
        ("Hidden by review", str(health.review_hidden), ""),
        ("Missing load", str(health.activities_without_load), ""),
        ("Runs without pace zones", str(health.runs_without_pace_zones), ""),
        ("Runs without HR", str(health.runs_without_hr), ""),
        ("Runs without distance", str(health.runs_without_distance), ""),
    ]

    queue_rows = []

    for item in review_items:
        label = " ".join(
            part
            for part in (
                str(item.activity_date) if item.activity_date else "",
                item.activity_name or item.sport,
            )
            if part
        ) or "-"
        activity_html = (
            link(activity_href(item.activity_id), label)
            if item.activity_id and item.activity_id in detail_ids
            else esc(label)
        )
        queue_rows.append([
            esc(item.severity),
            esc(item.category.replace("_", " ")),
            esc(item.detail or "-"),
            activity_html,
            esc(item.reported_at[:10] if item.reported_at else "-"),
        ])

    queue_html = table(
        ["Severity", "Category", "Detail", "Activity", "Reported"],
        queue_rows,
        empty="The review queue is empty.",
    )

    review_rows = []

    for activity in health.review_flagged:
        name = activity.name or sport_label(activity)
        status = "included" if include_review else "hidden"
        name_html = (
            link(activity_href(activity.id), name)
            if include_review and activity.id in detail_ids
            else esc(name)
        )
        review_rows.append([
            esc(activity.date),
            esc(sport_label(activity)),
            name_html,
            esc(status),
        ])

    review_html = table(
        ["Date", "Sport", "Name", "Status"],
        review_rows,
        empty="No activities with open review items in this window.",
    )

    missing_rows = [
        ["Activities without load", str(health.activities_without_load)],
        ["Runs without pace zones", str(health.runs_without_pace_zones)],
        ["Runs without average HR", str(health.runs_without_hr)],
        ["Runs without distance", str(health.runs_without_distance)],
    ]
    missing_html = table(
        ["Check", "Count"],
        missing_rows,
        numeric=(1,),
    )

    body = (
        stat_grid(stats)
        + card("Review queue", queue_html)
        + card("Activities with open review items", review_html)
        + card("Missing data", missing_html)
    )

    return page(
        title=f"Data Health · {health.start} → {health.end}",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="health",
    )


def gear_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    section: GearSection,
) -> str:
    """Render gear mileage, coverage, and retirement candidates."""
    body = (
        card(None, section.summary_html)
        + card("Mileage", section.chart_html)
        + card("Gear", section.table_html)
        + card("Coverage", section.coverage_html)
        + card("Retirement candidates", section.candidates_html)
    )

    return page(
        title="Gear",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="gear",
        plotly=True,
    )


def lab_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    section: LabSection,
) -> str:
    """Render the experiments notebook and script index."""
    body = (
        card(None, f'<div class="report">{section.intro_html}</div>')
        + card(None, f'<div class="report">{section.readme_html}</div>')
        + card("Experiment scripts", section.scripts_html)
    )

    return page(
        title="Lab",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="lab",
    )


def docs_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    demo_label: str | None = None,
    section: DocsSection,
) -> str:
    """Render the package README and metric registry."""
    body = (
        card(None, f'<div class="report">{section.intro_html}</div>')
        + card("Reports guide", f'<div class="report">{section.readme_html}</div>')
        + card("Metrics", f'<div class="report">{section.metrics_html}</div>')
    )

    return page(
        title="Docs",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        demo_label=demo_label,
        active="docs",
    )


