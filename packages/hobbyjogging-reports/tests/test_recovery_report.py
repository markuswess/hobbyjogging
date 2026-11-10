import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import WellnessDay
from hobbyjogging_report.recovery_report import recovery_averages, recovery_report
from support import FakeSource

TODAY = date(2026, 11, 10)


def _wellness(days: int) -> list[WellnessDay]:
    return [
        WellnessDay(
            date=TODAY - timedelta(days=offset),
            hrv=50 + 2 * offset,
            resting_hr=46 + 2 * offset,
            sleep_s=7 * 3600 + offset * 600,
        )
        for offset in range(days)
    ]


def _row(report: str, label: str) -> list[str]:
    line = next(
        row
        for row in report.splitlines()
        if row.startswith(f"| {label} |")
    )

    return [cell.strip() for cell in line.strip("|").split("|")]


class RecoveryAverageTests(unittest.TestCase):

    def test_windows_average_the_trailing_days(self):
        averages = recovery_averages(_wellness(182), TODAY)

        # HRV rises by two per day: the 7-day window averages offsets
        # 0-6 (56), the 42-day window 0-41 (91), all 182 days 231.
        self.assertEqual(56.0, averages["HRV"][7])
        self.assertEqual(91.0, averages["HRV"][42])
        self.assertEqual(231.0, averages["HRV"][182])

    def test_missing_days_are_skipped_not_zero(self):
        wellness = [
            WellnessDay(date=TODAY, hrv=60, resting_hr=45, sleep_s=8 * 3600),
            WellnessDay(date=TODAY - timedelta(days=3), hrv=50),
        ]

        averages = recovery_averages(wellness, TODAY)

        self.assertEqual(55.0, averages["HRV"][7])
        self.assertEqual(45.0, averages["Resting HR"][7])
        self.assertAlmostEqual(8.0, averages["Sleep"][7] / 3600)

    def test_empty_range_returns_no_averages(self):
        averages = recovery_averages([], TODAY)

        for metric in averages.values():
            for window in (7, 42, 182):
                self.assertIsNone(metric[window])


class RecoveryReportTests(unittest.TestCase):

    def test_report_renders_metric_rows(self):
        source = FakeSource(wellness=_wellness(30))

        report = recovery_report(source, today=TODAY)

        self.assertIn("# Recovery Report — Moving Averages", report)
        self.assertIn(f"7/42/182-day averages ending {TODAY}", report)
        self.assertEqual(
            ["HRV", "56 ms", "79 ms", "79 ms"],
            _row(report, "HRV"),
        )
        self.assertEqual(
            ["Resting HR", "52 bpm", "75 bpm", "75 bpm"],
            _row(report, "Resting HR"),
        )
        self.assertEqual(
            ["Sleep", "7.5 h", "9.4 h", "9.4 h"],
            _row(report, "Sleep"),
        )
        self.assertIn("missing days are skipped", report)

    def test_report_lists_the_last_four_nights(self):
        source = FakeSource(wellness=_wellness(10))

        report = recovery_report(source, today=TODAY)

        self.assertIn("\n## Night\n", report)
        self.assertIn(
            f"- {TODAY}: HRV 50 ms, RHR 46 bpm, Sleep 7h00",
            report,
        )
        self.assertIn(
            f"- {TODAY - timedelta(days=3)}: HRV 56 ms, RHR 52 bpm, Sleep 7h30",
            report,
        )
        night_lines = [
            line
            for line in report.splitlines()
            if line.startswith("- 20")
        ]
        self.assertEqual(4, len(night_lines))

    def test_report_without_wellness(self):
        report = recovery_report(FakeSource(), today=TODAY)

        self.assertIn("No wellness data in the last 182 days.", report)


if __name__ == "__main__":
    unittest.main()
