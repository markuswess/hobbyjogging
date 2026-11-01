import os

import requests


# -------------------------------------------------
# API
# -------------------------------------------------

class Intervals:

    def __init__(self):
        athlete_id = os.environ.get("INTERVALS_ATHLETE_ID")
        api_key = os.environ.get("INTERVALS_API_KEY")
        if not athlete_id or not api_key:
            raise RuntimeError(
                "INTERVALS_ATHLETE_ID and INTERVALS_API_KEY must be set"
            )

        self.base = (
            f"https://intervals.icu/api/v1/athlete/{athlete_id}"
        )
        self.auth = ("API_KEY", api_key)
        self._intervals_cache = {}


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

    def get_activity_intervals(self, activity_id):
        """Return intervals for an activity, caching the result per id."""
        if activity_id not in self._intervals_cache:
            activity = self.get_activity(activity_id)
            self._intervals_cache[activity_id] = activity.get("icu_intervals") or []
        return self._intervals_cache[activity_id]
