import unittest
from datetime import date, timedelta
from unittest.mock import patch

from hobbyjogging_core.model import Event

from hobbyjogging_report.html import markdown_to_html
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


FIXED_TODAY = date(2026, 10, 2)

MULTILINE = "# Warm up\n- 10 min easy\n\n## Main\n3 x 10 min"


class DailyDescriptionTests(unittest.TestCase):

    def test_activity_description_is_markdown(self):
        source = FakeSource(
            [activity(name="Easy", description=MULTILINE)]
        )

        with patch("hobbyjogging_report.daily.date", FixedDate):
            report = daily(source)

        self.assertIn("## Yesterday", report)
        self.assertIn("# Warm up", report)
        self.assertIn("- 10 min easy", report)
        self.assertIn("## Main", report)
        self.assertIn("3 x 10 min", report)
        self.assertNotIn("- Description:", report)
        self.assertNotIn("```", report)

        pretty = render_markdown(report, color=False)

        self.assertIn("Warm up", pretty)
        self.assertIn("10 min easy", pretty)
        self.assertNotIn("```", pretty)

    def test_planned_list_after_paragraph_stays_a_list(self):
        source = FakeSource(
            [activity(name="Easy", date=FIXED_TODAY)],
            events=[
                Event(
                    date=FIXED_TODAY + timedelta(days=1),
                    name="Easy",
                    type="run",
                    description="1x\n- 45m 60-68% Pace",
                    duration_s=2700,
                ),
            ],
        )

        with patch("hobbyjogging_report.daily.date", FixedDate):
            report = daily(source)

        self.assertIn("1x\n\n- 45m 60-68% Pace", report)

        html = markdown_to_html(report, demote=1)

        self.assertIn("<p>1x</p>", html)
        self.assertIn("<li>45m 60-68% Pace</li>", html)


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
