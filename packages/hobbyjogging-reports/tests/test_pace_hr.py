import unittest
from datetime import date

from hobbyjogging_report.analysis import pace_hr_points
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

    def test_speed_is_reciprocal_pace(self):
        points = pace_hr_points(
            [activity(id="a", date=D, distance_m=10000, avg_hr=140)],
            D,
            D,
        )

        self.assertAlmostEqual(1000 / 360, points[0].speed_m_s)


if __name__ == "__main__":
    unittest.main()
