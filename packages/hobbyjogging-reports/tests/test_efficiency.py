import unittest
from datetime import date

from hobbyjogging_core.model import Activity, Interval
from hobbyjogging_report.analysis import (
    activity_efficiency,
    aggregate_efficiency,
    beats,
    interval_efficiency,
    m_per_beat,
)
from hobbyjogging_report.analysis.subt import subt_work_points, subt_report_summary
from hobbyjogging_report.subt_ewma_report import subt_ewma_markdown

D = date(2026, 1, 1)


class EfficiencyHelperTests(unittest.TestCase):

    def test_known_value(self):
        # 10 km in one hour at 150 bpm -> 150 * 60 beats.
        self.assertAlmostEqual(1.1111, m_per_beat(10000, 3600, 150), places=4)
        self.assertEqual(9000, beats(3600, 150))

    def test_missing_pieces_give_none(self):
        self.assertIsNone(m_per_beat(None, 3600, 150))
        self.assertIsNone(m_per_beat(10000, None, 150))
        self.assertIsNone(m_per_beat(10000, 3600, None))
        self.assertIsNone(m_per_beat(0, 3600, 150))
        self.assertIsNone(beats(0, 150))
        self.assertIsNone(beats(3600, 0))

    def test_aggregate_is_weighted_not_the_mean_of_ratios(self):
        samples = [
            (10000, 3600, 150),  # 1.111 m/beat, 9000 beats
            (1000, 3600, 100),  # 0.167 m/beat, 6000 beats
        ]

        weighted = aggregate_efficiency(samples)
        naive = (10000 / 9000 + 1000 / 6000) / 2

        self.assertAlmostEqual(11000 / 15000, weighted)
        self.assertNotAlmostEqual(naive, weighted)

    def test_non_running_activity_has_no_efficiency(self):
        ride = Activity(
            id="b",
            date=D,
            type="ride",
            distance_m=30000,
            duration_s=3600,
            avg_hr=140,
        )

        self.assertIsNone(activity_efficiency(ride))

    def test_interval_efficiency(self):
        interval = Interval(
            type="WORK",
            duration_s=600,
            distance_m=3000,
            avg_hr=150,
        )

        self.assertAlmostEqual(3000 / 1500, interval_efficiency(interval))


class SubtEfficiencyTests(unittest.TestCase):

    def test_points_and_blocks_carry_efficiency(self):
        activity = Activity(
            id="a",
            date=D,
            type="run",
            name="5x5 subT",
            duration_s=3000,
        )
        intervals = [
            Interval(
                type="WORK",
                group_id="g",
                duration_s=300,
                distance_m=1000,
                avg_hr=160,
            )
            for _ in range(5)
        ]

        points = subt_work_points(activity, intervals)

        self.assertAlmostEqual(1.25, points[0].efficiency)
        self.assertEqual(5000, points[0].distance_m)
        self.assertEqual(4000, points[0].beats)

    def test_partial_hr_coverage_stays_weighted(self):
        activity = Activity(id="a", date=D, type="run", duration_s=600)
        intervals = [
            Interval(
                type="WORK",
                group_id="g",
                duration_s=300,
                distance_m=1000,
                avg_hr=160,
            ),
            Interval(
                type="WORK",
                group_id="g",
                duration_s=300,
                distance_m=1000,
                avg_hr=None,
            ),
        ]

        points = subt_work_points(activity, intervals)

        # Only the first rep has a heart rate: 1000 m / (160 * 5) beats.
        self.assertAlmostEqual(1000 / 800, points[0].efficiency)
        self.assertEqual(1000, points[0].distance_m)

    def test_ewma_report_has_an_efficiency_table(self):
        markdown = subt_ewma_markdown([], D)

        self.assertIn("## Efficiency", markdown)
        self.assertIn("| Short | - | - | - |", markdown)


if __name__ == "__main__":
    unittest.main()
