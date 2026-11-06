import unittest
from datetime import date, timedelta

from hobbyjogging_report.recent import search_recent
from support import FakeSource, activity_factory

TODAY = date(2026, 10, 30)
activity = activity_factory()


def on(day_offset):
    return activity(date=TODAY - timedelta(days=day_offset))


class SearchRecentTests(unittest.TestCase):

    def test_returns_first_window_when_enough(self):
        source = FakeSource([on(0)])

        activities, excluded = search_recent(
            source,
            today=TODAY,
            enough=bool,
        )

        self.assertEqual(["a"], [a.id for a in activities])
        self.assertEqual(0, excluded)

    def test_keeps_widening_until_enough(self):
        source = FakeSource(
            [on(35), on(40)],
        )

        activities, _ = search_recent(
            source,
            today=TODAY,
            enough=lambda found: len(found) >= 2,
        )

        self.assertEqual(2, len(activities))

    def test_last_window_used_when_never_enough(self):
        source = FakeSource([on(400)])

        activities, excluded = search_recent(
            source,
            today=TODAY,
            enough=bool,
        )

        self.assertEqual(["a"], [a.id for a in activities])

    def test_excluded_count_covers_all_steps_searched(self):
        source = FakeSource(
            [
                on(0),
                activity(
                    date=TODAY - timedelta(days=35),
                    needs_review=True,
                ),
            ]
        )

        _, excluded = search_recent(
            source,
            today=TODAY,
            enough=lambda found: len(found) >= 2,
        )

        self.assertEqual(1, excluded)
