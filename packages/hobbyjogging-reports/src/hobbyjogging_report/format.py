"""Report formatting.

All helpers take canonical model objects (see ``hobbyjogging_core.model``), so
reports work with any ``DataSource`` implementation.
"""

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import Activity, Interval

from .analysis import (
    RUN_TYPES,
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
        "| Category | Sessions | Time | Load | Time % | Load % |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for stat in stats:
        lines.append(
            f"| {stat.path} | {stat.sessions} | {fmt_time(stat.time_s)} | "
            f"{stat.load:.0f} | {fmt_share(stat.time_share)} | "
            f"{fmt_share(stat.load_share)} |"
        )

    total_sessions = sum(stat.sessions for stat in stats)
    total_time = sum(stat.time_s for stat in stats)
    total_load = sum(stat.load for stat in stats)

    load_share = "100%" if total_load else "-"

    lines.append(
        f"| **Total** | {total_sessions} | {fmt_time(total_time)} | "
        f"{total_load:.0f} | 100% | {load_share} |"
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

    return (
        f"{point.count}x{interval_duration} "
        f"{label}: "
        f"{format_pace(point.pace_s_per_km)}/km, "
        f"{hr}"
    )


def last_four_nights(wellness):

    wellness = sorted(
        wellness,
        key=lambda x: x.date,
        reverse=True,
    )

    return wellness[:4]


def format_pace(seconds):
    """Format seconds/km as M:SS."""
    if seconds is None:
        return "-"
    seconds = round(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def work_summary_for_activity(
    activity: Activity,
    intervals: list[Interval],
):
    """Return work-interval report lines for subT or LT1 activities."""

    if is_lt1_activity(activity):
        label = "LT1"
    elif is_subt_activity(activity):
        label = None
    else:
        return None

    points = subt_work_points(activity, intervals)

    if not points:
        return None

    return [
        format_work_result(point, label)
        for point in points
    ]


def get_work_summary(
    source: DataSource,
    activity: Activity,
):
    """Return compact work-interval summary for subT or LT1 activities."""

    if not (is_subt_activity(activity) or is_lt1_activity(activity)):
        return None

    try:
        intervals = source.activity_intervals(activity.id)
    except Exception:
        return None

    return work_summary_for_activity(activity, intervals)


def _activity_metric_lines(
    activity: Activity,
    *,
    detailed: bool = False,
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
    """Render a description; non-detailed output is plain Markdown."""
    if not (activity.description and activity.description.strip()):
        return []

    if detailed:
        return [
            "\n### Description",
            *format_fenced_block(activity.description),
        ]

    description = activity.description.strip("\n")
    return ["", *description.splitlines()]


def format_activity(
    source: DataSource,
    activity: Activity,
    heading: str,
    category: str | None = None,
    intervals: list[Interval] | None = None,
):

    lines = [f"\n### {heading}"]

    if category:
        lines.append(f"- Category: {category}")

    lines.extend(_activity_metric_lines(activity))
    lines.extend(_activity_description_lines(activity))

    if intervals is None:
        work = get_work_summary(source, activity)
    else:
        work = work_summary_for_activity(activity, intervals)

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


def format_session_activity(
    activity: Activity,
    intervals: list[Interval],
    category: str | None = None,
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

    if category:
        lines.append(f"- Category: {category}")

    lines.extend(_activity_metric_lines(activity, detailed=True))
    lines.extend(_activity_description_lines(activity, detailed=True))

    if intervals:
        lines.append("\n### Intervals")
        lines.extend(format_interval_table(intervals))

    points = []

    if intervals and (
        is_lt1_activity(activity) or is_subt_activity(activity)
    ):
        points = subt_work_points(activity, intervals)

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
        "Work km / week | Avg pace | Avg HR | Max HR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
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
            f"{_hr_cell(summary.max_hr)} |"
        )

    for summary in summaries:
        lines.append(row(subt_category_label(summary.category), summary))

    lines.append(row("**Total**", total))

    return lines


def format_subt_block_table(blocks: list[SubtBlock]):
    """Render one category's work blocks as a Markdown table."""
    lines = [
        "| Date | Session | Reps | Work time | Work km | Pace | "
        "Fastest | Slowest | Avg HR | Max HR |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
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
            f"{_hr_cell(block.max_hr)} |"
        )

    return lines
