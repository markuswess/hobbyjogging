import math
import unittest
from datetime import date, timedelta

from hobbyjogging_report.analysis import daily_session_rpe, rpe_metrics
from support import activity_factory

D = date(2026, 1, 1)
activity = activity_factory()


class DailyRpeTests(unittest.TestCase):

    def test_mean_of_the_day_s_sessions(self):
        activities = [
            activity(id="a", date=D, rpe=4),
            activity(id="b", date=D, rpe=6),
            activity(id="c", date=D + timedelta(days=1), rpe=3),
        ]

        self.assertEqual(
            [(D, 5.0), (D + timedelta(days=1), 3.0)],
            daily_session_rpe(activities, D, D + timedelta(days=1)),
        )

    def test_unrated_sessions_are_skipped(self):
        activities = [activity(id="a", date=D, rpe=None)]

        self.assertEqual([], daily_session_rpe(activities, D, D))


class RpeMetricsTests(unittest.TestCase):

    def test_standing_value_carries_between_sessions(self):
        activities = [activity(id="a", date=D, rpe=4)]

        points = rpe_metrics(
            activities,
            D,
            D + timedelta(days=2),
            warmup_days=0,
        )

        self.assertEqual(
            [D, D + timedelta(days=1), D + timedelta(days=2)],
            [point.date for point in points],
        )
        self.assertEqual(4.0, points[0].rpe)
        self.assertIsNone(points[1].rpe)
        self.assertAlmostEqual(4.0, points[0].base)
        self.assertAlmostEqual(4.0, points[2].fatigue)

    def test_new_session_moves_the_fatigue_line_first(self):
        activities = [
            activity(id="a", date=D, rpe=2),
            activity(id="b", date=D + timedelta(days=1), rpe=8),
        ]

        points = rpe_metrics(
            activities,
            D,
            D + timedelta(days=1),
            warmup_days=0,
        )
        last = points[-1]
        alpha = 1 - math.exp(-1 / 7)

        self.assertAlmostEqual(8 * alpha + 2 * (1 - alpha), last.fatigue)
        self.assertLess(abs(last.base - 2.0), abs(last.fatigue - 2.0))

    def test_no_rpe_returns_no_points(self):
        self.assertEqual(
            [],
            rpe_metrics(
                [activity(id="a", date=D)],
                D,
                D + timedelta(days=1),
                warmup_days=0,
            ),
        )


if __name__ == "__main__":
    unittest.main()
