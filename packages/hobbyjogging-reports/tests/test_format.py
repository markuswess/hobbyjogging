import unittest
from datetime import date

from intervals_report.classify import category_breakdown
from intervals_report.format import (
    format_activity,
    format_category_table,
    format_feel,
    last_four_nights,
    latest_recovery,
    pace,
    recovery_summary,
    sport_label,
    subt_summary_for_activity,
    summarize_training,
    work_summary_for_activity,
)
from intervals_report.model import Activity, Interval, WellnessDay

D = date(2026, 10, 1)


class FakeSource:

    def activity_intervals(self, activity_id):
        return []


def activity(**overrides):
    values = dict(id="a", date=D, type="run", name="", duration_s=3600)
    values.update(overrides)
    return Activity(**values)


class SummarizeTrainingTests(unittest.TestCase):

    def test_run_and_cross_totals(self):
        activities = [
            activity(
                id="run", type="run", duration_s=3600, distance_m=12000,
                training_load=60, rpe=5,
                pace_zone_times=[600, 600, 600, 600, 0],
            ),
            activity(
                id="trail", type="trail_run", duration_s=1800, distance_m=5000,
                training_load=30, rpe=3,
                hr_zone_times=[300, 300, 600, 600, 0],
            ),
            activity(
                id="ride", type="ride", duration_s=2400, training_load=40,
            ),
        ]

        result = summarize_training(activities)

        self.assertEqual(5400, result["run_time"])
        self.assertEqual(17000, result["run_distance"])
        self.assertEqual(90, result["run_load"])
        self.assertEqual(8, result["rpe"])
        self.assertEqual(2400, result["z3_z4_time"])
        self.assertEqual(2400, result["cross_time"])
        self.assertEqual(40, result["cross_load"])
        # RPE 3 can be quality when the zone distribution is hard.
        self.assertEqual(["run", "trail"], [a.id for a in result["quality"]])

    def test_race_support_is_not_in_quality_list(self):
        result = summarize_training([
            activity(
                id="warmup", name="Race warm up",
                rpe=2, duration_s=1200,
            ),
        ])

        self.assertEqual([], result["quality"])

    def test_feel_totals_separate_runs_and_cross_training(self):
        result = summarize_training([
            activity(id="run", type="run", feel=2),
            activity(id="trail", type="trail_run", feel=4),
            activity(id="ride", type="ride", feel=1),
            activity(id="unrated", type="run", feel=None),
        ])

        self.assertEqual(6, result["run_feel"])
        self.assertEqual(2, result["run_feel_count"])
        self.assertEqual(1, result["cross_feel"])
        self.assertEqual(1, result["cross_feel_count"])


class FormattingTests(unittest.TestCase):

    def test_sport_label(self):
        self.assertEqual("Run", sport_label(activity(type="run")))
        self.assertEqual("TrailRun", sport_label(activity(type="trail_run")))
        self.assertEqual("Ride", sport_label(activity(type="ride")))

    def test_pace(self):
        self.assertEqual(
            "5:00/km",
            pace(activity(duration_s=300, distance_m=1000)),
        )
        self.assertEqual("-", pace(activity(distance_m=0)))

    def test_format_feel(self):
        self.assertEqual("4 (Poor)", format_feel(4))
        self.assertEqual("9", format_feel(9))
        self.assertEqual("-", format_feel(None))

    def test_recovery(self):
        wellness = [
            WellnessDay(
                date=date(2026, 9, 30),
                hrv=50, resting_hr=45, sleep_s=7 * 3600,
            ),
            WellnessDay(
                date=date(2026, 10, 1),
                hrv=60, resting_hr=47, sleep_s=8 * 3600,
            ),
        ]

        summary = recovery_summary(wellness)

        self.assertEqual(55, summary["hrv"])
        self.assertEqual(46, summary["rhr"])
        self.assertEqual(7.5 * 3600, summary["sleep"])
        self.assertEqual(60, latest_recovery(wellness)["hrv"])
        self.assertEqual(2, len(last_four_nights(wellness)))

    def test_subt_summary_uses_model_intervals(self):
        a = activity(name="5x5' subT", duration_s=3000)
        intervals = [
            Interval(
                type="WORK", group_id="g",
                duration_s=300, distance_m=1000,
                avg_hr=160, max_hr=172,
            )
            for _ in range(5)
        ]

        self.assertEqual(
            ["5x5:00 subT-medium: 5:00/km, 160 avg / 172 max bpm"],
            subt_summary_for_activity(a, intervals),
        )

    def test_subt_summary_name_only(self):
        a = activity(name="LT1", description="instead of subT")
        self.assertIsNone(subt_summary_for_activity(a, []))

    def test_work_summary_for_lt1(self):
        a = activity(name="3x10' LT1", duration_s=3000)
        intervals = [
            Interval(
                type="WORK", group_id="g",
                duration_s=600, distance_m=3000,
                avg_hr=155, max_hr=168,
            )
            for _ in range(3)
        ]

        self.assertEqual(
            ["3x10:00 LT1: 3:20/km, 155 avg / 168 max bpm"],
            work_summary_for_activity(a, intervals),
        )

    def test_format_activity_lt1_heading(self):
        a = activity(name="3x10' LT1", duration_s=3000)
        intervals = [
            Interval(
                type="WORK", group_id="g",
                duration_s=600, distance_m=3000,
                avg_hr=155, max_hr=168,
            )
            for _ in range(3)
        ]

        lines = format_activity(
            None,
            a,
            "Run — 3x10' LT1",
            category="quality/intervals/lt1",
            intervals=intervals,
        )

        self.assertIn("- Category: quality/intervals/lt1", lines)
        self.assertIn("\n### LT1 report", lines)
        self.assertIn(
            "- 3x10:00 LT1: 3:20/km, 155 avg / 168 max bpm",
            lines,
        )

    def test_format_activity(self):
        a = activity(
            type="run", name="Easy", duration_s=3000, distance_m=10000,
            avg_hr=140, training_load=40, rpe=1, feel=2,
            pace_zone_times=[0, 0, 1800, 0, 0],
        )

        lines = format_activity(FakeSource(), a, "Run Easy")

        self.assertEqual("\n### Run Easy", lines[0])
        self.assertIn("- Duration: 50min", lines)
        self.assertIn("- Distance: 10.0 km", lines)
        self.assertIn("- Pace: 5:00/km", lines)
        self.assertIn("- HR: 140 avg", lines)
        self.assertIn("- Load: 40", lines)
        self.assertIn("- RPE: 1", lines)
        self.assertIn("- Feel: 2 (Good)", lines)
        self.assertIn("- Pace zones: Z3 30min", lines)

    def test_format_category_table(self):
        stats = category_breakdown([
            activity(id="a", rpe=5, duration_s=3000, training_load=50),
            activity(
                id="b", type="ride", duration_s=3600, training_load=40,
            ),
        ])

        lines = format_category_table(stats)

        self.assertEqual(
            "| Category | Sessions | Time | Load | Time % | Load % |",
            lines[0],
        )
        self.assertIn(
            "| quality/intervals/other | 1 | 50min | 50 | 45% | 56% |",
            lines,
        )
        self.assertIn(
            "| cross-training | 1 | 1h00 | 40 | 55% | 44% |",
            lines,
        )
        self.assertIn(
            "| **Total** | 2 | 1h50 | 90 | 100% | 100% |",
            lines,
        )


if __name__ == "__main__":
    unittest.main()
