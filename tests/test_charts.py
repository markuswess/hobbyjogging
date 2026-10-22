import tempfile
import unittest
from datetime import date
from pathlib import Path

from intervals_report.charts import plot_subt_hr, plot_subt_paces
from intervals_report.model import SubtPoint

D = date(2026, 1, 1)

POINTS = [
    SubtPoint(D, "short", 220, avg_hr=160),
    SubtPoint(date(2026, 1, 2), "short", 225, avg_hr=None),
    SubtPoint(date(2026, 1, 3), "medium", 230, avg_hr=158),
    SubtPoint(date(2026, 1, 4), "long", 240, avg_hr=150),
    SubtPoint(date(2026, 1, 5), "lt1", 245, avg_hr=145),
]


class SubtChartTests(unittest.TestCase):

    def test_pace_chart_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pace.png"

            result = plot_subt_paces(POINTS, str(output))

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_hr_chart_writes_file_and_skips_missing_hr(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "hr.png"

            result = plot_subt_hr(POINTS, str(output))

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
