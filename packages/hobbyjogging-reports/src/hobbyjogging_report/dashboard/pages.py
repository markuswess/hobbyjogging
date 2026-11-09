"""HTML page builders for the static dashboard."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from hobbyjogging_core.model import Activity, Event, Interval

from ..analysis import (
    RUN_TYPES,
    event_zone_time,
    is_lt1_activity,
    is_subt_activity,
    pace_s_per_km,
    subt_work_points,
)
from ..format import (
    fmt_clock,
    fmt_time,
    fmt_zones,
    format_feel,
    format_pace,
    format_work_result,
    pace,
    sport_label,
)
from ..html import card, chart, esc, link, page, stat_grid, table
from .charts import load_chart, zone_mix_chart
from .health import DataHealth, banner
from .views import PlannedSummary, WindowSummary


def activity_filename(activity_id: str) -> str:
    return f"{quote(str(activity_id), safe='')}.html"


def activity_href(activity_id: str) -> str:
    return f"activity/{activity_filename(activity_id)}"


def _duration(seconds: float) -> str:
    return fmt_time(seconds) if seconds else "0min"


def _km(distance_m: float) -> str:
    return f"{distance_m / 1000:,.1f}" if distance_m else "0.0"


def _km_cell(distance_m: float) -> str:
    return f"{distance_m / 1000:,.1f}" if distance_m else "-"


def _pace_cell(activity: Activity) -> str:
    return pace(activity) if activity.type in RUN_TYPES else "-"


def _load(value: float) -> str:
    return f"{value:.0f}"


def _hr(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def _count_delta(current: int, previous: int, days: int) -> str:
    if previous == 0:
        return "new vs previous window" if current else "unchanged"
    difference = current - previous
    if difference == 0:
        return f"unchanged vs previous {days} days"
    return f"{difference:+d} vs previous {days} days"


def _pct_delta(current: float, previous: float, days: int) -> str:
    if previous == 0:
        return "new vs previous window" if current else ""
    return f"{(current - previous) / previous:+.0%} vs previous {days} days"


def _zone_seconds(event: Event) -> str:
    seconds = event_zone_time(event, (3, 4))

    if seconds is None:
        return "-"
    if not seconds:
        return "0min"
    return fmt_time(seconds)


def _event_distance(event: Event) -> str:
    return f"{event.distance_m / 1000:.1f} km" if event.distance_m else "-"


def _event_load(event) -> str:
    return "-" if event.training_load is None else f"{event.training_load:.0f}"


def overview_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    start: date,
    end: date,
    days: int,
    summary: WindowSummary,
    previous: WindowSummary,
    last7: WindowSummary,
    events: list[Event],
    planned: PlannedSummary,
    actual_zones: list[float],
    actual_unzoned_s: float,
    planned_zones: list[float],
    load_series: list[tuple[date, float]],
    detail_ids: set[str],
) -> str:
    stats = [
        (
            "Runs",
            str(summary.runs),
            _count_delta(summary.runs, previous.runs, days),
        ),
        (
            "Cross sessions",
            str(summary.cross),
            _count_delta(summary.cross, previous.cross, days),
        ),
        (
            "Run time",
            _duration(summary.run_time_s),
            _pct_delta(summary.run_time_s, previous.run_time_s, days),
        ),
        (
            "Run km",
            _km(summary.run_distance_m),
            _pct_delta(
                summary.run_distance_m,
                previous.run_distance_m,
                days,
            ),
        ),
        (
            "Load",
            _load(summary.load),
            _pct_delta(summary.load, previous.load, days),
        ),
        (
            "Z3+4 time",
            _duration(summary.z3_z4_s),
            _pct_delta(summary.z3_z4_s, previous.z3_z4_s, days),
        ),
    ]

    if any(value > 0 for _, value in load_series):
        load_html = chart(load_chart(load_series))
    else:
        load_html = '<p class="muted">No training load in this window.</p>'

    if any(actual_zones) or actual_unzoned_s or any(planned_zones):
        zone_html = chart(
            zone_mix_chart(
                actual_zones,
                planned_zones,
                unzoned_s=actual_unzoned_s,
            )
        )
    else:
        zone_html = '<p class="muted">No pace-zone data in this window.</p>'

    plan_actual = table(
        ["Metric", "Last 7 days", "Next 7 days"],
        [
            [
                "Run time",
                esc(_duration(last7.run_time_s)),
                esc(_duration(planned.run_time_s)),
            ],
            [
                "Run km",
                esc(_km(last7.run_distance_m)),
                esc(_km(planned.run_distance_m)),
            ],
            [
                "Run load",
                esc(_load(last7.run_load)),
                esc(_load(planned.load)),
            ],
        ],
        numeric=(1, 2),
    )

    planned_rows = []

    for event in sorted(events, key=lambda item: (item.date, item.name)):
        planned_rows.append([
            esc(event.date),
            esc(event.date.strftime("%a")),
            esc(event.name or "-"),
            esc(sport_label(event)),
            esc(_event_distance(event)),
            esc(fmt_time(event.duration_s)),
            esc(_zone_seconds(event)),
            esc(_event_load(event)),
        ])

    planned_html = table(
        ["Date", "Day", "Workout", "Sport", "Distance", "Time", "Z3+4", "Load"],
        planned_rows,
        numeric=(4, 5, 6, 7),
        empty="No planned sessions in the next 7 days.",
    )

    if any(event.zone_times for event in events):
        planned_html += (
            '<p class="muted">Z3+4 uses each event\'s planned zone '
            "kind.</p>"
        )

    quality_rows = []

    for activity in summary.quality[:5]:
        name = activity.name or sport_label(activity)
        name_html = (
            link(activity_href(activity.id), name)
            if activity.id in detail_ids
            else esc(name)
        )
        quality_rows.append([
            esc(activity.date),
            name_html,
            esc(sport_label(activity)),
            esc(fmt_time(activity.duration_s)),
            esc(_pace_cell(activity)),
            esc(_hr(activity.avg_hr)),
        ])

    quality_html = table(
        ["Date", "Session", "Sport", "Time", "Pace", "Avg HR"],
        quality_rows,
        numeric=(3, 4, 5),
        empty="No quality sessions in this window.",
    )

    body = (
        stat_grid(stats)
        + card(
            f"Training load — last {days} days",
            load_html,
        )
        + card("Pace-zone mix", zone_html)
        + card("Plan vs actual", plan_actual)
        + card("Next 7 days", planned_html)
        + card("Quality sessions", quality_html)
        + f'<p>{link("activities.html", "All activities →")}</p>'
    )

    return page(
        title=f"Training overview · {start} → {end}",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        active="overview",
        plotly=True,
    )


def activities_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
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
            esc(fmt_time(activity.duration_s)),
            esc(_km_cell(activity.distance_m)),
            esc(_pace_cell(activity)),
            esc(_hr(activity.avg_hr)),
            esc(_event_load(activity)),
            esc(format_feel(activity.feel)),
        ])

    body = table(
        ["Date", "Sport", "Name", "Time", "Distance", "Pace", "Avg HR",
         "Load", "Feel"],
        rows,
        numeric=(3, 4, 5, 6, 7),
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
        active="activities",
    )


def activity_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    activity: Activity,
    intervals: list[Interval],
    category: str,
) -> str:
    title = (
        f"{sport_label(activity)} — {activity.name}"
        if activity.name
        else sport_label(activity)
    )
    metrics = [
        ["Date", esc(activity.date)],
        ["Category", esc(category)],
        ["Duration", esc(fmt_time(activity.duration_s))],
    ]

    if activity.elapsed_s and activity.elapsed_s != activity.duration_s:
        metrics.append(["Elapsed", esc(fmt_time(activity.elapsed_s))])

    if activity.distance_m:
        metrics.append(
            ["Distance", esc(f"{activity.distance_m / 1000:.2f} km")]
        )

    metrics.extend([
        ["Pace", esc(_pace_cell(activity))],
        ["Avg HR", esc(_hr(activity.avg_hr))],
        ["Load", esc(_event_load(activity))],
        ["RPE", esc("-" if activity.rpe is None else f"{activity.rpe:g}")],
        ["Feel", esc(format_feel(activity.feel))],
    ])

    if activity.intensity is not None:
        metrics.append(["Intensity", esc(f"{activity.intensity:.0%}")])

    metrics_html = table(["Field", "Value"], metrics)

    zones = []

    if activity.pace_zone_times:
        zones.append(
            f"<p><strong>Pace zones:</strong> "
            f"{esc(fmt_zones(activity.pace_zone_times))}</p>"
        )

    if activity.hr_zone_times:
        zones.append(
            f"<p><strong>HR zones:</strong> "
            f"{esc(fmt_zones(activity.hr_zone_times))}</p>"
        )

    interval_rows = []

    for index, interval in enumerate(intervals, start=1):
        interval_pace = pace_s_per_km(
            interval.duration_s,
            interval.distance_m,
        )
        interval_rows.append([
            str(index),
            esc(interval.type.title() or "-"),
            esc(fmt_clock(interval.duration_s)),
            esc(_km_cell(interval.distance_m)),
            esc(
                f"{format_pace(interval_pace)}/km"
                if interval_pace is not None
                else "-"
            ),
            esc(_hr(interval.avg_hr)),
            esc(_hr(interval.max_hr)),
        ])

    intervals_html = table(
        ["#", "Type", "Time", "Distance", "Pace", "Avg HR", "Max HR"],
        interval_rows,
        numeric=(0, 2, 3, 4, 5, 6),
        empty="No recorded intervals.",
    )

    work_html = ""

    if is_subt_activity(activity) or is_lt1_activity(activity):
        points = subt_work_points(activity, intervals)

        if points:
            label = "LT1" if is_lt1_activity(activity) else None
            items = "".join(
                f"<li>{esc(format_work_result(point, label))}</li>"
                for point in points
            )
            work_html = card("Work reps", f"<ul>{items}</ul>")

    body = (
        f'<p>{link("activities.html", "← All activities")}</p>'
        + card("Metrics", metrics_html + "".join(zones))
    )

    if activity.description and activity.description.strip():
        body += card(
            "Description",
            f'<pre class="description">{esc(activity.description)}</pre>',
        )

    body += card("Intervals", intervals_html)

    if work_html:
        body += work_html

    return page(
        title=title,
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            root="../",
            include_review=include_review,
        ),
        active="activities",
        root="../",
    )


def health_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    detail_ids: set[str],
) -> str:
    stats = [
        ("Activities in window", str(health.activities), ""),
        ("Hidden by review", str(health.review_hidden), ""),
        ("Missing load", str(health.activities_without_load), ""),
        ("Runs without pace zones", str(health.runs_without_pace_zones), ""),
        ("Runs without HR", str(health.runs_without_hr), ""),
        ("Runs without distance", str(health.runs_without_distance), ""),
    ]

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
        + card("Open review items", review_html)
        + card("Missing data", missing_html)
        + '<p class="muted">The dashboard reads canonical data only; '
        "individual review-item categories are not exposed yet.</p>"
    )

    return page(
        title=f"Data health · {health.start} → {health.end}",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        active="health",
    )
