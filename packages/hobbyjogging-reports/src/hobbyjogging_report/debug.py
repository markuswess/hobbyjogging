"""Raw Intervals.icu payload dump for debugging."""

import json
from datetime import date, timedelta

from .api import Intervals


def debug(resource: str = "all"):
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
            activities[0]["id"]
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
            "usage: hobbyjogging_report debug "
            "[activities|wellness|events|intervals|all]"
        )

    print(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )
    )
