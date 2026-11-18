import unittest
from datetime import date

from hobbyjogging_core.model import ActivityWeather

from hobbyjogging_report.health_report import health_report
from support import FakeSource, activity_factory

D = date(2026, 10, 1)
activity = activity_factory()


class HealthReportTests(unittest.TestCase):

    def test_counts_missing_data_and_coverage(self):
        source = FakeSource(
            [
                activity(
                    id="full",
                    date=D,
                    type="run",
                    distance_m=10000,
                    avg_hr=140,
                    training_load=50,
                    pace_zone_times=[600, 600, 300, 300],
                ),
                activity(id="empty", date=D, type="run"),
            ],
            weather={"full": ActivityWeather(temp_c=12.0)},
        )

        report = health_report(source, today=D)

        self.assertIn("# Data Health", report)
        self.assertIn(f"{D} → {D}", report)
        self.assertIn("- Activities in range: 2", report)
        self.assertIn("- Missing load: 1", report)
        self.assertIn(
            "| Runs without pace zones | 1 |",
            report,
        )
        self.assertIn(
            "| Runs without average HR | 1 |",
            report,
        )
        self.assertIn(
            "| Runs without distance | 1 |",
            report,
        )
        self.assertIn("The review queue is empty.", report)
        self.assertIn(
            f"| {D.year} | 2 | 1 (50%) |",
            report,
        )

    def test_hidden_review_activity_is_listed(self):
        source = FakeSource(
            [
                activity(
                    id="bad",
                    date=D,
                    type="run",
                    distance_m=5000,
                    avg_hr=150,
                    training_load=40,
                    pace_zone_times=[600, 600, 300, 300],
                    needs_review=True,
                )
            ]
        )

        report = health_report(source, today=D)

        self.assertIn("- Hidden by review: 1", report)
        self.assertIn("## Activities with open review items", report)
        self.assertIn("| hidden |", report)


if __name__ == "__main__":
    unittest.main()
