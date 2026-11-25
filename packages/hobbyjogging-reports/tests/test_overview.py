import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import Event, EventZoneTime, WellnessDay
from hobbyjogging_report.analysis import average_warmup_days
from hobbyjogging_report.overview import overview_ewma, overview_report
from support import FakeSource, activity_factory

TODAY = date(2026, 11, 10)
activity = activity_factory()


def _source():
    return FakeSource(
        activities=[
            activity(
                id="run",
                date=TODAY,
                duration_s=3600,
                distance_m=10000,
                avg_hr=150,
                training_load=50,
                workout_methods=["continuous"],
                workout_targets=["base"],
                pace_zone_times=[600, 600, 600, 600],
            ),
            activity(
                id="ride",
                date=TODAY - timedelta(days=1),
                type="ride",
                duration_s=1800,
                training_load=20,
            ),
        ],
        wellness=[
            WellnessDay(date=TODAY, resting_hr=50),
        ],
        events=[
            Event(
                date=TODAY + timedelta(days=1),
                name="Plan run",
                type="run",
                duration_s=3600,
                distance_m=10000,
                training_load=40,
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 1200, 1),
                    EventZoneTime("Z3", 600, 3),
                ],
            ),
            Event(
                date=TODAY + timedelta(days=2),
                name="Plan ride",
                type="ride",
                duration_s=1800,
                training_load=20,
            ),
        ],
    )


def _source_without_today_run():
    return FakeSource(
        activities=[
            activity(
                id="run",
                date=TODAY - timedelta(days=1),
                duration_s=3600,
                distance_m=10000,
                avg_hr=150,
                training_load=50,
                workout_methods=["continuous"],
                workout_targets=["base"],
                pace_zone_times=[600, 600, 600, 600],
            ),
        ],
    )


def _row(report: str, label: str) -> list[str]:
    line = next(
        row
        for row in report.splitlines()
        if row.startswith(f"| {label} |")
    )
    return [cell.strip() for cell in line.strip("|").split("|")]


class OverviewReportTests(unittest.TestCase):

    def test_renders_ewma_table_and_planned_column(self):
        report = overview_report(
            _source(),
            today=TODAY,
            future_days=14,
        )

        self.assertIn("# Training Overview — EWMA", report)
        self.assertIn(f"EWMA ending {TODAY}", report)
        self.assertIn(
            "| Metric | 7-day EWMA | 42-day EWMA | 182-day EWMA | "
            "Next 14 days (avg/week) |",
            report,
        )

        self.assertEqual("0.5", _row(report, "Runs / week")[-1])
        self.assertEqual("0.5", _row(report, "Cross / week")[-1])
        self.assertEqual("30min", _row(report, "Run time / week")[-1])
        self.assertEqual("5.0", _row(report, "Run km / week")[-1])
        self.assertEqual("20", _row(report, "Run load / week")[-1])
        self.assertIn("Load counts running only", report)
        self.assertEqual("5min", _row(report, "Z3+4 / week")[-1])
        self.assertEqual(
            [
                "Efficiency (40–75 min steady)",
                "1.67",
                "1.67",
                "1.67",
                "-",
            ],
            _row(report, "Efficiency (40–75 min steady)"),
        )
        self.assertNotIn("## Efficiency", report)
        self.assertIn("sum(excess beats)", report)

    def test_no_future_column_when_horizon_is_zero(self):
        report = overview_report(
            _source(),
            today=TODAY,
            future_days=0,
        )

        self.assertIn("Next period (avg/week)", report)
        self.assertEqual("-", _row(report, "Runs / week")[-1])

    def test_ewmas_end_yesterday_when_today_has_no_run(self):
        source = _source_without_today_run()
        yesterday = TODAY - timedelta(days=1)

        report = overview_report(source, today=TODAY, future_days=14)

        self.assertIn(f"EWMA ending {yesterday}", report)
        self.assertIn(
            f"No run recorded today; the EWMAs end {yesterday}.",
            report,
        )
        self.assertNotIn(f"EWMA ending {TODAY}", report)
        self.assertIn(f"EWMA ending {yesterday}; the last column", report)

        warm_start = TODAY - timedelta(days=average_warmup_days())
        rows = overview_ewma(
            source.activities(warm_start, TODAY),
            warm_start,
            yesterday,
        )

        self.assertEqual(
            f"{rows[0].values[7]:.1f}",
            _row(report, "Runs / week")[1],
        )

    def test_a_ride_today_does_not_end_the_window(self):
        source = _source_without_today_run()
        source._activities.append(
            activity(
                id="ride",
                date=TODAY,
                type="ride",
                duration_s=1800,
            )
        )
        yesterday = TODAY - timedelta(days=1)

        report = overview_report(source, today=TODAY, future_days=14)

        self.assertIn(f"EWMA ending {yesterday}", report)

    def test_review_items_are_noted_and_excluded(self):
        source = _source()
        source._activities.append(
            activity(
                id="flagged",
                date=TODAY,
                duration_s=3600,
                distance_m=10000,
                needs_review=True,
            )
        )

        report = overview_report(source, today=TODAY, future_days=14)

        self.assertIn("1 activity excluded (import review)", report)

    def test_empty_source_renders_zero_table(self):
        report = overview_report(
            FakeSource(),
            today=TODAY,
            future_days=14,
        )

        self.assertIn("Runs / week", report)
        self.assertIn("0min", report)


if __name__ == "__main__":
    unittest.main()
