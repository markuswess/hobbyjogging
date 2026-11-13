"""Coverage: every report renders non-empty content on the demo database."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from hobbyjogging_report.analysis import race_results
from hobbyjogging_report.dashboard.reports import REPORT_NAMES, build_report
from hobbyjogging_report.demo import generate_demo_database
from hobbyjogging_report.equipment_report import equipment_report
from hobbyjogging_report.race_report import race_report, races_report
from hobbyjogging_report.sessions import session_report
from hobbyjogging_report.sources import create_source
from hobbyjogging_report.subt_ewma_report import subt_ewma_report

TODAY = date(2026, 11, 12)

REPORT_MARKERS = {
    "overview": ("Training Overview", "Efficiency"),
    "recovery-report": ("Recovery Report", "HRV", "Resting HR"),
    "daily": ("Daily Training Report", "## Yesterday"),
    "weekly": ("Weekly Training Report", "## Categories"),
    "monthly": ("Monthly Training Report", "## Categories"),
    "yearly": ("Yearly Training Report", "## Categories"),
    "report": ("Custom Training Report", "## Categories"),
    "planned": ("Planned Workouts", "## Summary"),
    "subt-report": ("subT Report", "## Summary", "## Short"),
    "compare-years": ("Training Comparison by Year", "|"),
    "compare-months": ("Training Comparison by Month", "|"),
}


class DemoCoverageTests(unittest.TestCase):

    def test_every_report_renders_demo_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )
            source = create_source(database_path=summary.path)

            try:
                for name in REPORT_NAMES:
                    report = build_report(name, source, today=TODAY)

                    self.assertTrue(report.strip(), name)
                    for marker in REPORT_MARKERS[name]:
                        self.assertIn(marker, report, name)

                races = races_report(source, today=TODAY)
                for marker in (
                    "# Races",
                    "## Results",
                    "## Personal bests",
                    "Riegel estimate",
                ):
                    self.assertIn(marker, races)

                equipment = equipment_report(source, today=TODAY)
                for marker in ("# Gear", "## Coverage"):
                    self.assertIn(marker, equipment)

                ewma = subt_ewma_report(source, today=TODAY)
                for marker in (
                    "subT EWMA Report",
                    "## Pace",
                    "## Heart rate",
                    "## Efficiency",
                ):
                    self.assertIn(marker, ewma)

                session = session_report("last", source, today=TODAY)
                for marker in ("# Session", "- Duration"):
                    self.assertIn(marker, session)

                results = race_results(
                    source.activities(date(2015, 1, 1), TODAY)
                )
                self.assertTrue(results, "demo has no completed races")
                race = race_report(
                    results[0].activity.id,
                    source,
                    today=TODAY,
                )
                self.assertIn("# Race", race)
                self.assertIn("- Time:", race)
            finally:
                source.close()


if __name__ == "__main__":
    unittest.main()
