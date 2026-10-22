import os

import requests

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
