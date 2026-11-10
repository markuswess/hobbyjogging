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
from ..charts import plot_overview, plot_recovery
from ..html import card, chart, esc, link, page, stat_grid, table
from ..model import RecoveryPoint, Vo2maxPoint
from .health import DataHealth, banner
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


def _latest(points: list[RecoveryPoint], attribute: str):
    for point in reversed(points):
        value = getattr(point, attribute)
        if value is not None:
            return value
    return None


def _recovery_stat(
    points: list[RecoveryPoint],
    attribute: str,
    average_attribute: str,
    *,
    scale: float = 1.0,
    unit: str,
    decimals: int = 0,
) -> tuple[str, str]:
    value = _latest(points, attribute)
    average = (
        getattr(points[-1], average_attribute)
        if points
        else None
    )

    if value is None:
        current_value = "-"
    else:
        current_value = f"{value * scale:.{decimals}f} {unit}"

    if average is None:
        average_text = "7-day avg -"
    else:
        average_text = (
            f"7-day avg {average * scale:.{decimals}f} {unit}"
        )

    return current_value, average_text


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
    end: date,
    overview_html: str,
    daily_html: str,
    events: list[Event],
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
        empty="No planned sessions in the next 14 days.",
    )

    if any(event.zone_times for event in events):
        planned_html += (
            '<p class="muted">Z3+4 uses each event\'s planned zone '
            "kind.</p>"
        )

    body = (
        card(None, f'<div class="report">{overview_html}</div>')
        + card("Daily running minutes", volume_html)
        + card("Daily report",f'<div class="report">{daily_html}</div>')
        + card("Next 14 days", planned_html)
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


def recovery_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    points: list[RecoveryPoint],
    start: date,
    end: date,
) -> str:
    hrv_value, hrv_average = _recovery_stat(
        points,
        "hrv",
        "hrv_avg",
        unit="ms",
    )
    rhr_value, rhr_average = _recovery_stat(
        points,
        "resting_hr",
        "resting_hr_avg",
        unit="bpm",
    )
    sleep_value, sleep_average = _recovery_stat(
        points,
        "sleep_s",
        "sleep_avg",
        scale=1 / 3600,
        unit="h",
        decimals=1,
    )

    stats = [
        ("HRV", hrv_value, hrv_average),
        ("Resting HR", rhr_value, rhr_average),
        ("Sleep", sleep_value, sleep_average),
    ]

    if points:
        chart_html = chart(
            plot_recovery(
                points,
                output="",
                as_html=True,
            )
        )
    else:
        chart_html = '<p class="muted">No wellness data in this window.</p>'

    total_days = (end - start).days + 1
    completeness = (
        f"{len(points)} of {total_days} days have wellness data."
    )

    body = (
        stat_grid(stats)
        + card("Recovery trends", chart_html)
        + card(
            "Data completeness",
            f'<p class="muted">{esc(completeness)}</p>'
            '<p class="muted">Daily values are points; lines are 7-day '
            "calendar-day averages. Missing values are skipped.</p>",
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
        active="recovery",
        plotly=True,
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
        title=f"Data Health · {health.start} → {health.end}",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        active="health",
    )


def reports_page(
    *,
    generated_at: str,
    health: DataHealth,
    include_review: bool,
    sections: list[tuple[str, str]],
) -> str:
    """Render the selected Markdown reports as HTML sections."""
    if not sections:
        body = (
            '<p class="muted">No Markdown reports selected. Use '
            "<code>dashboard.sh --reports overview,daily,planned</code>."
            "</p>"
        )
    else:
        body = "".join(
            card(
                name.replace("-", " ").title(),
                f'<div class="report">{html}</div>',
            )
            for name, html in sections
        )

    return page(
        title="Reports",
        body=body,
        generated_at=generated_at,
        health_html=banner(
            health,
            include_review=include_review,
        ),
        active="reports",
    )
