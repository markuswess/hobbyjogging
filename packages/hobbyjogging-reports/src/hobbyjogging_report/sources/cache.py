"""Read-only query cache for one dashboard build."""

from __future__ import annotations

from collections import Counter
from datetime import date

from hobbyjogging_core.datasource import DataSource
from hobbyjogging_core.model import Activity, Interval, Lap


class CachedDataSource:
    """Memoize the queries a dashboard build repeats.

    ``activities`` caches whole ranges and serves narrower requests from a
    cached range that covers them. Intervals and laps are cached by activity
    id, which is where most of the duplicate queries come from.
    """

    def __init__(self, source: DataSource):
        self._source = source
        self._ranges: list[tuple[date, date, list[Activity]]] = []
        self._intervals: dict[str, list[Interval]] = {}
        self._laps: dict[str, list[Lap]] = {}
        self.query_counts: Counter[str] = Counter()

    def activities(self, start: date, end: date) -> list[Activity]:
        for cached_start, cached_end, rows in self._ranges:
            if cached_start <= start and end <= cached_end:
                return [row for row in rows if start <= row.date <= end]

        rows = list(self._source.activities(start, end))
        self.query_counts["activities"] += 1
        self._ranges.append((start, end, rows))
        return list(rows)

    def activity_intervals(self, activity_id: str) -> list[Interval]:
        if activity_id not in self._intervals:
            self._intervals[activity_id] = list(
                self._source.activity_intervals(activity_id)
            )
            self.query_counts["activity_intervals"] += 1

        return list(self._intervals[activity_id])

    def activity_laps(self, activity_id: str) -> list[Lap]:
        if activity_id not in self._laps:
            self._laps[activity_id] = list(
                self._source.activity_laps(activity_id)
            )
            self.query_counts["activity_laps"] += 1

        return list(self._laps[activity_id])

    def __getattr__(self, name):
        return getattr(self._source, name)
