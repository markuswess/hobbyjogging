import unittest
from datetime import date
from unittest.mock import patch

from hobbyjogging_core.model import Activity
from hobbyjogging_report.mdpretty import render_markdown
from hobbyjogging_report.reports import daily, period_report

D1 = date(2026, 10, 1)


class FixedDate(date):

    @classmethod
    def today(cls):
        return cls(2026, 10, 2)


class FakeSource:

    def __init__(self, activities, intervals=None):
        self._activities = activities
        self._intervals = intervals or {}

    def activities(self, start, end):
        return [
            activity
            for activity in self._activities
            if start <= activity.date <= end
        ]

    def wellness(self, start, end):
        return []

    def events(self, start, end):
        return []

    def activity_intervals(self, activity_id):
        return self._intervals.get(activity_id, [])


def activity(**overrides):
    values = dict(
        id="a",
        date=D1,
        type="run",
        name="Easy",
        duration_s=2400,
        distance_m=8000,
        avg_hr=140,
    )
    values.update(overrides)
    return Activity(**values)


MULTILINE = "# Warm up\n- 10 min easy\n\n## Main\n3 x 10 min"


class DailyDescriptionTests(unittest.TestCase):

    def test_activity_description_is_fenced(self):
        source = FakeSource(
            [activity(name="Easy", description=MULTILINE)]
        )

        with patch("hobbyjogging_report.reports.date", FixedDate):
            report = daily(source)

        self.assertIn("## Yesterday", report)
        self.assertIn("- Description:", report)
        self.assertIn("  ```", report)
        self.assertIn("  # Warm up", report)
        self.assertIn("  - 10 min easy", report)
        self.assertIn("  ## Main", report)
        self.assertNotIn("- Description: # Warm up", report)
        self.assertIn(
            "- Description:\n"
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
