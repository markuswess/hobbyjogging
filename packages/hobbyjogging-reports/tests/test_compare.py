import math
import unittest
from datetime import date, timedelta

from hobbyjogging_report.analysis import (
    compare_periods,
    compare_year_ewma,
    compare_year_planned_ewma,
)
from hobbyjogging_report.analysis.compare import EFFICIENCY_MIN_RUNS
from hobbyjogging_report.compare import compare_report
from support import FakeSource, activity_factory
from hobbyjogging_core.model import Event, WellnessDay

D = date(2026, 10, 1)
activity = activity_factory()


class ComparePlannedEwmaTests(unittest.TestCase):

    def _run(self, day, distance_m=10000, ident=None):
        return activity(
            id=ident or f"run-{day}",
            date=day,
            duration_s=3600,
            distance_m=distance_m,
            avg_hr=150,
        )

    def test_projection_uses_actuals_until_today_then_the_plan(self):
        today = date(2026, 1, 3)
        activities = [
            self._run(date(2026, 1, 1)),
            self._run(date(2026, 1, 2)),
        ]
        events = [
            Event(
                date=today,
                type="run",
                distance_m=20000,
            ),
            Event(
                date=date(2026, 1, 4),
                type="run",
                distance_m=20000,
            ),
        ]

        projection = dict(
            compare_year_planned_ewma(
                activities,
                events,
                "volume",
                42,
                today=today,
            )[0][1]
        )
        actual = dict(
            compare_year_ewma(
                activities,
                "volume",
                42,
                today=today,
            )[0][1]
        )

        # The history before today is unchanged.
        self.assertEqual(actual[date(2026, 1, 1)], projection[date(2026, 1, 1)])
        self.assertEqual(actual[date(2026, 1, 2)], projection[date(2026, 1, 2)])
        # Today had no workout, so the planned 20 km is used.
        self.assertGreater(
            projection[date(2026, 1, 3)],
            actual[date(2026, 1, 3)],
        )

    def test_an_actual_workout_today_wins_over_the_plan(self):
        today = date(2026, 1, 3)
        activities = [
            self._run(date(2026, 1, 1)),
            self._run(date(2026, 1, 2)),
            self._run(today, distance_m=10000),
        ]
        events = [
            Event(
                date=today,
                type="run",
                distance_m=50000,
            ),
            Event(
                date=date(2026, 1, 4),
                type="run",
                distance_m=20000,
            ),
        ]

        projection = dict(
            compare_year_planned_ewma(
                activities,
                events,
                "volume",
                42,
                today=today,
            )[0][1]
        )
        actual = dict(
            compare_year_ewma(
                activities,
                "volume",
                42,
                today=today,
            )[0][1]
        )

        self.assertEqual(actual[date(2026, 1, 3)], projection[date(2026, 1, 3)])

    def test_projection_continues_into_next_year(self):
        today = date(2026, 12, 31)
        activities = [self._run(date(2026, 12, 30))]
        events = [
            Event(
                date=today,
                type="run",
                distance_m=10000,
            ),
            Event(
                date=date(2027, 1, 2),
                type="run",
                distance_m=12000,
            ),
        ]

        series = compare_year_planned_ewma(
            activities,
            events,
            "volume",
            42,
            today=today,
        )

        self.assertEqual([2026, 2027], [year for year, _ in series])
        self.assertGreater(dict(series[1][1])[date(2027, 1, 2)], 0)

    def test_only_volume_and_time_have_planned_series(self):
        self.assertEqual(
            [],
            compare_year_planned_ewma(
                [],
                [Event(date=date(2026, 1, 1), type="run", distance_m=10000)],
                "efficiency",
                42,
            ),
        )
        self.assertEqual(
            [],
            compare_year_planned_ewma(
                [],
                [Event(date=date(2026, 1, 1), type="run", distance_m=10000)],
                "load",
                42,
            ),
        )


class ComparePeriodsTests(unittest.TestCase):

    def test_yearly_rows_sum_runs_and_cross_training(self):
        activities = [
            activity(
                id="a",
                date=date(2025, 6, 1),
                duration_s=3600,
                distance_m=10000,
                avg_hr=140,
            ),
            activity(
                id="b",
                date=date(2025, 6, 2),
                duration_s=1800,
                distance_m=5000,
                avg_hr=150,
            ),
            activity(
                id="c",
                date=date(2025, 7, 1),
                type="ride",
                duration_s=3600,
                avg_hr=160,
            ),
            activity(
                id="d",
                date=date(2026, 1, 1),
                type="trail_run",
                duration_s=7200,
                distance_m=20000,
                avg_hr=145,
            ),
        ]

        rows = compare_periods(
            activities,
            "years",
            date(2025, 1, 1),
            date(2026, 12, 31),
        )

        self.assertEqual(["2025", "2026"], [row.label for row in rows])

        first = rows[0]
        self.assertEqual(2, first.runs)
        self.assertEqual(1, first.cross_sessions)
        self.assertEqual(5400, first.run_time_s)
        self.assertEqual(3600, first.cross_time_s)
        self.assertEqual(15000, first.run_distance_m)
        self.assertEqual(360, first.pace_s_per_km)
        self.assertEqual(145, first.avg_hr)

        second = rows[1]
        self.assertEqual(1, second.runs)
        self.assertEqual(0, second.cross_sessions)
        self.assertEqual(7200, second.run_time_s)
        self.assertEqual(0, second.cross_time_s)
        self.assertEqual(20000, second.run_distance_m)
        self.assertEqual(360, second.pace_s_per_km)
        self.assertEqual(145, second.avg_hr)

    def test_monthly_rows_fill_empty_periods(self):
        activities = [
            activity(
                id="a",
                date=date(2026, 1, 15),
                distance_m=10000,
            )
        ]

        rows = compare_periods(
            activities,
            "months",
            date(2025, 12, 1),
            date(2026, 2, 28),
        )

        self.assertEqual(
            ["2025-12", "2026-01", "2026-02"],
            [row.label for row in rows],
        )
        self.assertEqual(0, rows[0].runs)
        self.assertEqual(1, rows[1].runs)
        self.assertEqual(0, rows[2].runs)

    def test_pace_uses_total_time_and_distance(self):
        activities = [
            activity(
                id="a",
                date=D,
                duration_s=3600,
                distance_m=10000,
            ),
            activity(
                id="b",
                date=D,
                duration_s=3600,
                distance_m=20000,
            ),
        ]

        rows = compare_periods(activities, "years", D, D)

        # 7200 s over 30 km is 4:00/km, not the 4:30 mean of 6:00 and 3:00.
        self.assertEqual(240, rows[0].pace_s_per_km)

    def test_avg_hr_uses_runs_with_hr_only(self):
        activities = [
            activity(id="a", date=D, avg_hr=140),
            activity(id="b", date=D, avg_hr=150),
            activity(id="c", date=D, avg_hr=None),
            activity(id="d", date=D, type="ride", avg_hr=170),
        ]

        rows = compare_periods(activities, "years", D, D)

        self.assertEqual(145, rows[0].avg_hr)

    def test_empty_period_is_a_zero_row(self):
        rows = compare_periods(
            [activity(date=date(2025, 1, 1))],
            "years",
            date(2027, 1, 1),
            date(2027, 12, 31),
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("2027", rows[0].label)
        self.assertEqual(0, rows[0].runs)

    def test_reversed_range_has_no_rows(self):
        self.assertEqual(
            [],
            compare_periods(
                [activity(date=D)],
                "years",
                date(2027, 12, 31),
                date(2027, 1, 1),
            ),
        )


class CompareReportTests(unittest.TestCase):

    def test_years_report_starts_at_first_activity_year(self):
        source = FakeSource(
            [
                activity(
                    id="a",
                    date=date(2025, 6, 1),
                    duration_s=3600,
                    distance_m=10000,
                    avg_hr=140,
                ),
                activity(
                    id="b",
                    date=date(2026, 1, 1),
                    type="ride",
                    duration_s=1800,
                ),
            ]
        )

        report = compare_report(
            "years",
            None,
            date(2026, 12, 31),
            source,
        )

        self.assertIn("# Training Comparison by Year", report)
        self.assertIn("2025-01-01 → 2026-12-31", report)
        self.assertIn(
            "| Period | Runs | Cross | Run time | Cross time | Run km | "
            "Avg pace | Avg HR | Garmin VO2max avg | Steady efficiency (45–75 min) |",
            report,
        )
        self.assertIn(
            "| 2025 | 1 | 0 | 1h00 | - | 10.0 | 6:00/km | 140 | - | - |",
            report,
        )
        self.assertIn(
            "| 2026 | 0 | 1 | - | 30min | - | - | - | - |",
            report,
        )

    def test_months_report_uses_calendar_months(self):
        source = FakeSource(
            [
                activity(
                    id="a",
                    date=date(2026, 1, 15),
                    duration_s=3600,
                    distance_m=10000,
                )
            ]
        )

        report = compare_report(
            "months",
            date(2025, 12, 1),
            date(2026, 2, 28),
            source,
        )

        self.assertIn("# Training Comparison by Month", report)
        self.assertIn("| 2025-12 | 0 | 0 | - | - | - | - | - | - |", report)
        self.assertIn(
            "| 2026-01 | 1 | 0 | 1h00 | - | 10.0 | 6:00/km | - | - | - |",
            report,
        )

    def test_review_items_are_excluded_and_noted(self):
        source = FakeSource(
            [
                activity(id="a", date=D, distance_m=10000),
                activity(
                    id="b",
                    date=D,
                    distance_m=5000,
                    needs_review=True,
                ),
            ]
        )

        report = compare_report("years", D, D, source)

        self.assertIn("1 activity excluded (import review)", report)
        self.assertIn(
            "| 2026 | 1 | 0 | 1h00 | - | 10.0 | 6:00/km | - | - | - |",
            report,
        )

    def test_report_adds_weighted_efficiency(self):
        source = FakeSource(
            [
                activity(
                    id="a",
                    date=date(2025, 6, 1),
                    duration_s=3600,
                    distance_m=10000,
                    avg_hr=140,
                )
            ],
            wellness=[WellnessDay(date=date(2025, 6, 1), resting_hr=50)],
        )

        report = compare_report(
            "years",
            None,
            date(2025, 12, 31),
            source,
        )

        # 10 km / ((140 - 50) * 60) excess beats.
        self.assertIn(
            "| 2025 | 1 | 0 | 1h00 | - | 10.0 | 6:00/km | 140 | - | 1.85 |",
            report,
        )

    def test_report_averages_garmin_vo2max(self):
        source = FakeSource(
            [
                activity(
                    id="a",
                    date=date(2025, 6, 1),
                    distance_m=10000,
                    vo2max_garmin=54.2,
                ),
                activity(
                    id="b",
                    date=date(2025, 6, 3),
                    distance_m=10000,
                    vo2max_garmin=55.0,
                ),
            ]
        )

        report = compare_report(
            "years",
            date(2025, 1, 1),
            date(2025, 12, 31),
            source,
        )

        self.assertIn(
            "| 2025 | 2 | 0 | 2h00 | - | 20.0 | 6:00/km | - | 54.6 | - |",
            report,
        )

    def test_empty_range_has_no_table(self):
        report = compare_report(
            "years",
            D,
            D,
            FakeSource(),
        )

        self.assertIn("- No activities in this range", report)
        self.assertNotIn("| Period |", report)



class CompareYearEwmaTests(unittest.TestCase):

    def test_one_series_per_year_aligned_to_january(self):
        activities = [
            activity(id="a", date=date(2025, 3, 1), distance_m=10000),
            activity(id="b", date=date(2026, 3, 1), distance_m=20000),
        ]

        series = compare_year_ewma(
            activities,
            "volume",
            7,
            today=date(2026, 11, 11),
        )

        self.assertEqual([2025, 2026], [year for year, _ in series])

        for _year, points in series:
            self.assertEqual(date(_year, 1, 1), points[0][0])
            self.assertEqual(date(_year, 3, 1), points[59][0])

        # The current year stops at today, complete years run to Dec 31.
        self.assertEqual(date(2026, 11, 11), series[1][1][-1][0])
        self.assertEqual(date(2025, 12, 31), series[0][1][-1][0])

    def test_metric_values_are_daily(self):
        activities = [
            activity(id="a", date=date(2026, 1, 2), distance_m=10000),
            activity(id="b", date=date(2026, 1, 2), distance_m=5000),
        ]

        series = compare_year_ewma(
            activities,
            "volume",
            7,
            today=date(2026, 1, 3),
        )
        points = dict(series[0][1])
        alpha = 1 - math.exp(-1 / 7)

        self.assertEqual(0.0, points[date(2026, 1, 1)])
        self.assertAlmostEqual(
            15.0 * alpha,
            points[date(2026, 1, 2)],
        )

    def test_each_year_starts_where_the_previous_one_ended(self):
        activities = [
            activity(id="a", date=date(2025, 7, 1), distance_m=10000)
        ]

        series = compare_year_ewma(
            activities,
            "volume",
            42,
            today=date(2026, 6, 1),
        )
        last_2025 = series[0][1][-1][1]
        first_2026 = series[1][1][0][1]

        self.assertGreater(last_2025, 0)
        self.assertEqual(last_2025, first_2026)

    def test_efficiency_skips_rest_days_and_carries_forward(self):
        activities = [
            activity(
                id="a",
                date=date(2025, 3, 1),
                distance_m=10000,
                duration_s=3600,
                avg_hr=150,
            ),
            activity(
                id="b",
                date=date(2025, 3, 5),
                distance_m=10000,
                duration_s=3600,
                avg_hr=160,
            ),
        ]
        activities += [
            activity(
                id=f"f{index}",
                date=date(2025, 3, 6) + timedelta(days=index),
                distance_m=10000,
                duration_s=3600,
                avg_hr=150,
            )
            for index in range(20)
        ]

        series = compare_year_ewma(
            activities,
            "efficiency",
            42,
            today=date(2025, 3, 10),
            resting_hr=lambda _day: 50,
        )
        points = dict(series[0][1])

        first = 10000 / ((150 - 50) * 60)
        self.assertAlmostEqual(first, points[date(2025, 3, 1)], places=4)
        # Rest days carry the previous value instead of dropping to zero.
        self.assertAlmostEqual(first, points[date(2025, 3, 4)], places=4)
        alpha = 1 - math.exp(-1 / 42)
        expected = (
            alpha * (10000 / ((160 - 50) * 60))
            + (1 - alpha) * first
        )
        self.assertAlmostEqual(expected, points[date(2025, 3, 5)], places=4)
        self.assertLess(points[date(2025, 3, 5)], points[date(2025, 3, 4)])
        self.assertEqual(date(2025, 3, 10), series[0][1][-1][0])

    def test_efficiency_drops_years_with_too_little_hr_data(self):
        activities = [
            # 2014: only a handful of HR-backed runs.
            activity(
                id="a",
                date=date(2014, 4, 1),
                distance_m=10000,
                duration_s=3600,
                avg_hr=150,
            )
        ]
        activities += [
            activity(
                id=f"b{index}",
                date=date(2025, 1, 1) + timedelta(days=index),
                distance_m=10000,
                duration_s=3600,
                avg_hr=150,
            )
            for index in range(EFFICIENCY_MIN_RUNS)
        ]
        # A year with plenty of runs but no heart rate is dropped too.
        activities += [
            activity(
                id=f"c{index}",
                date=date(2026, 1, 1) + timedelta(days=index),
                distance_m=10000,
                duration_s=3600,
                avg_hr=None,
            )
            for index in range(EFFICIENCY_MIN_RUNS)
        ]

        series = compare_year_ewma(
            activities,
            "efficiency",
            42,
            today=date(2026, 2, 1),
            resting_hr=lambda _day: 50,
        )

        self.assertEqual([2025], [year for year, _ in series])

    def test_unknown_metric_is_rejected(self):
        with self.assertRaises(ValueError):
            compare_year_ewma([], "watts", 7)


if __name__ == "__main__":
    unittest.main()
