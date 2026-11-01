import json
import sys
from datetime import date, timedelta

from hobbyjogging_core.datasource import DataSource

from .analysis import (
    activity_sort_key,
    is_lt1_activity,
    is_subt_activity,
)
from .api import Intervals
from .classify import category_breakdown, classify
from .format import (
    fmt_time,
    format_activity,
    format_category_table,
    format_feel,
    last_four_nights,
    pace,
    recovery_summary,
    sport_label,
    summarize_training,
    work_summary_for_activity,
)
from .sources import DEFAULT_SOURCE, create_source


def debug():

    api = Intervals()

    today = date.today()
    yesterday = today - timedelta(days=2)

    activities = api.activities(
        yesterday,
        today,
    )

    wellness = api.wellness(
        yesterday - timedelta(days=3),
        today
    )

    events = api.events(
        today,
        today + timedelta(days=1),
    )

    resource = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "all"
    )

    if resource == "activities":
        data = activities

    elif resource == "wellness":
        data = wellness

    elif resource == "events":
        data = events

    elif resource == "all":
        data = {
            "activities": activities,
            "wellness": wellness,
            "events": events,
        }
    elif resource == "intervals":

        if not activities:
            print("No activities found")
            return

        activity = api.get_activity(
            activities[2]["id"]
        )

        print(
            json.dumps(
                activity.get("icu_intervals"),
                indent=2,
                ensure_ascii=False,
            )
        )

        return
    else:
        raise SystemExit(
            "usage: intervals_report.py debug "
            "[activities|wellness|events]"
        )

    print(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )
    )

def session_report(day: date, source: DataSource | None = None) -> str:
    """Render one day's activities with categories and work intervals."""
    if source is None:
        with create_source(DEFAULT_SOURCE) as source:
            return session_report(day, source)

    activities = source.activities(day, day)

    lines = [f"# Session {day}"]

    if not activities:
        lines.append("\n- No activity")
        return "\n".join(lines)

    for activity in sorted(activities, key=activity_sort_key):
        try:
            intervals = source.activity_intervals(activity.id)
        except Exception:
            intervals = []

        category = classify(activity, intervals)

        lines.extend(
            format_activity(
                source,
                activity,
                f"{sport_label(activity)} — {activity.name}",
                category=category.path,
                intervals=intervals,
            )
        )

    return "\n".join(lines)


def daily(source: DataSource | None = None):

    if source is None:
        with create_source(DEFAULT_SOURCE) as source:
            return daily(source)

    today = date.today()

    yesterday = today - timedelta(days=1)

    activities = source.activities(
        yesterday,
        yesterday
    )

    wellness = source.wellness(
        today - timedelta(days=4),
        today
    )

    events = source.events(
        today,
        today
    )

    activities_today = source.activities(
        today,
        today
    )

    lines = []


    lines.append(
        f"# Daily Training Report {today}"
    )


    # -----------------------------
    # Yesterday
    # -----------------------------

    lines.append(
        "\n## Yesterday"
    )


    if activities:

        # newest first
        activities.sort(key=activity_sort_key)

        for a in activities:

            heading = (
                f"{sport_label(a)} "
                f"{a.name}"
            )

            lines.extend(
                format_activity(source, a, heading)
            )

    else:

        lines.append(
            "- No activity"
        )


    # -----------------------------
    # Recovery
    # -----------------------------
    lines.append("\n## Night")

    nights = last_four_nights(wellness)

    for w in reversed(nights):

        night_date = w.date

        hrv = w.hrv
        rhr = w.resting_hr
        sleep = w.sleep_s

        lines.append(
            f"- {night_date}: "
            + (
            f"HRV {hrv:.0f} ms, " if hrv is not None else "HRV N/A, ")
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

    # -----------------------------
    # Today
    # -----------------------------
    
    if activities_today:

        # newest first
        activities_today.sort(key=activity_sort_key)

        for a in activities_today:

            heading = (
                f"Today:  {sport_label(a)} "
                f"{a.name}"
            )

            lines.extend(
                format_activity(source, a, heading)
            )

    else:
        lines.append(
            "\n## Planned Today"
        )


        if events:

            for e in events:

                lines.append(
                    f"\n### {e.name}"
                )

                if e.type:

                    lines.append(
                        f"- Type: {sport_label(e)}"
                    )

                if e.description:

                    lines.append(
                        e.description
                    )

                if e.duration_s:

                    lines.append(
                        f"- Duration: "
                        f"{fmt_time(e.duration_s)}"
                    )

                if e.distance_m:

                    lines.append(
                        f"- Distance: "
                        f"{e.distance_m/1000:.1f} km"
                    )


        else:

            lines.append(
                "- No planned session"
            )


    return "\n".join(lines)

def period_report(
    start: date,
    end: date,
    title: str,
    source: DataSource | None = None,
) -> str:
    """Render a summary for an inclusive date range."""
    if start > end:
        raise ValueError("start must not be after end")

    if source is None:
        with create_source(DEFAULT_SOURCE) as source:
            return period_report(start, end, title, source)

    ndays = (end - start).days + 1

    activities = sorted(source.activities(start, end), key=activity_sort_key)

    training = summarize_training(activities)

    # subT/LT1 names need intervals for their work-interval details.
    intervals_by_id = {}

    for activity in activities:

        if not (
            is_subt_activity(activity)
            or is_lt1_activity(activity)
        ):
            continue

        try:
            intervals_by_id[activity.id] = (
                source.activity_intervals(activity.id)
            )
        except Exception:
            continue

    breakdown = category_breakdown(activities, intervals_by_id)

    recovery = recovery_summary(
        source.wellness(start, end)
    )

    lines = []

    lines.append(
        f"# {title}"
    )

    lines.append(
        f"{start} → {end}"
    )

    lines.append("\n## Running (avg. per week)")

    lines.append(
        f"- Time: {fmt_time(training['run_time']/ndays*7)}"
    )

    lines.append(
        f"- Distance: "
        f"{training['run_distance']/1000/ndays*7:.1f} km"
    )

    lines.append(
        f"- Load: "
        f"{training['run_load']/ndays*7:.0f}"
    )

    lines.append(
        f"- RPE: "
        f"{training['rpe']/ndays*7:.0f}"
    )

    if training["run_feel_count"]:
        lines.append(
            f"- Feel: "
            f"{training['run_feel']/training['run_feel_count']:.1f} avg"
        )

    lines.append(
        f"- Time in Zones 3 and 4: "
        f"{fmt_time(training['z3_z4_time']/ndays*7)}"
    )

    lines.append("\n## Cross training (avg. per week)")

    lines.append(
        f"- Time: {fmt_time(training['cross_time']/ndays*7)}"
    )

    lines.append(
        f"- Load: "
        f"{training['cross_load']/ndays*7:.0f}"
    )

    if training["cross_feel_count"]:
        lines.append(
            f"- Feel: "
            f"{training['cross_feel']/training['cross_feel_count']:.1f} avg"
        )

    lines.append("\n## Categories (period totals)")

    lines.extend(
        format_category_table(breakdown)
    )

    if len(training["quality"]) < 10:
        lines.append("\n## Quality sessions")

        for q in training["quality"]:

            intervals = intervals_by_id.get(q.id)

            if intervals is None:
                intervals = source.activity_intervals(q.id)

            work = work_summary_for_activity(q, intervals)

            hr = f"{q.avg_hr:.0f}" if q.avg_hr is not None else "-"

            feel = (
                f", feel {format_feel(q.feel)}"
                if q.feel is not None
                else ""
            )

            lines.append(
                f"### Planned: {q.name}: "
                f"\n    Totals: {fmt_time(q.duration_s)}, "
                f"{pace(q)},"
                f" {hr} BpM{feel}")

            if work:
                lines.append(f"    Work intervals done:")

                for line in work:
                    lines.append(f"    - {line}")

            lines.append(f"    Comments: {q.description}")

    lines.append("\n## Recovery")

    lines.append(
        f"- HRV avg: {recovery['hrv']}"
    )

    lines.append(
        f"- RHR avg: {recovery['rhr']}"
    )

    lines.append(
        f"- Sleep avg: {fmt_time(recovery['sleep'])}"
    )

    return "\n".join(lines)


def summary(period, source: DataSource | None = None):
    """Render one of the fixed weekly, monthly or yearly reports."""
    today = date.today()
    end = today - timedelta(days=1)

    if period == "weekly":
        ndays = 7

    elif period == "monthly":
        ndays = 30

    elif period == "yearly":
        ndays = 365

    else:
        raise ValueError(period)

    start = today - timedelta(days=ndays)

    return period_report(
        start,
        end,
        f"{period.title()} Training Report",
        source=source,
    )
