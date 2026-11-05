import math
import unittest
from datetime import date

from hobbyjogging_report.series import (
    alpha_from_half_life,
    alpha_from_span,
    alpha_from_time_constant,
    daily_sums,
    date_range,
    ewma,
    ewma_series,
    rolling_mean_by_date,
    sma,
)

D = date(2026, 1, 1)


class DateSeriesTests(unittest.TestCase):

    def test_date_range_is_inclusive(self):
        self.assertEqual(
            [D, date(2026, 1, 2), date(2026, 1, 3)],
            date_range(D, date(2026, 1, 3)),
        )

    def test_reversed_date_range_is_empty(self):
        self.assertEqual([], date_range(date(2026, 1, 3), D))

    def test_daily_sums_zero_fill(self):
        series = daily_sums(
            {D: 40.0, date(2026, 1, 3): 60.0},
            D,
            date(2026, 1, 3),
        )

        self.assertEqual(
            [(D, 40.0), (date(2026, 1, 2), 0.0), (date(2026, 1, 3), 60.0)],
            series,
        )

    def test_daily_sums_can_use_another_fill(self):
        series = daily_sums(
            {D: 40.0},
            D,
            date(2026, 1, 2),
            fill=1.0,
        )

        self.assertEqual([(D, 40.0), (date(2026, 1, 2), 1.0)], series)


class AverageTests(unittest.TestCase):

    def test_sma_includes_current_value(self):
        self.assertEqual(
            [1.0, 1.5, 2.5, 3.5],
            sma([1, 2, 3, 4], 2),
        )

    def test_sma_rejects_non_positive_window(self):
        with self.assertRaises(ValueError):
            sma([1, 2], 0)

    def test_ewma_with_explicit_alpha(self):
        self.assertEqual(
            [0.5, 1.25, 2.125],
            ewma([1, 2, 3], 0.5),
        )

    def test_ewma_supports_initial_state(self):
        self.assertEqual(
            [1.0, 1.5, 2.25],
            ewma([1, 2, 3], 0.5, initial=1.0),
        )

    def test_ewma_series_keeps_dates(self):
        points = [(D, 1.0), (date(2026, 1, 2), 2.0)]

        self.assertEqual(
            [(D, 0.5), (date(2026, 1, 2), 1.25)],
            ewma_series(points, 0.5),
        )

    def test_alpha_from_time_constant(self):
        self.assertAlmostEqual(
            1 - math.exp(-1),
            alpha_from_time_constant(1),
        )

    def test_alpha_from_half_life(self):
        self.assertAlmostEqual(0.5, alpha_from_half_life(1))

    def test_alpha_from_span(self):
        self.assertAlmostEqual(2 / 43, alpha_from_span(42))

    def test_rejects_invalid_alpha(self):
        with self.assertRaises(ValueError):
            ewma([1], 0)

    def test_rejects_invalid_alpha_helpers(self):
        with self.assertRaises(ValueError):
            alpha_from_time_constant(0)
        with self.assertRaises(ValueError):
            alpha_from_half_life(0)
        with self.assertRaises(ValueError):
            alpha_from_span(0)


class RollingDateAverageTests(unittest.TestCase):

    def test_uses_calendar_window_and_skips_missing(self):
        points = [
            (D, 50.0),
            (date(2026, 1, 3), 60.0),
            (date(2026, 1, 8), 70.0),
        ]

        self.assertEqual(
            [50.0, 55.0, 65.0],
            rolling_mean_by_date(points, 7),
        )

    def test_missing_values_do_not_pull_average_down(self):
        points = [
            (D, 50.0),
            (date(2026, 1, 2), None),
            (date(2026, 1, 3), 60.0),
        ]

        self.assertEqual(
            [50.0, 50.0, 55.0],
            rolling_mean_by_date(points, 7),
        )

    def test_all_missing_returns_none(self):
        points = [(D, None), (date(2026, 1, 2), None)]

        self.assertEqual(
            [None, None],
            rolling_mean_by_date(points, 7),
        )

    def test_rejects_non_positive_window(self):
        with self.assertRaises(ValueError):
            rolling_mean_by_date([(D, 50.0)], 0)


if __name__ == "__main__":
    unittest.main()
