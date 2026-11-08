import unittest
from datetime import date

from hobbyjogging_report.analysis import compare_periods
from hobbyjogging_report.compare import compare_report
from support import FakeSource, activity_factory

D = date(2026, 10, 1)
activity = activity_factory()


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
            "Avg pace | Avg HR |",
            report,
        )
        self.assertIn(
            "| 2025 | 1 | 0 | 1h00 | - | 10.0 | 6:00/km | 140 |",
            report,
        )
        self.assertIn(
            "| 2026 | 0 | 1 | - | 30min | - | - | - |",
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
        self.assertIn("| 2025-12 | 0 | 0 | - | - | - | - | - |", report)
        self.assertIn(
            "| 2026-01 | 1 | 0 | 1h00 | - | 10.0 | 6:00/km | - |",
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
            "| 2026 | 1 | 0 | 1h00 | - | 10.0 | 6:00/km | - |",
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


if __name__ == "__main__":
    unittest.main()
