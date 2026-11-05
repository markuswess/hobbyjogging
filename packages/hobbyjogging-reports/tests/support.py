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
    ):
        self._activities = list(activities or [])
        self._intervals = dict(intervals or {})
        self._wellness = list(wellness or [])
        self._events = list(events or [])

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

    def activity_intervals(self, activity_id):
        return self._intervals.get(activity_id, [])
