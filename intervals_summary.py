#!/usr/bin/env python3

import os
import sys
import requests

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


    def wellness(self, start):

        return self.get(
            "wellness",
            {
                "oldest": start.isoformat(),
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

def summarize_training(activities):

    run_types = {
        "Run",
        "Trail Run",
    }

    result = {
        "run_time": 0,
        "run_distance": 0,
        "run_load": 0,

        "cross_time": 0,
        "cross_load": 0,

        "quality": [],
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


        if sport in run_types:

            result["run_time"] += time
            result["run_distance"] += distance
            result["run_load"] += load


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
def daily():

    today = date.today()

    yesterday = today - timedelta(days=1)


    api = Intervals()


    activities = api.activities(
        yesterday,
        today
    )

    wellness = api.wellness(
        yesterday
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
                "Trail Run"
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


    else:

        lines.append(
            "- No activity"
        )


    # -----------------------------
    # Recovery
    # -----------------------------

    lines.append(
        "\n## Night"
    )


    lines.append(
        f"- HRV: {recovery['hrv']} ms"
    )

    lines.append(
        f"- RHR: {recovery['rhr']} bpm"
    )

    lines.append(
        f"- Sleep: "
        f"{fmt_time(recovery['sleep'])}"
    )


    # -----------------------------
    # Planned
    # -----------------------------

    lines.append(
        "\n## Today"
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

        start = today - timedelta(days=8)

    elif period == "monthly":

        start = today - timedelta(days=30)

    else:

        raise ValueError(period)


    api = Intervals()


    training = summarize_training(
        api.activities(start,yesterday)
    )

    recovery = recovery_summary(
        api.wellness(start)
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
        f"- Time: {fmt_time(training['run_time'])}"
    )

    lines.append(
        f"- Distance: "
        f"{training['run_distance']/1000:.1f} km"
    )

    lines.append(
        f"- Load: "
        f"{training['run_load']:.0f}"
    )


    lines.append("\n## Cross training")

    lines.append(
        f"- Time: {fmt_time(training['cross_time'])}"
    )

    lines.append(
        f"- Load: "
        f"{training['cross_load']:.0f}"
    )


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

    elif mode in ("weekly","monthly"):
        report = summary(mode)

    else:
        raise SystemExit(
            "usage: intervals_report.py daily|weekly|monthly"
        )


    print(report)
