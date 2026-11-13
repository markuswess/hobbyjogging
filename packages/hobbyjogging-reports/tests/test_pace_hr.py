import unittest
from dataclasses import replace
from datetime import date, timedelta

from hobbyjogging_report.analysis import (
    pace_hr_efficiency_lines,
    pace_hr_points,
    pace_hr_trends,
)
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

    def test_points_carry_the_resting_baseline_and_excess_beats(self):
        points = pace_hr_points(
            [
                activity(
                    id="a",
                    date=D,
                    duration_s=3600,
                    distance_m=10000,
                    avg_hr=150,
                )
            ],
            D,
            D,
            resting_hr_baseline=lambda _day: 50,
        )

        self.assertEqual(50, points[0].resting_hr)
        self.assertEqual(10000, points[0].distance_m)
        self.assertEqual(6000, points[0].excess_beats)

    def test_points_carry_the_classified_category_and_steady_flag(self):
        activities = [
            activity(
                id="a",
                date=D,
                duration_s=3600,
                distance_m=10000,
                avg_hr=150,
                name="Easy",
                workout_methods=["continuous"],
                workout_targets=["base"],
            ),
            activity(
                id="b",
                date=D,
                duration_s=3600,
                distance_m=10000,
                avg_hr=165,
                name="Intervals",
                workout_methods=["intervals"],
                workout_targets=["threshold"],
            ),
        ]

        points = pace_hr_points(activities, D, D)

        self.assertEqual(["easy", "intervals"], [p.category for p in points])
        self.assertEqual([True, False], [p.steady for p in points])

    def test_points_without_a_baseline_are_still_scattered(self):
        points = pace_hr_points(
            [activity(id="a", date=D, distance_m=10000, avg_hr=150)],
            D,
            D,
        )

        self.assertIsNone(points[0].resting_hr)
        self.assertEqual(0, points[0].excess_beats)

    def test_speed_is_reciprocal_pace(self):
        points = pace_hr_points(
            [activity(id="a", date=D, distance_m=10000, avg_hr=140)],
            D,
            D,
        )

        self.assertAlmostEqual(1000 / 360, points[0].speed_m_s)


if __name__ == "__main__":
    unittest.main()


class PaceHrEfficiencyLineTests(unittest.TestCase):

    def _points(self, efficiency=2.0, resting_hr=50, count=8):
        points = []

        for index in range(count):
            speed = 2.5 + 0.1 * index
            points.append(
                PaceHrPoint(
                    D + timedelta(days=index),
                    pace_s_per_km=1000 / speed,
                    avg_hr=resting_hr + speed * 60 / efficiency,
                    resting_hr=resting_hr,
                    distance_m=10000,
                    excess_beats=5000,
                    steady=True,
                )
            )

        return points

    def test_constant_efficiency_gives_the_expected_line(self):
        lines = pace_hr_efficiency_lines(self._points())

        self.assertEqual(["first half", "second half"], [l.label for l in lines])

        for line in lines:
            self.assertAlmostEqual(50.0, line.intercept)
            self.assertAlmostEqual(30.0, line.slope)
            self.assertAlmostEqual(2.0, line.efficiency)

        self.assertAlmostEqual(2.5, lines[0].speed_low)
        self.assertAlmostEqual(2.8, lines[0].speed_high)
        self.assertAlmostEqual(125.0, lines[0].at(2.5))

    def test_points_without_a_baseline_have_no_line(self):
        points = self._points(count=8)

        points = [
            replace(point, resting_hr=None, excess_beats=0)
            for point in points
        ]

        self.assertEqual([], pace_hr_efficiency_lines(points))

    def test_needs_at_least_two_usable_points_per_half(self):
        points = [
            replace(point, excess_beats=0) if index < 2 else point
            for index, point in enumerate(self._points(count=4))
        ]

        lines = pace_hr_efficiency_lines(points)

        self.assertEqual(1, len(lines))
        self.assertEqual("second half", lines[0].label)

    def test_too_few_points_have_no_lines(self):
        self.assertEqual([], pace_hr_efficiency_lines(self._points(count=3)))
