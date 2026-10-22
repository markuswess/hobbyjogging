#!/usr/bin/env python3

import os
import sys
import requests
import json

from datetime import date, timedelta


ATHLETE_ID = os.environ["INTERVALS_ATHLETE_ID"]
API_KEY = os.environ["INTERVALS_API_KEY"]


# -------------------------------------------------
# API
# -------------------------------------------------

class Intervals:

    def __init__(self):
        self.base = (
            f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
        )
        self.auth = ("API_KEY", API_KEY)


    def get(self, endpoint, params=None):

        r = requests.get(
            f"{self.base}/{endpoint}",
            auth=self.auth,
            params=params,
            timeout=20,
        )

        r.raise_for_status()

        return r.json()


    def activities(self, start, end):

        return self.get(
            "activities",
            {
                "oldest": start.isoformat(),
                "newest": end.isoformat(),
            },
        )

    def wellness(self, start, end):

        return self.get(
            "wellness",
            {
                "oldest": start.isoformat(),
                "newest": end.isoformat(),
            },
        )


    def events(self, start, end):

        return self.get(
            "events",
            {
                "oldest": start.isoformat(),
                "newest": end.isoformat(),
            },
        )

    def get_activity(self, activity_id):

        r = requests.get(
            f"https://intervals.icu/api/v1/activity/{activity_id}",
            auth=self.auth,
            params={"intervals": "true"},
            timeout=20,
        )

        r.raise_for_status()

        return r.json()

# -------------------------------------------------
# Formatting
# -------------------------------------------------

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


def pace(activity):

    try:

        sec = (
            activity["moving_time"]
            /
            activity["distance"]
            *
            1000
        )

        return (
            f"{int(sec//60)}:"
            f"{int(sec%60):02d}/km"
        )

    except Exception:
        return "-"

def format_subt_result(result):

    duration = result["duration"] / result["count"]

    mins = int(duration // 60)
    secs = round(duration % 60)

    if secs == 60:
        mins += 1
        secs = 0

    interval_duration = f"{mins}:{secs:02d}"

    return (
        f'{result["count"]}x{interval_duration} '
        f'subT-{result["category"]}: '
        f'{format_pace(result["pace"])}/km, '
        f'{result["hr"]} bpm'
    )
def format_subt_summary(sessions):

    if not sessions:
        return []

    lines = ["## SubT"]

    categories = [
        ("short", "Short"),
        ("medium", "Medium"),
        ("long", "Long"),
    ]

    for category, label in categories:

        data = [
            s for s in sessions
            if s["category"] == category
        ]

        if not data:
            continue

        # Chronological
        data.sort(key=lambda x: x["date"])

        values = []

        for s in data:
            pace = format_pace(s["pace"])
            values.append(pace)

        # One value: just show it
        if len(values) == 1:
            pace_text = values[0]

        else:
            pace_text = " → ".join(values)

        hr_values = [
            str(s["hr"])
            for s in data
            if s["hr"] is not None
        ]

        if len(hr_values) == 1:
            hr_text = hr_values[0]
        elif hr_values:
            hr_text = " → ".join(hr_values)
        else:
            hr_text = "-"

        # Use the latest workout's structure
        latest = data[-1]

        duration = latest["duration"]
        mins = int(duration // 60)
        secs = round(duration % 60)

        if secs == 60:
            mins += 1
            secs = 0

        interval = f"{mins}:{secs:02d}"

        lines.append(
            f"- {label}: {len(data)} session"
            f"{'s' if len(data) != 1 else ''}, "
            #f"{latest['count']}x{interval} — "
            f"{pace_text}/km, HR {hr_text}"
        )

    return lines
# -------------------------------------------------
# Analysis
# -------------------------------------------------

def last_four_nights(wellness):

    wellness = sorted(
        wellness,
        key=lambda x: x.get("id", ""),
        reverse=True,
    )

    return wellness[:4]

def zone_3_4_time(zone_times):
    """Return combined time spent in zones 3 and 4."""
    if not zone_times:
        return 0

    return sum(zone_times[2:4])

def summarize_training(activities):

    run_types = {
        "Run",
        "TrailRun",
    }

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

        sport = a.get("type","")

        time = a.get(
            "moving_time",
            0
        )

        distance = a.get(
            "distance",
            0
        )

        load = (
            a.get("icu_training_load")
            or 0
        )

        rpe = (
            a.get("icu_rpe")
            or 0
        )


        if sport in run_types:
            result["run_time"] += time
            result["run_distance"] += distance
            result["run_load"] += load
            result["rpe"] += rpe 


            name = a.get(
                "name",
                ""
            ).lower()


            if any(
                x in name
                for x in [
                    "interval",
                    "tempo",
                    "threshold",
                    "subt",
                    "lt1",
                    "race",
                    "berg",
                ]
            ):
                result["quality"].append(a)

        if sport == "Run":
            result["z3_z4_time"] += zone_3_4_time(
                a.get("pace_zone_times")
            )

        elif sport == "TrailRun":

            result["z3_z4_time"] += zone_3_4_time(
                a.get("icu_hr_zone_times")
            )

        else:

            result["cross_time"] += time
            result["cross_load"] += load


    return result



def recovery_summary(wellness):

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

        if w.get("hrv"):
            hrv.append(w["hrv"])

        if w.get("restingHR"):
            rhr.append(w["restingHR"])

        if w.get("sleepSecs"):
            sleep.append(w["sleepSecs"])


    return {
        "hrv": avg(hrv),
        "rhr": avg(rhr),
        "sleep": avg(sleep),
    }

def latest_recovery(wellness):

    if not wellness:
        return {
            "hrv": None,
            "rhr": None,
            "sleep": None,
        }

    # newest entry
    w = sorted(
        wellness,
        key=lambda x: x.get("id", ""),
        reverse=True
    )[0]

    return {
        "hrv": w.get("hrv"),
        "rhr": w.get("restingHR"),
        "sleep": w.get("sleepSecs"),
    }
def pace_from_speed(speed):
    """Return pace as seconds/km."""
    if not speed or speed <= 0:
        return None
    return 1000 / speed


def format_pace(seconds):
    """Format seconds/km as M:SS."""
    if seconds is None:
        return "-"
    seconds = round(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def classify_subt(duration):
    """Classify subT interval length."""
    if duration <= 240:
        return "short"
    elif duration <= 350:
        return "medium"
    else:
        return "long"


def extract_subt_intervals(intervals):
    """
    Extract WORK blocks from an Intervals.icu icu_intervals list.

    Returns one entry per group_id.
    """

    work = [
        i for i in intervals
        if i.get("type") == "WORK"
        and i.get("moving_time")
        and i.get("distance")
    ]

    groups = {}

    for interval in work:
        group_id = interval.get("group_id")

        # If there is no group_id, keep it as its own group.
        if not group_id:
            group_id = f"interval-{interval['id']}"

        groups.setdefault(group_id, []).append(interval)

    results = []

    for group_id, group in groups.items():

        # Sort chronologically
        group.sort(key=lambda x: x["start_time"])

        total_time = sum(
            i["moving_time"] for i in group
        )

        total_distance = sum(
            i["distance"] for i in group
        )

        if total_time <= 0 or total_distance <= 0:
            continue

        avg_speed = total_distance / total_time
        avg_pace = pace_from_speed(avg_speed)

        # Time-weighted HR
        hr_values = [
            (i["average_heartrate"], i["moving_time"])
            for i in group
            if i.get("average_heartrate") is not None
        ]

        if hr_values:
            avg_hr = (
                sum(hr * t for hr, t in hr_values)
                / sum(t for _, t in hr_values)
            )
            avg_hr = round(avg_hr)
        else:
            avg_hr = None

        results.append({
            "group_id": group_id,
            "count": len(group),
            "duration": total_time,
            "distance": total_distance,
            "pace": avg_pace,
            "hr": avg_hr,
            "category": classify_subt(total_time / len(group)),
        })

    return results

def get_subt_summary(api, activity):
    """Return compact subT interval summary for an activity."""

    name = (activity.get("name") or "").lower()
    description = (activity.get("description") or "").lower()

    # Only inspect activities that look like subT workouts.
    if "subt" not in name and "subt" not in description:
        return None

    try:
        detailed = api.get_activity(activity["id"])
        intervals = detailed.get("icu_intervals", [])
    except Exception:
        return None

    results = extract_subt_intervals(intervals)

    if not results:
        return None

    return [
        format_subt_result(result)
        for result in results
    ]


def get_subt_sessions(api, activities):
    """Extract subT workout blocks from a list of activities."""

    sessions = []

    for activity in activities:

        name = (activity.get("name") or "").lower()
        description = (activity.get("description") or "").lower()

        if "subt" not in name and "subt" not in description:
            continue

        try:
            detailed = api.get_activity(activity["id"])
            intervals = detailed.get("icu_intervals", [])
        except Exception:
            continue

        results = extract_subt_intervals(intervals)

        for result in results:

            sessions.append({
                "date": activity["start_date_local"][:10],
                "category": result["category"],
                "count": result["count"],
                "duration": result["duration"] / result["count"],
                "pace": result["pace"],
                "hr": result["hr"],
            })

    return sessions
# -------------------------------------------------
# Reports
# -------------------------------------------------
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


def format_activity(api, a, heading):

    lines = [
        f"\n### {heading}",
        f"- Duration: {fmt_time(a.get('moving_time'))}",
    ]

    if a.get("distance"):
        lines.append(f"- Distance: {a['distance']/1000:.1f} km")

    if a.get("type") in ("Run", "TrailRun"):
        lines.append(f"- Pace: {pace(a)}")

    if a.get("average_heartrate"):
        lines.append(f"- HR: {a['average_heartrate']:.0f} avg")

    if a.get("icu_training_load"):
        lines.append(f"- Load: {a['icu_training_load']:.0f}")

    if a.get("icu_rpe"):
        lines.append(f"- RPE: {a['icu_rpe']:.0f}")

    if a.get("pace_zone_times"):
        lines.append(f"- Pace zones: {fmt_zones(a['pace_zone_times'])}")

    if a.get("description"):
        lines.append(f"- Description: {a['description']}")

    subt = get_subt_summary(api, a)

    if subt:
        lines.append("\n### subT report")
        for line in subt:
            lines.append(f"- {line}")

    return lines


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
#    else:
#        subt_sessions = get_subt_sessions(
#            api,
#            training["quality"],
#        )
#
#        lines.extend(
#            format_subt_summary(subt_sessions)
#        )

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



# -------------------------------------------------
# Main
# -------------------------------------------------

if __name__ == "__main__":

    mode = sys.argv[1]

    if mode == "daily":
        report = daily()

    elif mode == "all":
        report = daily()
        report+="\n\n"
        report+=summary("weekly")
        report+="\n\n"
        report+=summary("monthly")
        report+="\n\n"
        report+=summary("yearly")

    elif mode in ("weekly","monthly", "yearly"):
        report = summary(mode)

    elif mode == "debug":
        debug()
        sys.exit(0)

    else:
        raise SystemExit(
            "usage: intervals_report.py daily|weekly|monthly|yearly|debug|all"
        )


    print(report)
