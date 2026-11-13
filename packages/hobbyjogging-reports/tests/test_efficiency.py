import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import Activity, Interval, WellnessDay
from hobbyjogging_report.analysis import (
    EFFICIENCY_UNIT,
    activity_efficiency,
    aggregate_efficiency,
    excess_beats,
    interval_efficiency,
    m_per_excess_beat,
    resting_hr_baseline,
    resting_hr_baselines,
    is_steady_run,
    steady_efficiency,
)
from hobbyjogging_report.analysis.subt import (
    subt_blocks,
    subt_report_summary,
    subt_work_points,
)
from hobbyjogging_report.format import (
    format_session_activity,
    format_subt_summary_table,
)
from hobbyjogging_report.model import SubtSummary
from hobbyjogging_report.subt_ewma_report import subt_ewma_markdown

D = date(2026, 1, 1)


class EfficiencyHelperTests(unittest.TestCase):

    def test_known_value(self):
        # 10 km in one hour at 150 bpm with a 50 bpm baseline: 100 * 60
        # excess beats, so 10 000 / 6 000.
        self.assertAlmostEqual(
            1.6667,
            m_per_excess_beat(10000, 3600, 150, 50),
            places=4,
        )
        self.assertEqual(6000, excess_beats(3600, 150, 50))

    def test_missing_pieces_give_none(self):
        self.assertIsNone(m_per_excess_beat(None, 3600, 150, 50))
        self.assertIsNone(m_per_excess_beat(10000, None, 150, 50))
        self.assertIsNone(m_per_excess_beat(10000, 3600, None, 50))
        self.assertIsNone(m_per_excess_beat(10000, 3600, 150, None))
        self.assertIsNone(m_per_excess_beat(0, 3600, 150, 50))
        self.assertIsNone(excess_beats(0, 150, 50))

    def test_excess_heart_rate_guard(self):
        # Less than 10 bpm above rest is too close to be meaningful.
        self.assertIsNone(excess_beats(3600, 59, 50))
        self.assertIsNone(m_per_excess_beat(10000, 3600, 59, 50))
        self.assertIsNotNone(excess_beats(3600, 60, 50))

    def test_aggregate_is_weighted_not_the_mean_of_ratios(self):
        samples = [
            (10000, 3600, 150, 50),  # 1.667 m/beat, 6000 excess beats
            (1000, 3600, 100, 50),  # 0.333 m/beat, 3000 excess beats
        ]

        weighted = aggregate_efficiency(samples)
        naive = (10000 / 6000 + 1000 / 3000) / 2

        self.assertAlmostEqual(11000 / 9000, weighted)
        self.assertNotAlmostEqual(naive, weighted)

    def test_metric_is_flat_across_speeds_with_a_linear_hr_model(self):
        # HR = 52.5 + 26.2 * v; subtracting the intercept removes the
        # pace bias, so m/excess beat stays constant across speed bands.
        resting_hr = 52.5
        values = []

        for speed in (2.5, 3.0, 3.5, 4.0):
            duration = 1800
            distance = speed * duration
            avg_hr = 52.5 + 26.2 * speed
            values.append(
                m_per_excess_beat(
                    distance,
                    duration,
                    avg_hr,
                    resting_hr,
                )
            )

        for value in values:
            self.assertAlmostEqual(values[0], value, places=6)

    def test_steady_run_requires_aerobic_band_and_non_quality(self):
        steady = Activity(
            id="a",
            date=D,
            type="run",
            duration_s=60 * 60,
            workout_methods=["continuous"],
            workout_targets=["base"],
        )
        short = Activity(
            id="b",
            date=D,
            type="run",
            duration_s=30 * 60,
            workout_methods=["continuous"],
            workout_targets=["base"],
        )
        quality = Activity(
            id="c",
            date=D,
            type="run",
            duration_s=60 * 60,
            workout_methods=["intervals"],
            workout_targets=["threshold"],
        )

        self.assertTrue(is_steady_run(steady))
        self.assertFalse(is_steady_run(short))
        self.assertFalse(is_steady_run(quality))

    def test_steady_efficiency_ignores_quality_sessions(self):
        steady = Activity(
            id="a",
            date=D,
            type="run",
            duration_s=60 * 60,
            distance_m=10000,
            avg_hr=150,
            workout_methods=["continuous"],
            workout_targets=["base"],
        )
        quality = Activity(
            id="b",
            date=D,
            type="run",
            duration_s=60 * 60,
            distance_m=10000,
            avg_hr=170,
            workout_methods=["intervals"],
            workout_targets=["threshold"],
        )

        value = steady_efficiency([steady, quality], lambda _day: 50)

        self.assertAlmostEqual(10000 / 6000, value)

    def test_interval_structure_can_keep_a_run_out_of_the_steady_band(self):
        session = Activity(
            id="a",
            date=D,
            type="run",
            duration_s=60 * 60,
            rpe=3,
        )
        work = [Interval(type="WORK", duration_s=20 * 60)]

        # Without the interval structure an RPE-3 session with no quality
        # signal reads as steady; the sustained work block makes it quality.
        self.assertTrue(is_steady_run(session))
        self.assertFalse(is_steady_run(session, intervals=work))

    def test_aggregate_duration_band_filter(self):
        value = aggregate_efficiency(
            [(10000, 3600, 150, 50), (10000, 1800, 150, 50)],
            duration_band=(45 * 60, 75 * 60),
        )

        self.assertAlmostEqual(10000 / 6000, value)

    def test_non_running_activity_has_no_efficiency(self):
        ride = Activity(
            id="b",
            date=D,
            type="ride",
            distance_m=30000,
            duration_s=3600,
            avg_hr=140,
        )

        self.assertIsNone(activity_efficiency(ride, 50))

    def test_interval_efficiency(self):
        interval = Interval(
            type="WORK",
            duration_s=600,
            distance_m=3000,
            avg_hr=150,
        )

        self.assertAlmostEqual(
            3000 / 1000,
            interval_efficiency(interval, 50),
        )


class RestingHrBaselineTests(unittest.TestCase):

    def _days(self, start, count, value):
        return [
            WellnessDay(date=start + timedelta(days=index), resting_hr=value)
            for index in range(count)
        ]

    def test_no_wellness_gives_none(self):
        self.assertIsNone(resting_hr_baseline([], D))

    def test_rolling_year_median(self):
        wellness = self._days(D - timedelta(days=30), 31, 50)

        self.assertEqual(50, resting_hr_baseline(wellness, D))

    def test_expands_over_old_values_when_the_window_is_empty(self):
        old = WellnessDay(date=D - timedelta(days=400), resting_hr=48)
        older = WellnessDay(date=D - timedelta(days=500), resting_hr=52)

        self.assertEqual(
            50,
            resting_hr_baseline([old, older], D),
        )

    def test_ignores_values_after_the_day(self):
        wellness = [
            WellnessDay(date=D - timedelta(days=5), resting_hr=50),
            WellnessDay(date=D + timedelta(days=1), resting_hr=70),
        ]

        self.assertEqual(50, resting_hr_baseline(wellness, D))

    def test_a_short_excursion_does_not_move_the_baseline(self):
        wellness = self._days(D - timedelta(days=364), 365, 51)
        wellness += self._days(D - timedelta(days=4), 5, 59)

        baseline = resting_hr_baseline(wellness, D)

        self.assertLessEqual(abs(baseline - 51), 2)

    def test_lookup_is_reusable_across_days(self):
        wellness = self._days(D - timedelta(days=10), 11, 50)
        lookup = resting_hr_baselines(wellness)

        self.assertEqual(50, lookup(D))
        self.assertIsNone(lookup(D - timedelta(days=11)))


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

        points = subt_work_points(activity, intervals, resting_hr=50)
        blocks = subt_blocks(activity, intervals, resting_hr=50)

        # 5 km over 5 * (160 - 50) * 5 excess beats.
        self.assertAlmostEqual(5000 / 2750, points[0].efficiency)
        self.assertEqual(5000, points[0].distance_m)
        self.assertEqual(2750, points[0].beats)
        self.assertAlmostEqual(5000 / 2750, blocks[0].efficiency)

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

        points = subt_work_points(activity, intervals, resting_hr=50)

        self.assertAlmostEqual(1000 / 550, points[0].efficiency)
        self.assertEqual(1000, points[0].distance_m)

    def test_summary_is_weighted_from_block_sums(self):
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

        blocks = subt_blocks(activity, intervals, resting_hr=50)
        summaries, total = subt_report_summary(blocks)

        self.assertAlmostEqual(5000 / 2750, total.efficiency)
        self.assertAlmostEqual(
            5000 / 2750,
            summaries[1].efficiency,
        )

    def test_without_a_baseline_points_have_no_efficiency(self):
        activity = Activity(id="a", date=D, type="run", duration_s=300)
        intervals = [
            Interval(
                type="WORK",
                group_id="g",
                duration_s=300,
                distance_m=1000,
                avg_hr=160,
            )
        ]

        points = subt_work_points(activity, intervals)

        self.assertIsNone(points[0].efficiency)
        self.assertEqual(0, points[0].beats)

    def test_ewma_report_has_an_efficiency_table(self):
        markdown = subt_ewma_markdown([], D)

        self.assertIn("## Efficiency", markdown)
        self.assertIn("| Short | - | - | - |", markdown)


class EfficiencyRendererTests(unittest.TestCase):

    def _run(self):
        return Activity(
            id="a",
            date=D,
            type="run",
            name="Easy",
            distance_m=10000,
            duration_s=3600,
            avg_hr=150,
        )

    def test_session_line_uses_the_excess_beat_unit(self):
        lines = format_session_activity(
            self._run(),
            [],
            resting_hr=50,
        )

        self.assertIn(
            f"- Efficiency: 1.67 {EFFICIENCY_UNIT}",
            lines,
        )
        self.assertEqual("m/excess beat", EFFICIENCY_UNIT)

    def test_session_line_is_absent_without_a_baseline(self):
        lines = format_session_activity(self._run(), [])

        self.assertNotIn(
            "- Efficiency:",
            "\n".join(lines),
        )

    def test_table_cell_is_a_dash_without_efficiency(self):
        summary = SubtSummary(category="short")
        lines = format_subt_summary_table([summary], summary, 7)

        self.assertTrue(lines[2].endswith("| - |"))


if __name__ == "__main__":
    unittest.main()
