import unittest
from datetime import date, timedelta

from hobbyjogging_report.analysis import recovery_bands, robust_baseline
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

    def test_hrv_bands_follow_the_robust_baseline(self):
        # Constant baseline 50 with a ±2 ms swing: median 50, MAD 2,
        # so the spread is 1.4826 * 2.
        bands = recovery_bands(
            _points(42, hrv=lambda offset: 50 + (2 if offset % 2 else -2))
        )
        normal, watch, alert = bands.hrv

        self.assertEqual("normal", normal.level)
        self.assertAlmostEqual(50.0, normal.low)
        self.assertIsNone(normal.high)
        self.assertAlmostEqual(50.0 - 1.4826 * 2, watch.low)
        self.assertAlmostEqual(50.0, watch.high)
        self.assertIsNone(alert.low)
        self.assertAlmostEqual(50.0 - 1.4826 * 2, alert.high)

    def test_resting_hr_bands_mirror_hrv(self):
        bands = recovery_bands(
            _points(42, rhr=lambda offset: 48 + (1 if offset % 2 else -1))
        )
        normal, watch, alert = bands.resting_hr

        self.assertEqual("normal", normal.level)
        self.assertIsNone(normal.low)
        self.assertAlmostEqual(48.0, normal.high)
        self.assertAlmostEqual(48.0, watch.low)
        self.assertAlmostEqual(48.0 + 1.4826, watch.high)
        self.assertAlmostEqual(48.0 + 1.4826, alert.low)
        self.assertIsNone(alert.high)

    def test_sleep_bands_are_absolute(self):
        bands = recovery_bands(_points(3))

        levels = [(band.level, band.low, band.high) for band in bands.sleep_s]

        self.assertIn(("normal", 7 * 3600, 9 * 3600), levels)
        self.assertIn(("watch", 6 * 3600, 7 * 3600), levels)
        self.assertIn(("watch", 9 * 3600, 10 * 3600), levels)
        self.assertIn(("alert", None, 6 * 3600), levels)
        self.assertIn(("alert", 10 * 3600, None), levels)

    def test_an_illness_sized_excursion_barely_moves_the_center(self):
        # A year at 51 followed by five days at 59 (the Feb-Mar 2026 shape).
        points = _points(360, rhr=lambda _offset: 51)
        points += [
            RecoveryPoint(
                date=D + timedelta(days=360 + offset),
                resting_hr=59,
            )
            for offset in range(5)
        ]

        normal, _, _ = recovery_bands(points).resting_hr

        self.assertLessEqual(abs(normal.high - 51), 2)

    def test_a_stable_period_does_not_produce_a_hair_trigger_band(self):
        # A year cycling 47..53 bpm: median 50, MAD 2, spread ~2.97.
        points = _points(365, rhr=lambda offset: 47 + offset % 7)
        points.append(
            RecoveryPoint(
                date=D + timedelta(days=365),
                resting_hr=52,
            )
        )

        normal, watch, alert = recovery_bands(points).resting_hr

        # A 2 bpm rise is amber (watch), not above the alert threshold.
        self.assertAlmostEqual(50.0, normal.high)
        self.assertGreater(watch.high, 52.0)
        self.assertGreater(alert.low, 52.0)

    def test_expanding_fallback_uses_old_values(self):
        samples = [
            (D + timedelta(days=offset), 50)
            for offset in range(7)
        ]

        baseline = robust_baseline(samples, D + timedelta(days=400))

        self.assertIsNotNone(baseline)
        self.assertEqual(50, baseline.center)
        self.assertEqual(7, baseline.count)

    def test_expanding_fallback_in_recovery_bands(self):
        points = _points(7, hrv=lambda _offset: 50)
        points.append(
            RecoveryPoint(
                date=D + timedelta(days=400),
                sleep_s=7 * 3600,
            )
        )

        bands = recovery_bands(points)

        self.assertTrue(bands.hrv)
        self.assertAlmostEqual(50.0, bands.hrv[0].low)

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
