"""Shared fixtures for report tests."""

from datetime import date

from hobbyjogging_core.model import Activity, Interval


DEFAULT_DATE = date(2026, 10, 1)


def activity_factory(**defaults):
    """Return an ``activity()`` helper with per-module defaults."""
    def make(**overrides):
        values = dict(
            id="a",
            date=DEFAULT_DATE,
            type="run",
            name="",
            duration_s=3600,
        )
        values.update(defaults)
        values.update(overrides)
        return Activity(**values)

    return make


def make_interval(
    duration_s,
    distance_m,
    type="WORK",
    group_id=None,
    avg_hr=None,
    max_hr=None,
):
    return Interval(
        type=type,
        group_id=group_id or f"{duration_s}-{distance_m}",
        duration_s=duration_s,
        distance_m=distance_m,
        avg_hr=avg_hr,
        max_hr=max_hr,
    )


class FakeSource:
    """Small in-memory DataSource for report tests."""

    def __init__(
        self,
        activities=None,
        intervals=None,
        wellness=None,
        events=None,
        links=None,
        review_items=None,
        laps=None,
        equipment=None,
        weather=None,
        social=None,
        periods=None,
        thresholds=None,
        race_results=None,
        devices=None,
    ):
        self._activities = list(activities or [])
        self._equipment = list(equipment or [])
        self._intervals = dict(intervals or {})
        self._laps = dict(laps or {})
        self._wellness = list(wellness or [])
        self._events = list(events or [])
        self._links = dict(links or {})
        self._weather = dict(weather or {})
        self._social = dict(social or {})
        self._review_items = list(review_items or [])
        self._periods = list(periods or [])
        self._thresholds = list(thresholds or [])
        self._race_results = list(race_results or [])
        self._devices = list(devices or [])

    @staticmethod
    def _in_range(items, start, end):
        return [
            item
            for item in items
            if start <= item.date <= end
        ]

    def activities(self, start, end):
        return self._in_range(self._activities, start, end)

    def wellness(self, start, end):
        return self._in_range(self._wellness, start, end)

    def events(self, start, end):
        return self._in_range(self._events, start, end)

    def earliest_activity_date(self):
        return min(
            (activity.date for activity in self._activities),
            default=None,
        )

    def activity_intervals(self, activity_id):
        return self._intervals.get(activity_id, [])

    def activity_laps(self, activity_id):
        return self._laps.get(activity_id, [])

    def activity_weather(self, activity_id):
        return self._weather.get(activity_id)

    def activity_social(self, activity_id):
        return list(self._social.get(activity_id, []))

    def equipment(self):
        return list(self._equipment)

    def training_periods(self):
        return list(self._periods)

    def athlete_thresholds(self):
        return list(self._thresholds)

    def devices(self):
        return list(self._devices)

    def race_results(self):
        return list(self._race_results)

    def activity_links(self, activity_id):
        return self._links.get(activity_id)

    def review_items(self, *, status="open", category=None):
        items = [
            item
            for item in self._review_items
            if status in ("all", "", item.status)
        ]

        if category is not None:
            items = [item for item in items if item.category == category]

        return items
