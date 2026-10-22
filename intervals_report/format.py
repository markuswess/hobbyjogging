"""Report formatting.

All helpers take model objects (see ``model.py``), so reports work with
any ``DataSource`` implementation.
"""

from .analysis import (
    RUN_TYPES,
    is_lt1_activity,
    is_subt_activity,
    subt_work_points,
)
from .classify import classify
from .model import Activity, Interval, SubtPoint, WellnessDay
from .sources.base import DataSource


SPORT_LABELS = {
    "run": "Run",
    "trail_run": "TrailRun",
}


def sport_label(item):

    return SPORT_LABELS.get(
        item.type,
        item.type.replace("_", " ").title(),
    )


def fmt_time(seconds):

    if not seconds:
        return "-"

    seconds = int(seconds)

    minutes = seconds // 60

    h = minutes // 60
    m = minutes % 60

    if h:
        return f"{h}h{m:02d}"

    return f"{m}min"


def fmt_zones(zone_times):

    if not zone_times:
        return "-"

    return " | ".join(
        f"Z{i+1} {fmt_time(t)}"
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

    try:

        sec = (
            activity.duration_s
            /
            activity.distance_m
            *
            1000
        )

        return (
            f"{int(sec//60)}:"
            f"{int(sec%60):02d}/km"
        )

    except Exception:
        return "-"


def format_work_result(point: SubtPoint, label: str | None = None):

    duration = point.avg_rep_s

    mins = int(duration // 60)
    secs = round(duration % 60)

    if secs == 60:
        mins += 1
        secs = 0

    interval_duration = f"{mins}:{secs:02d}"
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


def format_subt_result(point: SubtPoint):
    """Backward-compatible subT formatter."""
    return format_work_result(point)


def last_four_nights(wellness):

    wellness = sorted(
        wellness,
        key=lambda x: x.date,
        reverse=True,
    )

    return wellness[:4]


def zone_3_4_time(zone_times):
    """Return combined time spent in zones 3 and 4."""
    if not zone_times:
        return 0

    return sum(zone_times[2:4])


def summarize_training(activities: list[Activity]):

    result = {
        "run_time": 0,
        "run_distance": 0,
        "run_load": 0,

        "cross_time": 0,
        "cross_load": 0,

        "quality": [],
        "z3_z4_time": 0,
        "rpe": 0,
    }

    for a in activities:

        time = a.duration_s
        distance = a.distance_m
        load = a.training_load or 0
        rpe = a.rpe or 0

        if a.type in RUN_TYPES:
            result["run_time"] += time
            result["run_distance"] += distance
            result["run_load"] += load
            result["rpe"] += rpe

            category = classify(a)

            # Warm-ups/cool-downs are quality in the breakdown, but they
            # would clutter the per-session detail list.
            if category.quality and category.kind != "race-support":
                result["quality"].append(a)

        if a.type == "run":
            result["z3_z4_time"] += zone_3_4_time(
                a.pace_zone_times
            )

        elif a.type == "trail_run":
            result["z3_z4_time"] += zone_3_4_time(
                a.hr_zone_times
            )

        else:
            result["cross_time"] += time
            result["cross_load"] += load

    return result


def recovery_summary(wellness: list[WellnessDay]):

    def avg(values):

        return (
            round(sum(values)/len(values),1)
            if values
            else None
        )

    hrv = []
    rhr = []
    sleep = []

    for w in wellness:

        if w.hrv:
            hrv.append(w.hrv)

        if w.resting_hr:
            rhr.append(w.resting_hr)

        if w.sleep_s:
            sleep.append(w.sleep_s)

    return {
        "hrv": avg(hrv),
        "rhr": avg(rhr),
        "sleep": avg(sleep),
    }


def latest_recovery(wellness: list[WellnessDay]):

    if not wellness:
        return {
            "hrv": None,
            "rhr": None,
            "sleep": None,
        }

    w = max(wellness, key=lambda x: x.date)

    return {
        "hrv": w.hrv,
        "rhr": w.resting_hr,
        "sleep": w.sleep_s,
    }


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


def subt_summary_for_activity(
    activity: Activity,
    intervals: list[Interval],
):
    """Backward-compatible alias for work_summary_for_activity."""
    return work_summary_for_activity(activity, intervals)


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


def get_subt_summary(
    source: DataSource,
    activity: Activity,
):
    """Backward-compatible alias for get_work_summary."""
    return get_work_summary(source, activity)


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

    lines.append(f"- Duration: {fmt_time(activity.duration_s)}")

    if activity.distance_m:
        lines.append(f"- Distance: {activity.distance_m/1000:.1f} km")

    if activity.type in RUN_TYPES:
        lines.append(f"- Pace: {pace(activity)}")

    if activity.avg_hr:
        lines.append(f"- HR: {activity.avg_hr:.0f} avg")

    if activity.training_load:
        lines.append(f"- Load: {activity.training_load:.0f}")

    if activity.rpe:
        lines.append(f"- RPE: {activity.rpe:.0f}")

    if activity.pace_zone_times:
        lines.append(
            f"- Pace zones: {fmt_zones(activity.pace_zone_times)}"
        )

    if activity.description:
        lines.append(f"- Description: {activity.description}")

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
