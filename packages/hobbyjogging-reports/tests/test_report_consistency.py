import unittest
from datetime import date
from unittest.mock import patch

from hobbyjogging_core.model import WellnessDay
from hobbyjogging_report.mdpretty import render_markdown
from hobbyjogging_report.daily import daily
from hobbyjogging_report.period_report import period_report
from support import FakeSource, activity_factory

D1 = date(2026, 10, 1)

activity = activity_factory(
    name="Easy",
    duration_s=2400,
    distance_m=8000,
    avg_hr=140,
)


class FixedDate(date):

    @classmethod
    def today(cls):
        return cls(2026, 10, 2)


MULTILINE = "# Warm up\n- 10 min easy\n\n## Main\n3 x 10 min"


class DailyDescriptionTests(unittest.TestCase):

    def test_activity_description_is_code_block(self):
        source = FakeSource(
            [activity(name="Easy", description=MULTILINE)]
        )

        with patch("hobbyjogging_report.daily.date", FixedDate):
            report = daily(source)

        self.assertIn("## Yesterday", report)
        self.assertIn("```\n# Warm up\n- 10 min easy\n", report)
        self.assertIn("## Main", report)
        self.assertIn("3 x 10 min", report)
        self.assertNotIn("- Description:", report)

        pretty = render_markdown(report, color=False)

        self.assertNotIn("▌ Warm up", pretty)
        self.assertNotIn("▌ Main", pretty)
        self.assertIn("│ # Warm up", pretty)


class EfficiencyReportTests(unittest.TestCase):

    def _source(self):
        return FakeSource(
            [
                activity(
                    name="Easy",
                    duration_s=2400,
                    distance_m=8000,
                    avg_hr=140,
                    rpe=2,
                    training_load=32,
                )
            ],
            wellness=[
                WellnessDay(
                    date=D1,
                    resting_hr=50,
                    hrv=55,
                    sleep_s=7.5 * 3600,
                )
            ],
        )

    def test_daily_compact_line_includes_efficiency(self):
        with patch("hobbyjogging_report.daily.date", FixedDate):
            report = daily(self._source())

        # 8 km / ((140 - 50) * 40) excess beats.
        self.assertIn(
            "- Efficiency: 2.22 m/excess beat",
            report,
        )

    def test_period_report_has_weighted_total_and_category_cell(self):
        report = period_report(
            D1,
            D1,
            "Test Report",
            self._source(),
        )

        self.assertIn("- Efficiency: 2.22 m/excess beat", report)
        self.assertIn(
            "| non-quality/easy | 1 | 40min | 32 | 2.22 | 100% | 100% |",
            report,
        )


class PeriodDescriptionTests(unittest.TestCase):

    def test_quality_comments_are_fenced(self):
        source = FakeSource(
            [
                activity(
                    name="5x5' subT medium",
                    duration_s=3000,
                    distance_m=10000,
                    rpe=5,
                    description=MULTILINE,
                )
            ],
            {"a": []},
        )

        report = period_report(D1, D1, "Test Report", source)

        self.assertIn("### 5x5' subT medium", report)
        self.assertIn("- Totals:", report)
        self.assertIn("- Comments:", report)
        self.assertIn("  ```", report)
        self.assertIn("  # Warm up", report)
        self.assertIn("  ## Main", report)
        self.assertNotIn("Comments: # Warm up", report)
        self.assertIn(
            "### 5x5' subT medium\n"
            "- Totals: 50min, 5:00/km, 140 BpM\n"
            "- Comments:\n"
            "  ```\n"
            "  # Warm up\n"
            "  - 10 min easy\n"
            "\n"
            "  ## Main\n"
            "  3 x 10 min\n"
            "  ```",
            report,
        )

        pretty = render_markdown(report, color=False)

        self.assertNotIn("▌ Warm up", pretty)
        self.assertNotIn("▌ Main", pretty)
        self.assertIn("│ # Warm up", pretty)


if __name__ == "__main__":
    unittest.main()
