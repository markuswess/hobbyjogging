import unittest
from datetime import date, timedelta

from hobbyjogging_report.analysis import pace_hr_points, pace_hr_trends
from hobbyjogging_report.model import PaceHrPoint
from support import activity_factory

D = date(2026, 1, 1)
activity = activity_factory()


class PaceHrTests(unittest.TestCase):

    def test_one_point_per_run(self):
        activities = [
            activity(
                id="a",
                date=D,
                duration_s=1800,
                distance_m=5000,
                avg_hr=150,
                name="Easy",
            ),
            activity(
                id="b",
                date=date(2026, 1, 2),
                duration_s=1500,
                distance_m=5000,
                avg_hr=165,
                name="Tempo",
            ),
        ]

        points = pace_hr_points(activities, D, date(2026, 1, 2))

        self.assertEqual(["Easy", "Tempo"], [p.name for p in points])
        self.assertEqual(360.0, points[0].pace_s_per_km)
        self.assertEqual(150.0, points[0].avg_hr)

    def test_runs_without_hr_or_distance_are_skipped(self):
        activities = [
            activity(id="a", date=D, distance_m=0, avg_hr=150),
            activity(id="b", date=D, distance_m=5000, avg_hr=None),
            activity(id="c", date=D, distance_m=5000, avg_hr=150),
        ]

        points = pace_hr_points(activities, D, D)

        self.assertEqual(1, len(points))
        self.assertEqual(D, points[0].date)

    def test_cross_training_is_skipped(self):
        activities = [
            activity(
                id="a",
                date=D,
                type="ride",
                distance_m=20000,
                avg_hr=140,
            )
        ]

        self.assertEqual([], pace_hr_points(activities, D, D))

    def test_trends_are_fitted_per_half(self):
        points = []

        for index in range(10):
            speed = 2.5 + 0.1 * index
            base = 120 if index < 5 else 130
            points.append(
                PaceHrPoint(
                    D + timedelta(days=index),
                    pace_s_per_km=1000 / speed,
                    avg_hr=base + (speed - 3.0),
                )
            )

        trends = pace_hr_trends(points)

        self.assertEqual(
            ["first half", "second half"],
            [t.label for t in trends],
        )
        self.assertEqual(5, trends[0].points)
        self.assertAlmostEqual(2.5, trends[0].speed_low)
        self.assertAlmostEqual(2.9, trends[0].speed_high)
        self.assertAlmostEqual(1.0, trends[0].slope)
        self.assertAlmostEqual(117.0, trends[0].intercept)
        self.assertAlmostEqual(127.0, trends[1].intercept)

    def test_trends_need_four_points(self):
        points = [
            PaceHrPoint(D, 300.0, 150.0),
            PaceHrPoint(D, 290.0, 151.0),
            PaceHrPoint(D, 280.0, 152.0),
        ]

        self.assertEqual([], pace_hr_trends(points))

    def test_speed_is_reciprocal_pace(self):
        points = pace_hr_points(
            [activity(id="a", date=D, distance_m=10000, avg_hr=140)],
            D,
            D,
        )

        self.assertAlmostEqual(1000 / 360, points[0].speed_m_s)


if __name__ == "__main__":
    unittest.main()
