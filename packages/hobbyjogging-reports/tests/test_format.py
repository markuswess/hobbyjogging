import unittest
from datetime import date

from hobbyjogging_report.classify import category_breakdown
from hobbyjogging_report.format import (
    format_activity,
    format_category_table,
    format_event,
    format_feel,
    format_weather,
    format_methods,
    format_session_activity,
    format_targets,
    last_four_nights,
    pace,
    sport_label,
    work_summary_for_activity,
)
from hobbyjogging_report.summary import recovery_summary, summarize_training
from hobbyjogging_core.model import (
    ActivityWeather,
    Event,
    EventZoneTime,
    Interval,
    WellnessDay,
)
from support import FakeSource, activity_factory

D = date(2026, 10, 1)
activity = activity_factory()


class Vo2maxLabelTests(unittest.TestCase):
    """The Garmin estimate is per sport, so non-runs say which."""

    def test_run_keeps_the_plain_garmin_label(self):
        lines = format_session_activity(
            activity(type="run", vo2max_garmin=52.3),
            [],
        )

        self.assertIn("- VO2max: 52.3 (Garmin)", lines)

    def test_ride_qualifies_the_garmin_label_as_cycling(self):
        lines = format_session_activity(
            activity(type="ride", vo2max_garmin=64.6),
            [],
        )

        self.assertIn("- VO2max: 64.6 (Garmin, cycling)", lines)

    def test_other_sport_uses_its_own_name(self):
        lines = format_session_activity(
            activity(type="swim", vo2max_garmin=55.0),
            [],
        )

        self.assertIn("- VO2max: 55.0 (Garmin, swim)", lines)


class EventReportTests(unittest.TestCase):
    """A planned event's page shows the plan, and the match when there is one."""

    def test_plain_event_page_carries_the_plan(self):
        event = Event(
            id="e1",
            date=D,
            name="5x5 subT",
            type="run",
            duration_s=3000,
            distance_m=12000,
            training_load=60,
            workout_methods=["intervals"],
            workout_targets=["threshold"],
            zone_kind="pace",
            zone_times=[EventZoneTime("Z3", 1500, 3)],
            description="Hold threshold.",
        )

        text = "\n".join(format_event(event))

        self.assertIn("## 5x5 subT", text)
        self.assertIn("- Date: 2026-10-01", text)
        self.assertIn("- Load: 60", text)
        self.assertIn("- Duration: 50min", text)
        self.assertIn("- Methods: Intervals", text)
        self.assertIn("- Targets: Threshold", text)
        self.assertIn("- Planned pace times: Z3 25:00", text)
        self.assertIn("Hold threshold.", text)
        self.assertNotIn("Plan vs actual", text)

    def test_matched_event_compares_plan_with_actual(self):
        event = Event(
            id="e1",
            date=D,
            name="Tempo",
            type="run",
            duration_s=3000,
            distance_m=12000,
            training_load=60,
        )
        matched = activity(
            id="a1",
            date=D,
            duration_s=2700,
            distance_m=11000,
            training_load=55,
        )

        text = "\n".join(
            format_event(
                event,
                matched=matched,
                matched_href="../activity/a1.html",
            )
        )

        self.assertIn("### Plan vs actual", text)
        self.assertIn("[2026-10-01 Run](../activity/a1.html)", text)
        self.assertIn("approximate", text)
        self.assertIn("| Time | 50min | 45min | -5min |", text)
        self.assertIn(
            "| Distance | 12.0 km | 11.0 km | -1.0 km |",
            text,
        )
        self.assertIn("| Load | 60 | 55 | -5 |", text)


class WeatherTests(unittest.TestCase):

    def test_session_report_carries_the_weather_line(self):
        lines = format_session_activity(
            activity(),
            [],
            weather=ActivityWeather(temp_c=12.4, wind_speed_ms=3.2),
        )

        self.assertIn("- Weather: 12 °C, wind 3 m/s", lines)

    def test_session_report_omits_an_empty_weather_line(self):
        lines = format_session_activity(activity(), [])

        self.assertNotIn("- Weather:", "\n".join(lines))

    def test_feels_like_appears_only_when_it_differs(self):
        self.assertEqual(
            "12 °C, feels 6 °C, wind 3 m/s",
            format_weather(
                ActivityWeather(
                    temp_c=12.4,
                    feels_like_c=5.8,
                    wind_speed_ms=3.2,
                )
            ),
        )
        self.assertEqual(
            "12 °C",
            format_weather(
                ActivityWeather(temp_c=12.4, feels_like_c=13.0)
            ),
        )

    def test_missing_weather_is_blank(self):
        self.assertEqual("", format_weather(None))
        self.assertEqual("", format_weather(ActivityWeather()))


class EstimatedBaselineTests(unittest.TestCase):

    def test_estimated_baseline_is_flagged(self):
        lines = format_session_activity(
            activity(distance_m=10000, duration_s=3600, avg_hr=150),
            [],
            resting_hr=50,
            resting_hr_estimated=True,
        )

        self.assertIn(
            "- Efficiency: 1.67 m/excess beat (estimated baseline)",
            lines,
        )

    def test_measured_baseline_has_no_flag(self):
        lines = format_session_activity(
            activity(distance_m=10000, duration_s=3600, avg_hr=150),
            [],
            resting_hr=50,
        )

        self.assertIn("- Efficiency: 1.67 m/excess beat", lines)
        self.assertNotIn("estimated", "\n".join(lines))


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
            [
                "5x5:00 subT-medium: 5:00/km, 160 avg / 172 max bpm, "
                "1.82 m/excess beat"
            ],
            work_summary_for_activity(a, intervals, resting_hr=50),
        )

    def test_subt_summary_name_only(self):
        a = activity(name="LT1", description="instead of subT")
        self.assertIsNone(work_summary_for_activity(a, []))

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
            [
                "3x10:00 LT1: 3:20/km, 155 avg / 168 max bpm, "
                "2.86 m/excess beat"
            ],
            work_summary_for_activity(a, intervals, resting_hr=50),
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
            resting_hr=50,
        )

        self.assertIn("- Category: quality/intervals/lt1", lines)
        self.assertIn("\n### LT1 report", lines)
        self.assertIn(
            "- 3x10:00 LT1: 3:20/km, 155 avg / 168 max bpm, "
            "2.86 m/excess beat",
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

    def test_format_methods_and_targets(self):
        a = activity(
            workout_methods=["intervals", "continuous"],
            workout_targets=["lt1", "base"],
        )

        self.assertEqual("Continuous, Intervals", format_methods(a))
        self.assertEqual("Base, LT1", format_targets(a))

    def test_format_methods_and_targets_default_to_dash(self):
        a = activity()

        self.assertEqual("-", format_methods(a))
        self.assertEqual("-", format_targets(a))

    def test_format_activity_description_is_code_block(self):
        a = activity(
            description="# Warm up\n- 10 min easy\n\n## Main\n3 x 10 min",
        )

        lines = format_activity(FakeSource(), a, "Run Easy")

        self.assertIn("```", lines)
        self.assertIn("# Warm up", lines)
        self.assertIn("- 10 min easy", lines)
        self.assertNotIn("- Description:", lines)
        self.assertNotIn("- Description: # Warm up", lines)

    def test_format_category_table(self):
        stats = category_breakdown([
            activity(id="a", rpe=5, duration_s=3000, training_load=50),
            activity(
                id="b", type="ride", duration_s=3600, training_load=40,
            ),
        ])

        lines = format_category_table(stats)

        self.assertEqual(
            "| Category | Sessions | Time | Load | "
            "Steady efficiency (40–75 min) | Time % | Load % |",
            lines[0],
        )
        self.assertIn(
            "| quality/intervals/other | 1 | 50min | 50 | - | 45% | 56% |",
            lines,
        )
        self.assertIn(
            "| cross-training | 1 | 1h00 | 40 | - | 55% | 44% |",
            lines,
        )
        self.assertIn(
            "| **Total** | 2 | 1h50 | 90 | - | 100% | 100% |",
            lines,
        )


if __name__ == "__main__":
    unittest.main()
