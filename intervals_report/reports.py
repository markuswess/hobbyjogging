import json
import sys
from datetime import date, timedelta

from .api import Intervals
from .format import (
    fmt_time,
    format_activity,
    get_subt_summary,
    last_four_nights,
    latest_recovery,
    pace,
    recovery_summary,
    summarize_training,
)


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

def daily():

    today = date.today()

    yesterday = today - timedelta(days=1)


    api = Intervals()

    activities = api.activities(
        yesterday,
        yesterday 
    )

    wellness = api.wellness(
        today-timedelta(days=4),
        today

    )
    
    events = api.events(
        today,
        today
    )

    activities_today = api.activities(
        today,
        today
    )



    recovery = latest_recovery(
        wellness
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
        activities.sort(
            key=lambda x: x.get(
                "start_date_local",
                ""
            )
        )


        for a in activities:

            heading = (
                f"{a.get('type','')} "
                f"{a.get('name','')}"
            )

            lines.extend(
                format_activity(api, a, heading)
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

        night_date = w.get("id", "")

        hrv = w.get("hrv")
        rhr = w.get("restingHR")
        sleep = w.get("sleepSecs")

        lines.append(
            f"- {night_date}: "
            + (
            f"HRV {hrv:.0f} ms, " if hrv is not None else "HRV N/A, ")
            +
            f"RHR {rhr:.0f} bpm"
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
        activities_today.sort(
            key=lambda x: x.get(
                "start_date_local",
                ""
            )
        )


        for a in activities_today:

            heading = (
                f"Today:  {a.get('type','')} "
                f"{a.get('name','')}"
            )

            lines.extend(
                format_activity(api, a, heading)
            )

    else:
        lines.append(
            "\n## Planned Today"
        )


        if events:

            for e in events:

                lines.append(
                    f"\n### {e.get('name','')}"
                )


                if e.get("type"):

                    lines.append(
                        f"- Type: {e['type']}"
                    )


                if e.get("description"):

                    lines.append(
                        e["description"]
                    )


                if e.get("duration"):

                    lines.append(
                        f"- Duration: "
                        f"{fmt_time(e['duration'])}"
                    )


                if e.get("distance"):

                    lines.append(
                        f"- Distance: "
                        f"{e['distance']/1000:.1f} km"
                    )


        else:

            lines.append(
                "- No planned session"
            )


    return "\n".join(lines)

def summary(period):

    today = date.today()
    yesterday = date.today() - timedelta(days=1)

    if period == "weekly":
        ndays = 7

    elif period == "monthly":
        ndays = 30

    elif period == "yearly":
        ndays = 365

    else:
        raise ValueError(period)

    start = today - timedelta(days=ndays)

    api = Intervals()


    training = summarize_training(
        api.activities(start,yesterday)
    )

    recovery = recovery_summary(
        api.wellness(start, yesterday)
    )


    lines = []

    lines.append(
        f"# {period.title()} Training Report"
    )

    lines.append(
        f"{start} → {yesterday}"
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

    if len(training["quality"])<10:
        lines.append("\n## Quality sessions")

        for q in training["quality"]:

            subt = get_subt_summary(api, q)
            lines.append(
                f"### Planned: {q.get('name','')}: "
                f"\n    Totals: {fmt_time(q.get('moving_time'))}, "
                f"{pace(q)},"
                f" {q.get('average_heartrate')} BpM")
            if subt:
                lines.append(f"    Work intervals done:")
                for line in subt:
                    lines.append(f"    - {line}")
            lines.append(f"    Comments: {q.get('description')}")

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
