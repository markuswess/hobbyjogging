import tempfile
import unittest
from datetime import date
from pathlib import Path

from hobbyjogging_report.charts import (
    plot_load,
    plot_recovery,
    plot_subt,
    plot_time,
    plot_volume,
)
from hobbyjogging_report.model import (
    DistancePoint,
    LoadPoint,
    AverageWindows,
    RecoveryPoint,
    SubtPoint,
    TimePoint,
    TimeZoneWeek,
    ZoneAveragePoint,
)

D = date(2026, 1, 1)

POINTS = [
    SubtPoint(
        D, "short", 220, avg_hr=160, max_hr=172,
        fastest_pace_s_per_km=210, slowest_pace_s_per_km=230,
    ),
    SubtPoint(
        date(2026, 1, 2), "short", 225, avg_hr=None, max_hr=170,
        fastest_pace_s_per_km=215, slowest_pace_s_per_km=235,
    ),
    SubtPoint(
        date(2026, 1, 3), "medium", 230, avg_hr=158, max_hr=170,
        fastest_pace_s_per_km=220, slowest_pace_s_per_km=245,
    ),
    SubtPoint(
        date(2026, 1, 4), "long", 240, avg_hr=150, max_hr=164,
        fastest_pace_s_per_km=230, slowest_pace_s_per_km=255,
    ),
    SubtPoint(
        date(2026, 1, 5), "lt1", 245, avg_hr=145, max_hr=160,
        fastest_pace_s_per_km=235, slowest_pace_s_per_km=260,
    ),
]


class SubtChartTests(unittest.TestCase):

    def test_combined_pace_and_hr_chart_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "subt.png"

            result = plot_subt(POINTS, str(output))

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_combined_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_subt([], str(Path(tmp) / "subt.png"))


class VolumeChartTests(unittest.TestCase):

    def test_volume_chart_with_distance_averages(self):
        data = [
            (date(2026, 1, 5), 30.0),
            (date(2026, 1, 12), 40.0),
        ]
        distance_points = [
            DistancePoint(D, 8.0, 7.0, 7.5, 7.8),
            DistancePoint(date(2026, 1, 2), 10.0, 7.1, 7.8, 8.2),
            DistancePoint(
                date(2026, 1, 20),
                0.0,
                7.2,
                7.6,
                7.9,
                projected=True,
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "volume.png"

            result = plot_volume(
                data,
                str(output),
                distance_points=distance_points,
                planned_distance=[
                    (date(2026, 1, 5), 45.0),
                    (date(2026, 1, 12), 50.0),
                    (date(2026, 1, 19), 55.0),
                ],
                windows=AverageWindows(),
            )

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_volume_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_volume([], str(Path(tmp) / "volume.png"))


class TimeChartTests(unittest.TestCase):

    def test_time_chart_writes_file(self):
        weeks = [
            TimeZoneWeek(
                date(2026, 1, 5),
                [3600, 1800, 0, 0],
                600,
            ),
            TimeZoneWeek(
                date(2026, 1, 12),
                [1800, 3600, 900, 0],
                0,
            ),
        ]
        points = [
            TimePoint(D, 7200, 6000, 6500, 7000),
            TimePoint(date(2026, 1, 2), 5400, 6100, 6500, 6600),
            TimePoint(
                date(2026, 1, 20),
                0,
                6100,
                6550,
                6650,
                projected=True,
            ),
        ]
        zone_points = [
            ZoneAveragePoint(D, [1200, 900, 300, 0]),
            ZoneAveragePoint(date(2026, 1, 2),  [1300, 850, 350, 0]),
        ]
        planned_zone_weeks = [
            TimeZoneWeek(
                date(2026, 1, 19),
                [3600, 1800, 900, 0],
            ),
            TimeZoneWeek(
                date(2026, 1, 26),
                [1800, 0, 0, 0],
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "time.png"

            result = plot_time(
                weeks,
                str(output),
                time_points=points,
                planned_time=[
                    (date(2026, 1, 5), 7200),
                    (date(2026, 1, 12), 8100),
                    (date(2026, 1, 19), 9000),
                ],
                planned_zone_weeks=planned_zone_weeks,
                zone_points=zone_points,
                zone_window_days=42,
                windows=AverageWindows(),
            )

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_time_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_time([], str(Path(tmp) / "time.png"))


class LoadChartTests(unittest.TestCase):

    def test_load_chart_writes_file(self):
        points = [
            LoadPoint(D, 50, 40, 45, 48),
            LoadPoint(date(2026, 1, 2), 80, 41, 50, 55),
            LoadPoint(date(2026, 1, 3), 0, 40, 48, 47),
            LoadPoint(date(2026, 1, 5), 60, 41, 50, 52, projected=True),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "load.png"

            result = plot_load(
                points,
                str(output),
                planned_load=[
                    (D, 55),
                    (date(2026, 1, 2), 70),
                    (date(2026, 1, 4), 60),
                ],
                windows=AverageWindows(base=182, fitness=42, fatigue=7),
            )

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_load_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_load([], str(Path(tmp) / "load.png"))


class RecoveryChartTests(unittest.TestCase):

    def test_recovery_chart_writes_file(self):
        points = [
            RecoveryPoint(
                D,
                hrv=50,
                resting_hr=45,
                sleep_s=7 * 3600,
                hrv_avg=50,
                resting_hr_avg=45,
                sleep_avg=7 * 3600,
            ),
            RecoveryPoint(
                date(2026, 1, 2),
                hrv=55,
                resting_hr=46,
                sleep_s=8 * 3600,
                hrv_avg=52.5,
                resting_hr_avg=45.5,
                sleep_avg=7.5 * 3600,
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "recovery.png"

            result = plot_recovery(
                points,
                str(output),
                planned_dates=[D, date(2026, 1, 2)],
                window_days=7,
            )

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_recovery_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_recovery([], str(Path(tmp) / "recovery.png"))


if __name__ == "__main__":
    unittest.main()
