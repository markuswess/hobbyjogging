import argparse
import unittest
from datetime import date, timedelta

from intervals_report.cli import (
    date_arg,
    parse_chart_args,
    parse_classify_args,
    parse_report_args,
    resolve_range,
)

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


class DateArgTests(unittest.TestCase):

    def test_parses_iso_date(self):
        self.assertEqual(date(2026, 1, 31), date_arg("2026-01-31"))

    def test_rejects_invalid_date(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            date_arg("31.01.2026")


if __name__ == "__main__":
    unittest.main()
