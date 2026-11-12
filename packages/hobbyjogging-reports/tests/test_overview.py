import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import Event, EventZoneTime, WellnessDay
from hobbyjogging_report.overview import overview_report
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
        self.assertEqual("30", _row(report, "Load / week")[-1])
        self.assertEqual("5min", _row(report, "Z3+4 / week")[-1])
        self.assertIn("## Efficiency", report)
        self.assertEqual("1.67", _row(report, "7-day")[-1])
        self.assertIn("sum(excess beats)", report)

    def test_no_future_column_when_horizon_is_zero(self):
        report = overview_report(
            _source(),
            today=TODAY,
            future_days=0,
        )

        self.assertIn("Next period (avg/week)", report)
        self.assertEqual("-", _row(report, "Runs / week")[-1])

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
