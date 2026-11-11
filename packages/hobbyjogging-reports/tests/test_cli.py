import argparse
import io
import unittest
from contextlib import redirect_stderr
from datetime import date, timedelta

from hobbyjogging_report.cli import (
    date_arg,
    extract_globals,
    parse_chart_args,
    parse_classify_args,
    parse_compare_args,
    parse_dashboard_args,
    parse_load_args,
    parse_overview_args,
    parse_overview_chart_args,
    parse_planned_args,
    parse_recovery_args,
    parse_report_args,
    parse_time_args,
    resolve_forward_range,
    resolve_range,
)
from hobbyjogging_report.model import AverageWindows

TODAY = date(2026, 10, 22)


class ResolveRangeTests(unittest.TestCase):

    def test_default_lookback_is_inclusive(self):
        self.assertEqual(
            (TODAY - timedelta(days=30), TODAY),
            resolve_range(30, today=TODAY),
        )

    def test_explicit_range_is_used_directly(self):
        self.assertEqual(
            (date(2026, 1, 1), date(2026, 1, 31)),
            resolve_range(
                30,
                start=date(2026, 1, 1),
                end=date(2026, 1, 31),
                today=TODAY,
            ),
        )

    def test_start_only_runs_to_today(self):
        self.assertEqual(
            (date(2026, 9, 1), TODAY),
            resolve_range(30, start=date(2026, 9, 1), today=TODAY),
        )

    def test_end_only_counts_back_from_end(self):
        self.assertEqual(
            (date(2026, 1, 1), date(2026, 1, 31)),
            resolve_range(
                30,
                end=date(2026, 1, 31),
                today=TODAY,
            ),
        )

    def test_zero_days_is_a_single_day(self):
        self.assertEqual(
            (TODAY, TODAY),
            resolve_range(0, today=TODAY),
        )

    def test_rejects_negative_days(self):
        with self.assertRaises(ValueError):
            resolve_range(-1, today=TODAY)

    def test_rejects_reversed_range(self):
        with self.assertRaises(ValueError):
            resolve_range(
                30,
                start=date(2026, 2, 1),
                end=date(2026, 1, 1),
                today=TODAY,
            )

    def test_rejects_start_after_today(self):
        with self.assertRaises(ValueError):
            resolve_range(
                30,
                start=date(2026, 11, 1),
                today=TODAY,
            )


class ForwardRangeTests(unittest.TestCase):

    def test_default_horizon_is_today_plus_days(self):
        self.assertEqual(
            (TODAY, TODAY + timedelta(days=28)),
            resolve_forward_range(28, today=TODAY),
        )

    def test_zero_days_is_a_single_day(self):
        self.assertEqual(
            (TODAY, TODAY),
            resolve_forward_range(0, today=TODAY),
        )

    def test_rejects_negative_days(self):
        with self.assertRaises(ValueError):
            resolve_forward_range(-1, today=TODAY)

    def test_explicit_range_is_used_directly(self):
        self.assertEqual(
            (date(2026, 11, 1), date(2026, 12, 15)),
            resolve_forward_range(
                28,
                start=date(2026, 11, 1),
                end=date(2026, 12, 15),
                today=TODAY,
            ),
        )

    def test_start_only_runs_days_from_start(self):
        self.assertEqual(
            (date(2026, 11, 1), date(2026, 11, 29)),
            resolve_forward_range(
                28,
                start=date(2026, 11, 1),
                today=TODAY,
            ),
        )

    def test_end_only_runs_from_today(self):
        self.assertEqual(
            (TODAY, date(2026, 12, 15)),
            resolve_forward_range(
                28,
                end=date(2026, 12, 15),
                today=TODAY,
            ),
        )

    def test_rejects_reversed_range(self):
        with self.assertRaises(ValueError):
            resolve_forward_range(
                28,
                start=date(2026, 12, 15),
                end=date(2026, 11, 1),
                today=TODAY,
            )

    def test_rejects_end_before_today(self):
        with self.assertRaises(ValueError):
            resolve_forward_range(
                28,
                end=date(2026, 10, 1),
                today=TODAY,
            )


class PlannedArgsTests(unittest.TestCase):

    def test_default_is_next_28_days(self):
        self.assertEqual(
            (TODAY, TODAY + timedelta(days=28)),
            parse_planned_args([], today=TODAY),
        )

    def test_days_option(self):
        self.assertEqual(
            (TODAY, TODAY + timedelta(days=56)),
            parse_planned_args(["--days", "56"], today=TODAY),
        )

    def test_explicit_range(self):
        self.assertEqual(
            (date(2026, 11, 1), date(2026, 12, 15)),
            parse_planned_args(
                ["--from", "2026-11-01", "--to", "2026-12-15"],
                today=TODAY,
            ),
        )

    def test_from_only(self):
        self.assertEqual(
            (date(2026, 11, 1), date(2026, 11, 29)),
            parse_planned_args(
                ["--from", "2026-11-01"],
                today=TODAY,
            ),
        )

    def test_to_only(self):
        self.assertEqual(
            (TODAY, date(2026, 12, 15)),
            parse_planned_args(
                ["--to", "2026-12-15"],
                today=TODAY,
            ),
        )


class ClassifyArgsTests(unittest.TestCase):

    def test_positional_days_still_work(self):
        self.assertEqual(
            (TODAY - timedelta(days=7), TODAY),
            parse_classify_args(["7"], today=TODAY),
        )

    def test_days_option(self):
        self.assertEqual(
            (TODAY - timedelta(days=14), TODAY),
            parse_classify_args(["--days", "14"], today=TODAY),
        )

    def test_days_option_overrides_positional_days(self):
        self.assertEqual(
            (TODAY - timedelta(days=7), TODAY),
            parse_classify_args(
                ["30", "--days", "7"],
                today=TODAY,
            ),
        )

    def test_explicit_range(self):
        self.assertEqual(
            (date(2026, 3, 1), date(2026, 3, 31)),
            parse_classify_args(
                ["--from", "2026-03-01", "--to", "2026-03-31"],
                today=TODAY,
            ),
        )


class ReportArgsTests(unittest.TestCase):

    def test_default_lookback(self):
        self.assertEqual(
            (TODAY - timedelta(days=30), TODAY),
            parse_report_args([], today=TODAY),
        )

    def test_days_option(self):
        self.assertEqual(
            (TODAY - timedelta(days=90), TODAY),
            parse_report_args(["--days", "90"], today=TODAY),
        )

    def test_explicit_range(self):
        self.assertEqual(
            (date(2026, 1, 1), date(2026, 3, 31)),
            parse_report_args(
                ["--from", "2026-01-01", "--to", "2026-03-31"],
                today=TODAY,
            ),
        )

    def test_end_only(self):
        self.assertEqual(
            (date(2026, 5, 1), date(2026, 6, 30)),
            parse_report_args(
                ["--to", "2026-06-30", "--days", "60"],
                today=TODAY,
            ),
        )


class ChartArgsTests(unittest.TestCase):

    def test_positional_output_still_works(self):
        output, start, end = parse_chart_args(
            ["pace.png"],
            default_output="default.png",
            default_days=365,
            today=TODAY,
        )

        self.assertEqual("pace.png", output)
        self.assertEqual(TODAY - timedelta(days=365), start)
        self.assertEqual(TODAY, end)

    def test_days_and_output_options(self):
        output, start, end = parse_chart_args(
            ["--days", "90", "--output", "hr.png"],
            default_output="default.png",
            default_days=365,
            today=TODAY,
        )

        self.assertEqual("hr.png", output)
        self.assertEqual(TODAY - timedelta(days=90), start)
        self.assertEqual(TODAY, end)

    def test_explicit_range_with_positional_output(self):
        output, start, end = parse_chart_args(
            ["pace.png", "--from", "2026-01-01", "--to", "2026-01-31"],
            default_output="default.png",
            default_days=365,
            today=TODAY,
        )

        self.assertEqual("pace.png", output)
        self.assertEqual(date(2026, 1, 1), start)
        self.assertEqual(date(2026, 1, 31), end)


class LoadArgsTests(unittest.TestCase):

    def test_defaults(self):
        output, start, end, planned_end, windows = parse_load_args(
            [],
            today=TODAY,
        )

        self.assertEqual("load.png", output)
        self.assertEqual(TODAY - timedelta(days=180), start)
        self.assertEqual(TODAY, end)
        self.assertEqual(TODAY + timedelta(days=28), planned_end)
        self.assertEqual(AverageWindows(), windows)

    def test_custom_windows_and_output(self):
        output, start, end, planned_end, windows = parse_load_args(
            [
                "--days", "30",
                "--base-days", "100",
                "--fitness-days", "20",
                "--fatigue-days", "5",
                "--output", "custom.png",
            ],
            today=TODAY,
        )

        self.assertEqual("custom.png", output)
        self.assertEqual(TODAY - timedelta(days=30), start)
        self.assertEqual(TODAY, end)
        self.assertEqual(TODAY + timedelta(days=28), planned_end)
        self.assertEqual(
            AverageWindows(base=100, fitness=20, fatigue=5),
            windows,
        )

    def test_positional_output(self):
        output, _, _, _, _ = parse_load_args(
            ["load.png"],
            today=TODAY,
        )

        self.assertEqual("load.png", output)

    def test_rejects_non_positive_window(self):
        with self.assertRaises(ValueError):
            parse_load_args(
                ["--fitness-days", "0"],
                today=TODAY,
            )

    def test_explicit_to_is_not_extended(self):
        _, _, end, planned_end, _ = parse_load_args(
            ["--to", "2026-10-31"],
            today=TODAY,
        )

        self.assertEqual(date(2026, 10, 31), end)
        self.assertEqual(end, planned_end)

    def test_planned_days_can_be_disabled(self):
        _, _, end, planned_end, _ = parse_load_args(
            ["--planned-days", "0"],
            today=TODAY,
        )

        self.assertEqual(end, planned_end)

    def test_custom_planned_days(self):
        _, _, end, planned_end, _ = parse_load_args(
            ["--planned-days", "14"],
            today=TODAY,
        )

        self.assertEqual(end + timedelta(days=14), planned_end)

    def test_rejects_negative_planned_days(self):
        with self.assertRaises(ValueError):
            parse_load_args(["--planned-days", "-1"], today=TODAY)


class TimeArgsTests(unittest.TestCase):

    def test_defaults(self):
        (
            output,
            start,
            end,
            planned_end,
            windows,
            zones,
            zone_window,
        ) = parse_time_args([], today=TODAY)

        self.assertEqual("time.png", output)
        self.assertEqual(TODAY - timedelta(days=90), start)
        self.assertEqual(TODAY, end)
        self.assertEqual(TODAY + timedelta(days=28), planned_end)
        self.assertEqual(AverageWindows(), windows)
        self.assertEqual(4, zones)
        self.assertEqual("fitness", zone_window)

    def test_custom_zones_and_zone_window(self):
        (
            output,
            _,
            _,
            _,
            _,
            zones,
            zone_window,
        ) = parse_time_args(
            [
                "--zones", "4",
                "--zone-window", "base",
                "--output", "zones.png",
            ],
            today=TODAY,
        )

        self.assertEqual("zones.png", output)
        self.assertEqual(4, zones)
        self.assertEqual("base", zone_window)

    def test_rejects_non_positive_zones(self):
        with self.assertRaises(ValueError):
            parse_time_args(["--zones", "0"], today=TODAY)


class RecoveryArgsTests(unittest.TestCase):

    def test_defaults(self):
        output, start, end, planned_end, window = parse_recovery_args(
            [],
            today=TODAY,
        )

        self.assertEqual("recovery.png", output)
        self.assertEqual(TODAY - timedelta(days=90), start)
        self.assertEqual(TODAY, end)
        self.assertEqual(TODAY + timedelta(days=28), planned_end)
        self.assertEqual(7, window)

    def test_custom_window_and_output(self):
        output, _, _, _, window = parse_recovery_args(
            ["--window", "14", "--output", "hrv.png"],
            today=TODAY,
        )

        self.assertEqual("hrv.png", output)
        self.assertEqual(14, window)

    def test_explicit_to_is_not_extended(self):
        _, _, end, planned_end, _ = parse_recovery_args(
            ["--to", "2026-10-31"],
            today=TODAY,
        )

        self.assertEqual(date(2026, 10, 31), end)
        self.assertEqual(end, planned_end)

    def test_rejects_non_positive_window(self):
        with self.assertRaises(ValueError):
            parse_recovery_args(["--window", "0"], today=TODAY)


class CompareArgsTests(unittest.TestCase):

    def test_years_default_to_all_years(self):
        self.assertEqual(
            ("years", None, TODAY),
            parse_compare_args(["years"], today=TODAY),
        )

    def test_months_default_to_last_12_calendar_months(self):
        self.assertEqual(
            ("months", date(2025, 11, 1), TODAY),
            parse_compare_args(["months"], today=TODAY),
        )

    def test_explicit_range(self):
        self.assertEqual(
            ("months", date(2026, 1, 1), date(2026, 3, 31)),
            parse_compare_args(
                ["months", "--from", "2026-01-01", "--to", "2026-03-31"],
                today=TODAY,
            ),
        )

    def test_to_only_months_uses_12_months_ending_there(self):
        self.assertEqual(
            ("months", date(2025, 12, 1), date(2026, 11, 30)),
            parse_compare_args(
                ["months", "--to", "2026-11-30"],
                today=TODAY,
            ),
        )

    def test_days_option(self):
        self.assertEqual(
            ("months", TODAY - timedelta(days=30), TODAY),
            parse_compare_args(
                ["months", "--days", "30"],
                today=TODAY,
            ),
        )

    def test_rejects_negative_days(self):
        with self.assertRaises(ValueError):
            parse_compare_args(
                ["months", "--days", "-1"],
                today=TODAY,
            )

    def test_rejects_reversed_range(self):
        with self.assertRaises(ValueError):
            parse_compare_args(
                ["years", "--from", "2026-02-01", "--to", "2026-01-01"],
                today=TODAY,
            )

    def test_rejects_unknown_mode(self):
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                parse_compare_args(["weeks"], today=TODAY)


class DashboardArgsTests(unittest.TestCase):

    def test_defaults(self):
        self.assertEqual(
            (None, 14, 50, 182, 14, 186, 731, ()),
            parse_dashboard_args([]),
        )

    def test_custom_output_and_limits(self):
        self.assertEqual(
            (
                "/tmp/site", 30, 100, 90, 21, 60, 120,
                ("overview", "daily"),
            ),
            parse_dashboard_args(
                [
                    "--output", "/tmp/site",
                    "--days", "30",
                    "--activities", "100",
                    "--chart-days", "90",
                    "--future-days", "21",
                    "--recovery-days", "60",
                    "--analysis-days", "120",
                    "--reports", "overview,daily",
                ]
            ),
        )

    def test_rejects_non_positive_days(self):
        with self.assertRaises(ValueError):
            parse_dashboard_args(["--days", "0"])

    def test_rejects_non_positive_activities(self):
        with self.assertRaises(ValueError):
            parse_dashboard_args(["--activities", "0"])

    def test_rejects_non_positive_chart_days(self):
        with self.assertRaises(ValueError):
            parse_dashboard_args(["--chart-days", "0"])

    def test_rejects_negative_future_days(self):
        with self.assertRaises(ValueError):
            parse_dashboard_args(["--future-days", "-1"])

    def test_rejects_non_positive_recovery_days(self):
        with self.assertRaises(ValueError):
            parse_dashboard_args(["--recovery-days", "0"])

    def test_rejects_non_positive_analysis_days(self):
        with self.assertRaises(ValueError):
            parse_dashboard_args(["--analysis-days", "0"])

    def test_rejects_unknown_reports(self):
        with self.assertRaises(ValueError):
            parse_dashboard_args(["--reports", "overview,nope"])


class OverviewChartArgsTests(unittest.TestCase):

    def test_defaults(self):
        self.assertEqual(
            ("overview.png", 182, 14, TODAY),
            parse_overview_chart_args([], today=TODAY),
        )

    def test_custom_output_and_ranges(self):
        self.assertEqual(
            ("/tmp/overview.png", 90, 21, TODAY),
            parse_overview_chart_args(
                [
                    "--output", "/tmp/overview.png",
                    "--chart-days", "90",
                    "--future-days", "21",
                ],
                today=TODAY,
            ),
        )

    def test_rejects_invalid_ranges(self):
        with self.assertRaises(ValueError):
            parse_overview_chart_args(
                ["--chart-days", "0"],
                today=TODAY,
            )
        with self.assertRaises(ValueError):
            parse_overview_chart_args(
                ["--future-days", "-1"],
                today=TODAY,
            )


class OverviewArgsTests(unittest.TestCase):

    def test_defaults(self):
        self.assertEqual(
            (14, TODAY),
            parse_overview_args([], today=TODAY),
        )

    def test_custom_future_days(self):
        self.assertEqual(
            (21, TODAY),
            parse_overview_args(
                ["--future-days", "21"],
                today=TODAY,
            ),
        )

    def test_rejects_negative_future_days(self):
        with self.assertRaises(ValueError):
            parse_overview_args(
                ["--future-days", "-1"],
                today=TODAY,
            )


class GlobalArgTests(unittest.TestCase):

    def test_defaults_to_no_review(self):
        self.assertEqual((False, ["weekly"]), extract_globals(["weekly"]))

    def test_include_review_flag_is_extracted(self):
        self.assertEqual(
            (True, ["weekly"]),
            extract_globals(["--include-review", "weekly"]),
        )

    def test_source_option_is_rejected_with_a_pointer(self):
        with self.assertRaises(SystemExit) as raised:
            extract_globals(["--source", "intervals", "weekly"])

        self.assertIn("--source was removed", str(raised.exception))

    def test_include_review_can_follow_the_mode(self):
        self.assertEqual(
            (True, ["weekly"]),
            extract_globals(["weekly", "--include-review"]),
        )


class DateArgTests(unittest.TestCase):

    def test_parses_iso_date(self):
        self.assertEqual(date(2026, 1, 31), date_arg("2026-01-31"))

    def test_rejects_invalid_date(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            date_arg("31.01.2026")


if __name__ == "__main__":
    unittest.main()
