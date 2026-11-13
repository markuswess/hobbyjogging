"""Report formatting.

All helpers take canonical model objects (see ``hobbyjogging_core.model``), so
reports work with any ``DataSource`` implementation.
"""

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import (
    Activity,
    Event,
    Interval,
    Lap,
    ReviewItem,
    WellnessDay,
)
from hobbyjogging_core.workouts import WORKOUT_METHODS, WORKOUT_TARGETS

from .analysis import (
    EFFICIENCY_UNIT,
    RUN_TYPES,
    activity_efficiency,
    is_lt1_activity,
    is_subt_activity,
    pace_s_per_km,
    subt_work_points,
)
from .model import SubtBlock, SubtPoint, SubtSummary


SPORT_LABELS = {
    "run": "Run",
    "trail_run": "TrailRun",
}

# Intervals.icu's 1-5 feel scale: 1 is best, 5 is worst.
FEEL_LABELS = {
    1: "Strong",
    2: "Good",
    3: "Normal",
    4: "Poor",
    5: "Weak",
}


def format_feel(feel):
    """Format a feel rating as ``4 (Poor)``."""
    if feel is None:
        return "-"

    label = FEEL_LABELS.get(feel)

    return f"{feel} ({label})" if label else f"{feel}"


def sport_label(item):
    """Human-readable sport/type name."""

    return SPORT_LABELS.get(
        item.type,
        item.type.replace("_", " ").title(),
    )


def _workout_labels(values, labels) -> str:
    present = set(values or [])

    return ", ".join(
        label for token, label in labels.items() if token in present
    )


def format_methods(item) -> str:
    """Format an activity's or event's workout methods, in vocabulary order."""
    return _workout_labels(item.workout_methods, WORKOUT_METHODS) or "-"


def format_targets(item) -> str:
    """Format an activity's or event's workout targets, in vocabulary order."""
    return _workout_labels(item.workout_targets, WORKOUT_TARGETS) or "-"


def fmt_time(seconds):
    """Format seconds as ``50min`` / ``1h02`` for report lines."""

    if not seconds:
        return "-"

    seconds = int(seconds)

    minutes = seconds // 60

    h = minutes // 60
    m = minutes % 60

    if h:
        return f"{h}h{m:02d}"

    return f"{m}min"


def fmt_clock(seconds):
    """Format seconds as M:SS, or H:MM:SS for longer intervals."""
    if not seconds:
        return "-"

    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes}:{secs:02d}"


def format_fenced_block(text, indent=""):
    """Return Markdown lines that keep arbitrary text inside a code fence."""
    text = (text or "").strip("\n")

    if not text.strip():
        return []

    fence = "```"

    while fence in text:
        fence += "`"

    return [
        f"{indent}{fence}",
        *[
            f"{indent}{line}" if line else ""
            for line in text.splitlines()
        ],
        f"{indent}{fence}",
    ]


def fmt_zones(zone_times):
    """Zone times as ``Z1 5min | Z3 30min`` for compact report lines."""

    if not zone_times:
        return "-"

    return " | ".join(
        f"Z{i+1} {fmt_time(t)}"
        for i, t in enumerate(zone_times)
        if t
    )


def fmt_zones_precise(zone_times):
    """Format zone times as M:SS, keeping sub-minute zones visible."""
    if not zone_times:
        return "-"

    return " | ".join(
        f"Z{i+1} {fmt_clock(t)}"
        for i, t in enumerate(zone_times)
        if t
    )


def fmt_share(share):

    if share <= 0:
        return "0%"

    if share < 0.01:
        return "<1%"

    return f"{share:.0%}"


def format_category_table(stats):

    if not stats:
        return ["- No activities"]

    lines = [
        "| Category | Sessions | Time | Load | "
        "Steady efficiency (45–75 min) | Time % | Load % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for stat in stats:
        lines.append(
            f"| {stat.path} | {stat.sessions} | {fmt_time(stat.time_s)} | "
            f"{stat.load:.0f} | {_efficiency_cell(stat.efficiency)} | "
            f"{fmt_share(stat.time_share)} | "
            f"{fmt_share(stat.load_share)} |"
        )

    total_sessions = sum(stat.sessions for stat in stats)
    total_time = sum(stat.time_s for stat in stats)
    total_load = sum(stat.load for stat in stats)

    load_share = "100%" if total_load else "-"

    total_distance = sum(stat.distance_m for stat in stats)
    total_beats = sum(stat.excess_beats for stat in stats)
    total_efficiency = (
        total_distance / total_beats if total_beats > 0 else None
    )

    lines.append(
        f"| **Total** | {total_sessions} | {fmt_time(total_time)} | "
        f"{total_load:.0f} | {_efficiency_cell(total_efficiency)} | "
        f"100% | {load_share} |"
    )

    return lines


def pace(activity):
    """Average pace of one activity as ``M:SS/km``."""

    seconds = pace_s_per_km(activity.duration_s, activity.distance_m)

    if seconds is None:
        return "-"

    return f"{format_pace(seconds)}/km"


def format_work_result(point: SubtPoint, label: str | None = None):

    duration = point.avg_rep_s
    interval_duration = fmt_clock(duration)
    label = label or f"subT-{point.category}"

    if point.avg_hr is None and point.max_hr is None:
        hr = "- bpm"
    elif point.max_hr is None:
        hr = f"{point.avg_hr:.0f} avg bpm"
    elif point.avg_hr is None:
        hr = f"{point.max_hr:.0f} max bpm"
    else:
        hr = f"{point.avg_hr:.0f} avg / {point.max_hr:.0f} max bpm"

    efficiency = (
        f", {point.efficiency:.2f} {EFFICIENCY_UNIT}"
        if point.efficiency is not None
        else ""
    )

    return (
        f"{point.count}x{interval_duration} "
        f"{label}: "
        f"{format_pace(point.pace_s_per_km)}/km, "
        f"{hr}{efficiency}"
    )


def last_four_nights(wellness):

    wellness = sorted(
        wellness,
        key=lambda x: x.date,
        reverse=True,
    )

    return wellness[:4]


def format_nights(wellness) -> list[str]:
    """Format the last four nights as bullets under a Night heading.

    Shared by the daily and recovery reports so both read the same way:
    ``- 2026-11-07: HRV 55 ms, RHR 46 bpm, Sleep 7h30``.
    """
    lines = ["\n## Night"]

    for day in reversed(last_four_nights(wellness)):
        hrv = day.hrv
        rhr = day.resting_hr
        sleep = day.sleep_s

        lines.append(
            f"- {day.date}: "
            + (f"HRV {hrv:.0f} ms, " if hrv is not None else "HRV N/A, ")
            + (
                f"RHR {rhr:.0f} bpm"
                if rhr is not None
                else "RHR N/A"
            )
            + (
                f", Sleep {fmt_time(sleep)}"
                if sleep
                else ", Sleep N/A"
            )
        )

    return lines


def format_pace(seconds):
    """Format seconds/km as M:SS."""
    if seconds is None:
        return "-"
    seconds = round(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def work_summary_for_activity(
    activity: Activity,
    intervals: list[Interval],
    resting_hr: float | None = None,
):
    """Return work-interval report lines for subT or LT1 activities."""

    if is_lt1_activity(activity):
        label = "LT1"
    elif is_subt_activity(activity):
        label = None
    else:
        return None

    points = subt_work_points(
        activity,
        intervals,
        resting_hr=resting_hr,
    )

    if not points:
        return None

    return [
        format_work_result(point, label)
        for point in points
    ]


def get_work_summary(
    source: DataSource,
    activity: Activity,
    resting_hr: float | None = None,
):
    """Return compact work-interval summary for subT or LT1 activities."""

    if not (is_subt_activity(activity) or is_lt1_activity(activity)):
        return None

    try:
        intervals = source.activity_intervals(activity.id)
    except Exception:
        return None

    return work_summary_for_activity(
        activity,
        intervals,
        resting_hr=resting_hr,
    )


def _vo2max_line(activity: Activity) -> str | None:
    parts = []

    if activity.vo2max_garmin is not None:
        parts.append(f"{activity.vo2max_garmin:.1f} (Garmin)")
    if activity.vo2max_runalyze is not None:
        parts.append(f"{activity.vo2max_runalyze:.1f} (Runalyze)")

    if not parts:
        return None

    return "- VO2max: " + ", ".join(parts)


def _activity_metric_lines(
    activity: Activity,
    *,
    detailed: bool = False,
    resting_hr: float | None = None,
):
    """Shared metric lines for compact and detailed activity renderers."""
    lines = [f"- Duration: {fmt_time(activity.duration_s)}"]

    if (
        detailed
        and activity.elapsed_s
        and activity.elapsed_s != activity.duration_s
    ):
        lines.append(f"- Elapsed: {fmt_time(activity.elapsed_s)}")

    if activity.distance_m:
        lines.append(f"- Distance: {activity.distance_m / 1000:.1f} km")

    if activity.type in RUN_TYPES:
        lines.append(f"- Pace: {pace(activity)}")

    if activity.avg_hr:
        if detailed:
            lines.append(f"- Avg HR: {activity.avg_hr:.0f} bpm")
        else:
            lines.append(f"- HR: {activity.avg_hr:.0f} avg")

    efficiency = activity_efficiency(activity, resting_hr)

    if efficiency is not None:
        lines.append(
            f"- Efficiency: {efficiency:.2f} {EFFICIENCY_UNIT}"
        )

    if activity.training_load:
        lines.append(f"- Load: {activity.training_load:.0f}")

    if detailed:
        if activity.rpe is not None:
            lines.append(f"- RPE: {activity.rpe:g}")
    elif activity.rpe:
        lines.append(f"- RPE: {activity.rpe:.0f}")

    if activity.feel is not None:
        lines.append(f"- Feel: {format_feel(activity.feel)}")

    if detailed and activity.intensity is not None:
        lines.append(f"- Intensity: {activity.intensity:.0%}")

    if detailed and activity.tags:
        lines.append(f"- Tags: {', '.join(activity.tags)}")

    if detailed:
        vo2max = _vo2max_line(activity)
        if vo2max:
            lines.append(vo2max)

    if detailed and activity.equipment:
        names = ", ".join(
            equipment.name or equipment.id
            for equipment in activity.equipment
        )
        lines.append(f"- Equipment: {names}")

    zones = fmt_zones_precise if detailed else fmt_zones

    if activity.pace_zone_times:
        lines.append(f"- Pace zones: {zones(activity.pace_zone_times)}")

    if detailed and activity.hr_zone_times:
        lines.append(f"- HR zones: {zones(activity.hr_zone_times)}")

    return lines


def _activity_description_lines(
    activity: Activity,
    *,
    detailed: bool = False,
):
    """Render a description as a fenced block, keeping the report layout."""
    if not (activity.description and activity.description.strip()):
        return []

    if detailed:
        return [
            "\n### Description",
            *format_fenced_block(activity.description),
        ]

    return ["", *format_fenced_block(activity.description)]


def format_activity(
    source: DataSource,
    activity: Activity,
    heading: str,
    category: str | None = None,
    intervals: list[Interval] | None = None,
    resting_hr: float | None = None,
):

    lines = [f"\n### {heading}"]

    if category:
        lines.append(f"- Category: {category}")

    lines.extend(
        _activity_metric_lines(activity, resting_hr=resting_hr)
    )
    lines.extend(_activity_description_lines(activity))

    if intervals is None:
        work = get_work_summary(source, activity, resting_hr=resting_hr)
    else:
        work = work_summary_for_activity(
            activity,
            intervals,
            resting_hr=resting_hr,
        )

    if work:
        label = "LT1 report" if is_lt1_activity(activity) else "subT report"
        lines.append(f"\n### {label}")
        for line in work:
            lines.append(f"- {line}")

    return lines


def format_interval_table(intervals: list[Interval]):
    """Render every interval as a Markdown table."""
    lines = [
        "| # | Type | Time | Distance | Pace | Avg HR | Max HR |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]

    for index, interval in enumerate(intervals, start=1):
        interval_pace = pace_s_per_km(
            interval.duration_s,
            interval.distance_m,
        )

        pace_cell = (
            f"{format_pace(interval_pace)}/km"
            if interval_pace is not None
            else "-"
        )
        distance_cell = (
            f"{interval.distance_m / 1000:.2f} km"
            if interval.distance_m
            else "-"
        )
        avg_hr = (
            f"{interval.avg_hr:.0f}"
            if interval.avg_hr is not None
            else "-"
        )
        max_hr = (
            f"{interval.max_hr:.0f}"
            if interval.max_hr is not None
            else "-"
        )

        lines.append(
            f"| {index} | {interval.type.title() or '-'} | "
            f"{fmt_clock(interval.duration_s)} | {distance_cell} | "
            f"{pace_cell} | {avg_hr} | {max_hr} |"
        )

    return lines


def _link(url: str) -> str:
    """Markdown link whose text is the external activity id."""
    label = url.rsplit("/", 1)[-1] or url
    return f"[{label}]({url})"


def format_wellness_summary(day: WellnessDay) -> str:
    """One-line wellness summary for a session's day."""
    parts = [
        f"HRV {day.hrv:.0f} ms" if day.hrv is not None else "HRV N/A",
        (
            f"RHR {day.resting_hr:.0f} bpm"
            if day.resting_hr is not None
            else "RHR N/A"
        ),
        f"Sleep {fmt_time(day.sleep_s)}" if day.sleep_s else "Sleep N/A",
    ]

    return "- " + ", ".join(parts)


def format_planned_event(event: Event) -> list[str]:
    """Render the day's planned workout under a session report."""
    lines = [f"\n### Planned — {event.name or sport_label(event)}"]

    if event.type:
        lines.append(f"- Type: {sport_label(event)}")
    if event.duration_s:
        lines.append(f"- Duration: {fmt_time(event.duration_s)}")
    if event.distance_m:
        lines.append(f"- Distance: {event.distance_m / 1000:.1f} km")
    if event.workout_methods:
        lines.append(f"- Methods: {format_methods(event)}")
    if event.workout_targets:
        lines.append(f"- Targets: {format_targets(event)}")
    if event.zone_times:
        label = event.zone_kind or "zone"
        zones = " | ".join(
            f"{zone.zone_label} {fmt_clock(zone.seconds)}"
            for zone in event.zone_times
            if zone.seconds
        )
        if zones:
            lines.append(f"- Planned {label} times: {zones}")

    description = event.description.strip("\n") if event.description else ""

    if description:
        lines.append("")
        lines.extend(format_fenced_block(description))

    return lines


def format_laps_table(laps: list[Lap]) -> list[str]:
    """Render stored laps as a Markdown table."""
    if not laps:
        return []

    lines = [
        "\n### Laps",
        "| # | Time | Distance | Pace | Avg HR | Max HR | Elev gain |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for lap in laps:
        lap_pace = pace_s_per_km(lap.duration_s, lap.distance_m)
        avg_hr = "-" if lap.avg_hr is None else f"{lap.avg_hr:.0f}"
        max_hr = "-" if lap.max_hr is None else f"{lap.max_hr:.0f}"
        elevation = (
            "-"
            if lap.elevation_gain_m is None
            else f"{lap.elevation_gain_m:.0f} m"
        )
        lines.append(
            f"| {lap.index} | {fmt_clock(lap.duration_s)} | "
            f"{lap.distance_m / 1000:.2f} km | "
            f"{format_pace(lap_pace)}/km | {avg_hr} | {max_hr} | "
            f"{elevation} |"
        )

    return lines


def format_review_items(items: list[ReviewItem]) -> list[str]:
    """Render open review items attached to one session."""
    if not items:
        return []

    lines = ["\n### Review"]

    for item in items:
        label = item.category.replace("_", " ")
        lines.append(
            f"- **{item.severity.title()} · {label}**: {item.detail}"
        )

    return lines


def format_session_activity(
    activity: Activity,
    intervals: list[Interval],
    category: str | None = None,
    *,
    links=None,
    resting_hr: float | None = None,
    planned_events: list[Event] | None = None,
    wellness: WellnessDay | None = None,
    review_items: list[ReviewItem] | None = None,
    laps: list[Lap] | None = None,
):
    """Render one activity as a detailed, standalone session report."""
    title = sport_label(activity)

    if activity.name:
        title = f"{title} — {activity.name}"

    lines = [
        f"\n## {title}",
        f"- ID: {activity.id}",
        f"- Date: {activity.date}",
    ]

    if activity.started_at_utc:
        lines.append(f"- Started: {activity.started_at_utc} (UTC)")

    if links is not None:
        if links.intervals:
            lines.append(f"- Intervals: {_link(links.intervals)}")
        if links.garmin:
            lines.append(f"- Garmin Connect: {_link(links.garmin)}")

    if category:
        lines.append(f"- Category: {category}")

    if review_items is not None:
        lines.append(
            f"- Review: {'open' if review_items else 'clear'}"
        )

    lines.append(f"- Methods: {format_methods(activity)}")
    lines.append(f"- Targets: {format_targets(activity)}")

    lines.extend(
        _activity_metric_lines(
            activity,
            detailed=True,
            resting_hr=resting_hr,
        )
    )
    lines.extend(_activity_description_lines(activity, detailed=True))
    lines.extend(format_review_items(review_items or []))

    for event in planned_events or []:
        lines.extend(format_planned_event(event))

    if wellness is not None:
        lines.append("\n### Wellness")
        lines.append(format_wellness_summary(wellness))

    # One raw segment table per activity: typed reps when there is more
    # than one, otherwise device splits. A single segment just restates
    # the activity; the subT work-reps section below is independent.
    if len(intervals) > 1:
        lines.append("\n### Intervals")
        lines.extend(format_interval_table(intervals))
    elif len(laps or []) > 1:
        lines.extend(format_laps_table(laps or []))

    points = []

    if intervals and (
        is_lt1_activity(activity) or is_subt_activity(activity)
    ):
        points = subt_work_points(
            activity,
            intervals,
            resting_hr=resting_hr,
        )

    if points:
        label = "LT1" if is_lt1_activity(activity) else None

        lines.append("\n### Work reps")

        for point in points:
            lines.append(f"- {format_work_result(point, label)}")

    return lines


def subt_category_label(category: str) -> str:
    """Human-readable label for a subT report category."""
    return "LT1" if category == "lt1" else category.title()


def table_text(value: str) -> str:
    """Keep arbitrary activity names inside one Markdown table cell."""
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _pace_cell(seconds: float | None) -> str:
    return f"{format_pace(seconds)}/km" if seconds is not None else "-"


def _hr_cell(value: float | None) -> str:
    return f"{value:.0f}" if value is not None else "-"


def _efficiency_cell(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _km_cell(distance_m: float, decimals: int) -> str:
    if not distance_m:
        return "-"
    return f"{distance_m / 1000:.{decimals}f}"


def format_subt_summary_table(
    summaries: list[SubtSummary],
    total: SubtSummary,
    days: int,
):
    """Render the cross-category summary for a subT report.

    Work time and distance are shown per week: total divided by ``days`` and
    multiplied by 7.
    """
    weeks = days / 7 if days else 0

    lines = [
        "| Category | Sessions | Reps | Work time / week | "
        "Work km / week | Avg pace | Avg HR | Max HR | Efficiency (m/excess beat) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def row(label: str, summary: SubtSummary) -> str:
        time = summary.total_time_s / weeks if weeks else 0
        distance = summary.total_distance_m / weeks if weeks else 0

        return (
            f"| {label} | "
            f"{summary.sessions} | {summary.reps} | "
            f"{fmt_clock(time)} | "
            f"{_km_cell(distance, 1)} | "
            f"{_pace_cell(summary.pace_s_per_km)} | "
            f"{_hr_cell(summary.avg_hr)} | "
            f"{_hr_cell(summary.max_hr)} | "
            f"{_efficiency_cell(summary.efficiency)} |"
        )

    for summary in summaries:
        lines.append(row(subt_category_label(summary.category), summary))

    lines.append(row("**Total**", total))

    return lines


def format_subt_block_table(blocks: list[SubtBlock]):
    """Render one category's work blocks as a Markdown table."""
    lines = [
        "| Date | Session | Reps | Work time | Work km | Pace | "
        "Fastest | Slowest | Avg HR | Max HR | "
        "Efficiency (m/excess beat) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for block in blocks:
        name = table_text(block.activity_name) or "-"

        lines.append(
            f"| {block.date} | {name} | "
            f"{block.count} × {fmt_clock(block.avg_rep_s)} | "
            f"{fmt_clock(block.total_time_s)} | "
            f"{_km_cell(block.total_distance_m, 2)} | "
            f"{_pace_cell(block.pace_s_per_km)} | "
            f"{_pace_cell(block.fastest_pace_s_per_km)} | "
            f"{_pace_cell(block.slowest_pace_s_per_km)} | "
            f"{_hr_cell(block.avg_hr)} | "
            f"{_hr_cell(block.max_hr)} | "
            f"{_efficiency_cell(block.efficiency)} |"
        )

    return lines
