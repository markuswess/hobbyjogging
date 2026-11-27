import unittest
from datetime import date, timedelta

from hobbyjogging_report.sources.cache import CachedDataSource
from support import FakeSource, activity_factory

D = date(2026, 1, 10)
activity = activity_factory()


class CachedDataSourceTests(unittest.TestCase):

    def _source(self):
        return FakeSource(
            [
                activity(id=str(index), date=D + timedelta(days=index))
                for index in range(-5, 6)
            ],
            intervals={"a": []},
            laps={"a": []},
        )

    def test_narrow_range_is_served_from_a_cached_range(self):
        cached = CachedDataSource(self._source())

        broad = cached.activities(D - timedelta(days=5), D + timedelta(days=5))
        narrow = cached.activities(D - timedelta(days=1), D + timedelta(days=1))

        self.assertEqual(11, len(broad))
        self.assertEqual(3, len(narrow))
        self.assertEqual(1, cached.query_counts["activities"])

    def test_weather_is_cached_by_activity(self):
        source = FakeSource(
            [activity(id="a", date=D)],
            weather={"a": object()},
        )
        cached = CachedDataSource(source)

        first = cached.activity_weather("a")
        second = cached.activity_weather("a")

        self.assertIs(first, second)
        self.assertEqual(1, cached.query_counts["activity_weather"])

    def test_disjoint_range_queries_again(self):
        cached = CachedDataSource(self._source())

        cached.activities(D, D)
        cached.activities(D - timedelta(days=5), D - timedelta(days=3))

        self.assertEqual(2, cached.query_counts["activities"])

    def test_intervals_and_laps_are_cached_by_activity_id(self):
        cached = CachedDataSource(self._source())

        first = cached.activity_intervals("missing")
        second = cached.activity_intervals("missing")
        laps = cached.activity_laps("missing")

        self.assertEqual([], first)
        self.assertEqual([], second)
        self.assertEqual([], laps)
        self.assertEqual(1, cached.query_counts["activity_intervals"])
        self.assertEqual(1, cached.query_counts["activity_laps"])

    def test_test_splits_are_cached_by_activity_id(self):
        cached = CachedDataSource(self._source())

        first = cached.activity_test_splits("missing")
        second = cached.activity_test_splits("missing")

        self.assertEqual([], first)
        self.assertEqual([], second)
        self.assertEqual(1, cached.query_counts["activity_test_splits"])

    def test_other_queries_delegate(self):
        cached = CachedDataSource(self._source())

        self.assertEqual([], cached.wellness(D, D))
        self.assertEqual([], cached.events(D, D))


if __name__ == "__main__":
    unittest.main()
