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


# -------------------------------------------------
# Reports
# -------------------------------------------------
def debug():

    api = Intervals()

    today = date.today()
    yesterday = today - timedelta(days=1)

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
#    import json
#    print(json.dumps(activities[0], indent=2))
    wellness = api.wellness(
        today-timedelta(days=4),
        today

    )

    events = api.events(
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

            lines.append(
                f"\n### {a.get('type','')} "
                f"{a.get('name','')}"
            )


            lines.append(
                f"- Duration: "
                f"{fmt_time(a.get('moving_time'))}"
            )


            if a.get("distance"):

                lines.append(
                    f"- Distance: "
                    f"{a['distance']/1000:.1f} km"
                )


            if a.get("type") in (
                "Run",
                "TrailRun"
            ):

                lines.append(
                    f"- Pace: {pace(a)}"
                )


            if a.get("average_heartrate"):

                lines.append(
                    f"- HR: "
                    f"{a['average_heartrate']:.0f} avg"
                )


            if a.get("icu_training_load"):

                lines.append(
                    f"- Load: "
                    f"{a['icu_training_load']:.0f}"
                )

            if a.get("icu_rpe"):

                lines.append(
                    f"- RPE: "
                    f"{a['icu_rpe']:.0f}"
                )

            if a.get("pace_zone_times"):
            #if 1:

                lines.append(
                    f"- Pace zones: "
                    f"{fmt_zones(a['pace_zone_times'])}"
                )

            if a.get("description"):
            #if 1:

                lines.append(
                    f"- Description: "
                    f"{a['description']}"
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
            f"HRV {hrv:.0f} ms, "
            f"RHR {rhr:.0f} bpm"
            + (
                f", Sleep {fmt_time(sleep)}"
                if sleep
                else ""
            )
        )

    # -----------------------------
    # Planned
    # -----------------------------

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


    lines.append("\n## Running")

    lines.append(
        f"- Avg. weekly Time: {fmt_time(training['run_time']/ndays*7)}"
    )

    lines.append(
        f"- Avg. weekly distance: "
        f"{training['run_distance']/1000/ndays*7:.1f} km"
    )

    lines.append(
        f"- Avg. weekly Load: "
        f"{training['run_load']/ndays*7:.0f}"
    )

    lines.append(
        f"- Avg. weekly RPE: "
        f"{training['rpe']/ndays*7:.0f}"
    )

    lines.append(
        f"- Avg. weekly Time in Zones 3 and 4: "
        f"{fmt_time(training['z3_z4_time']/ndays*7)}"
    )

    lines.append("\n## Cross training")

    lines.append(
        f"- Time: {fmt_time(training['cross_time'])}"
    )

    lines.append(
        f"- Avg. weekly Time: {fmt_time(training['cross_time']/ndays*7)}"
    )

    lines.append(
        f"- Load: "
        f"{training['cross_load']:.0f}"
    )

    lines.append(
        f"- Avg. weekly Load: "
        f"{training['cross_load']/ndays*7:.0f}"
    )

    if len(training["quality"])<10:
        lines.append("\n## Quality sessions")

        for q in training["quality"]:

            lines.append(
                f"- {q.get('name','')}: "
                f"{fmt_time(q.get('moving_time'))}, "
                f"{pace(q)}"
            )


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
