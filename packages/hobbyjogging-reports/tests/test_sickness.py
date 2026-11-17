import unittest
from datetime import date

from hobbyjogging_core.model import TrainingPeriod

from hobbyjogging_report.sickness_report import sickness_report
from support import FakeSource, activity_factory

activity = activity_factory()


def period(id, label, start, end):
    return TrainingPeriod(
        id=id,
        kind="illness",
        label=label,
        start_date=start,
        end_date=end,
    )


class SicknessReportTests(unittest.TestCase):

    def _source(self):
        return FakeSource(
            [
                activity(
                    id="a",
                    date=date(2026, 2, 2),
                    type="run",
                    duration_s=3600,
                    training_load=50,
                ),
                activity(
                    id="b",
                    date=date(2026, 2, 3),
                    type="ride",
                    duration_s=1800,
                    training_load=20,
                ),
                activity(
                    id="c",
                    date=date(2026, 9, 2),
                    type="run",
                    duration_s=2400,
                    training_load=30,
                ),
                activity(
                    id="d",
                    date=date(2026, 6, 1),
                    type="run",
                    duration_s=3000,
                    training_load=40,
                ),
            ],
            periods=[
                period("flu", "Flu", date(2026, 2, 1), date(2026, 2, 5)),
                period("cold", "Cold", date(2026, 9, 1), date(2026, 9, 3)),
                period(
                    "old",
                    "Old",
                    date(2025, 12, 1),
                    date(2025, 12, 5),
                ),
                period(
                    "clipped",
                    "Clipped",
                    date(2026, 12, 30),
                    date(2027, 1, 5),
                ),
            ],
        )

    def test_lists_episodes_with_the_training_inside_them(self):
        report = sickness_report(
            self._source(),
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )

        self.assertIn("# Sickness report", report)
        self.assertIn("2026-01-01 → 2026-12-31", report)
        self.assertIn("- Episodes: 3", report)
        self.assertIn("- Illness days: 10 of 365 (2.7%)", report)
        self.assertIn("- Longest: 5 days (2026-02-01 → 2026-02-05, Flu)", report)
        self.assertIn(
            "| 2026-02-01 | 2026-02-05 | 5 | Flu | 2 | 1h30 | 70 |",
            report,
        )
        self.assertIn(
            "| 2026-09-01 | 2026-09-03 | 3 | Cold | 1 | 40min | 30 |",
            report,
        )
        # The outside episode is gone and the clipped one stops at the range.
        self.assertNotIn("Old", report)
        self.assertIn(
            "| 2026-12-30 | 2026-12-31 | 2 | Clipped | 0 | - | 0 |",
            report,
        )
        # Newest episode first.
        self.assertLess(
            report.index("| 2026-12-30"),
            report.index("| 2026-09-01"),
        )
        self.assertLess(
            report.index("| 2026-09-01"),
            report.index("| 2026-02-01"),
        )
        self.assertIn(
            "- Current: day 2 of Clipped (from 2026-12-30)",
            report,
        )

    def test_ongoing_period_runs_to_the_range_end(self):
        source = FakeSource(
            periods=[
                TrainingPeriod(
                    id="now",
                    kind="illness",
                    label="Sick",
                    start_date=date(2026, 6, 28),
                )
            ]
        )

        report = sickness_report(
            source,
            start=date(2026, 6, 1),
            end=date(2026, 7, 2),
        )

        self.assertIn(
            "| 2026-06-28 | 2026-07-02 | 5 | Sick | 0 | - | 0 |",
            report,
        )
        self.assertIn("- Current: day 5 of Sick (from 2026-06-28)", report)

    def test_no_episodes_and_invalid_range(self):
        report = sickness_report(
            FakeSource(),
            start=date(2026, 1, 1),
            end=date(2026, 7, 1),
        )

        self.assertIn("- No illness periods in this range", report)

        with self.assertRaises(ValueError):
            sickness_report(
                FakeSource(),
                start=date(2026, 7, 1),
                end=date(2026, 1, 1),
            )


if __name__ == "__main__":
    unittest.main()
