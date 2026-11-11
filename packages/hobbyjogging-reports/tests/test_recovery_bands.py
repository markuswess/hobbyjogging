import unittest
from datetime import date, timedelta

from hobbyjogging_report.analysis import recovery_bands
from hobbyjogging_report.model import RecoveryPoint

D = date(2026, 1, 1)


def _points(days: int, *, hrv=None, rhr=None, sleep=7 * 3600):
    return [
        RecoveryPoint(
            date=D + timedelta(days=offset),
            hrv=hrv(offset) if hrv else None,
            resting_hr=rhr(offset) if rhr else None,
            sleep_s=sleep,
        )
        for offset in range(days)
    ]


class RecoveryBandTests(unittest.TestCase):

    def test_hrv_bands_follow_the_42_day_baseline(self):
        # Constant baseline 50 with a ±2 ms swing: sd = 2.
        bands = recovery_bands(
            _points(42, hrv=lambda offset: 50 + (2 if offset % 2 else -2))
        )
        normal, watch, alert = bands.hrv

        self.assertEqual("normal", normal.level)
        self.assertAlmostEqual(50.0, normal.low)
        self.assertIsNone(normal.high)
        self.assertAlmostEqual(48.0, watch.low)
        self.assertAlmostEqual(50.0, watch.high)
        self.assertIsNone(alert.low)
        self.assertAlmostEqual(48.0, alert.high)

    def test_resting_hr_bands_mirror_hrv(self):
        bands = recovery_bands(
            _points(42, rhr=lambda offset: 48 + (1 if offset % 2 else -1))
        )
        normal, watch, alert = bands.resting_hr

        self.assertEqual("normal", normal.level)
        self.assertIsNone(normal.low)
        self.assertAlmostEqual(48.0, normal.high)
        self.assertAlmostEqual(48.0, watch.low)
        self.assertAlmostEqual(49.0, watch.high)
        self.assertAlmostEqual(49.0, alert.low)
        self.assertIsNone(alert.high)

    def test_sleep_bands_are_absolute(self):
        bands = recovery_bands(_points(3))

        levels = [(band.level, band.low, band.high) for band in bands.sleep_s]

        self.assertIn(("normal", 7 * 3600, 9 * 3600), levels)
        self.assertIn(("watch", 6 * 3600, 7 * 3600), levels)
        self.assertIn(("watch", 9 * 3600, 10 * 3600), levels)
        self.assertIn(("alert", None, 6 * 3600), levels)
        self.assertIn(("alert", 10 * 3600, None), levels)

    def test_too_little_history_has_no_hrv_or_rhr_bands(self):
        bands = recovery_bands(_points(3, hrv=lambda _: 50, rhr=lambda _: 48))

        self.assertEqual((), bands.hrv)
        self.assertEqual((), bands.resting_hr)
        self.assertTrue(bands.sleep_s)

    def test_no_points_has_no_bands(self):
        bands = recovery_bands([])

        self.assertEqual((), bands.hrv)
        self.assertEqual((), bands.resting_hr)
        self.assertEqual((), bands.sleep_s)


if __name__ == "__main__":
    unittest.main()
