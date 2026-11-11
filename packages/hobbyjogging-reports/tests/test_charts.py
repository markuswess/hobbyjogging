import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_report.charts import (
    plot_compare,
    plot_load,
    plot_pace_hr,
    plot_overview,
    plot_recovery,
    plot_subt,
    plot_time,
    plot_vo2max,
    plot_volume,
)
from hobbyjogging_report.model import (
    DistancePoint,
    LoadPoint,
    AverageWindows,
    PaceHrPoint,
    RecoveryPoint,
    RpePoint,
    SubtPoint,
    TimePoint,
    TimeZoneWeek,
    Vo2maxPoint,
    ZoneAveragePoint,
)
from hobbyjogging_report.zone_groups import ZoneGroupPoint, ZoneGroupSeries

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
            ZoneAveragePoint(
                date(2026, 1, 20),
                [1400, 800, 400, 100],
                projected=True,
            ),
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

    def test_time_chart_draws_hard_ewmas_and_the_22_percent_mark(self):
        weeks = [
            TimeZoneWeek(date(2026, 1, 5), [3600, 1800, 900, 300], 0),
            TimeZoneWeek(date(2026, 1, 12), [1800, 1800, 900, 900], 0),
        ]
        time_points = [
            TimePoint(D, 6600, 6000, 6500, 7000),
            TimePoint(date(2026, 1, 12), 5400, 6100, 6500, 6600),
        ]
        hard_points = [
            TimePoint(D, 1200, 1000, 1100, 1150),
            TimePoint(date(2026, 1, 12), 1800, 1100, 1200, 1250),
        ]

        html = plot_time(
            weeks,
            "",
            time_points=time_points,
            hard_points=hard_points,
            as_html=True,
        )

        self.assertIn("hard 7d avg (weekly)", html)
        self.assertIn("hard 42d avg (weekly)", html)
        self.assertIn("hard 182d avg (weekly)", html)
        self.assertIn('"text":"22%"', html)

    def test_time_chart_flips_zones_and_adds_a_share_panel(self):
        weeks = [
            TimeZoneWeek(date(2026, 1, 5), [3600, 1800, 900, 0], 600),
            TimeZoneWeek(date(2026, 1, 12), [1800, 3600, 900, 300], 0),
        ]
        zone_points = [
            ZoneAveragePoint(date(2026, 1, 5), [1200, 900, 300, 0]),
            ZoneAveragePoint(date(2026, 1, 12), [1300, 850, 350, 0]),
        ]

        html = plot_time(
            weeks,
            "",
            zone_points=zone_points,
            zone_window_days=42,
            as_html=True,
        )

        self.assertIn("share of weekly running time", html)
        self.assertIn("42-day EWMA stacked by pace zone", html)
        self.assertIn('"text":"% of week"', html)

        index = html.find("Plotly.newPlot(")
        data, _ = json.JSONDecoder().raw_decode(
            html[html.find("[", index):]
        )
        absolute = [
            trace
            for trace in data
            if trace.get("type") == "bar" and trace.get("yaxis") == "y"
        ]
        percent = [
            trace
            for trace in data
            if trace.get("type") == "bar" and trace.get("yaxis") == "y2"
        ]

        # Bottom to top: unzoned, Z4, Z3, Z2, Z1.
        self.assertEqual(
            ["Unzoned", "Z4", "Z3", "Z2", "Z1"],
            [trace["name"] for trace in absolute],
        )
        self.assertEqual(
            ["Unzoned", "Z4", "Z3", "Z2", "Z1"],
            [trace["name"] for trace in percent],
        )
        self.assertEqual(
            100.0,
            round(sum(trace["y"][0] for trace in percent), 6),
        )


class OverviewChartTests(unittest.TestCase):

    def test_overview_chart_writes_file(self):
        actual_bars = [
            (D, 500.0, 300.0, 0.0),
            (date(2026, 1, 2), 600.0, 0.0, 0.0),
        ]
        planned_bars = [
            (date(2026, 1, 3), 400.0, 200.0, 0.0),
        ]
        series = ZoneGroupSeries(
            points=[
                ZoneGroupPoint(
                    D,
                    500.0,
                    300.0,
                    0.0,
                    0.1,
                    0.1,
                    0.1,
                    0.05,
                    0.05,
                    0.05,
                    0.15,
                    0.15,
                    0.15,
                ),
                ZoneGroupPoint(
                    date(2026, 1, 2),
                    600.0,
                    0.0,
                    0.0,
                    0.2,
                    0.2,
                    0.2,
                    0.1,
                    0.1,
                    0.1,
                    0.2,
                    0.2,
                    0.2,
                ),
            ]
        )
        vo2max = [
            Vo2maxPoint(D, 65.0, 65.0, 65.0),
            Vo2maxPoint(date(2026, 1, 2), 65.5, 65.2, 65.2),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "overview.png"

            result = plot_overview(
                actual_bars,
                planned_bars,
                series,
                str(output),
                start=D,
                end=date(2026, 1, 3),
                today=date(2026, 1, 2),
                vo2max_points=vo2max,
            )

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_chart_can_render_html(self):
        result = plot_load(
            [LoadPoint(D, 50, 40, 45, 48)],
            "",
            as_html=True,
        )

        self.assertIn("Plotly.newPlot", result)


class FixedRangeTests(unittest.TestCase):

    def test_charts_use_stable_axes(self):
        load_html = plot_load(
            [LoadPoint(D, 50, 40, 45, 48)],
            "",
            rpe_points=[RpePoint(D, 3.0, 2.8, 2.9, 3.0)],
            as_html=True,
        )

        self.assertIn('"range":[0,150.0]', load_html)
        self.assertIn('"range":[0,6.0]', load_html)

        volume_html = plot_volume([(D, 60.0)], "", as_html=True)
        self.assertIn('"range":[0,130.0]', volume_html)

        time_html = plot_time(
            [TimeZoneWeek(D, [3600, 1800, 0, 0], 0)],
            "",
            as_html=True,
        )
        self.assertIn('"range":[0,10.0]', time_html)
        self.assertIn('"range":[0,100]', time_html)

    def test_rpe_axis_extends_with_the_load_axis(self):
        html = plot_load(
            [LoadPoint(D, 50, 40, 45, 48)],
            "",
            rpe_points=[RpePoint(D, 7.2, 7.8, 7.2, 7.0)],
            as_html=True,
        )

        # RPE 7.8 rounds up to 8 -> load 0-200, RPE 0-8; gridlines align
        # every 25 load units with one RPE point.
        self.assertIn('"range":[0,200.0]', html)
        self.assertIn('"range":[0,8.0]', html)

    def test_clipped_bars_are_marked(self):
        html = plot_volume([(D, 187.0)], "", as_html=True)

        self.assertIn("clipped above 130 km", html)
        self.assertIn("187.0 km (bar clipped)", html)



class PaceHrChartTests(unittest.TestCase):

    def test_pace_hr_chart_writes_file(self):
        points = [
            PaceHrPoint(D, 300.0, 150.0, "Easy"),
            PaceHrPoint(date(2026, 1, 2), 240.0, 165.0, "Tempo"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pace-hr.png"

            result = plot_pace_hr(points, str(output))

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_pace_hr_chart_uses_speed_with_pace_labels(self):
        html = plot_pace_hr([PaceHrPoint(D, 300.0, 150.0)], "", as_html=True)

        self.assertIn('"range":[2.0,5.2]', html)
        self.assertIn("5:00", html)
        self.assertIn('"range":[90,190]', html)

    def test_pace_hr_chart_draws_half_trends(self):
        points = [
            PaceHrPoint(
                D + timedelta(days=index),
                1000 / (2.5 + 0.1 * index),
                120 + 0.1 * index,
            )
            for index in range(8)
        ]

        html = plot_pace_hr(points, "", as_html=True)

        self.assertIn("first half trend", html)
        self.assertIn("second half trend", html)
        self.assertIn("HR = ", html)

    def test_pace_hr_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_pace_hr([], str(Path(tmp) / "pace-hr.png"))


class CompareChartTests(unittest.TestCase):

    def test_compare_chart_aligns_years_on_a_reference_axis(self):
        series = [
            (2025, [(date(2025, 1, 1), 10.0), (date(2025, 1, 2), 12.0)]),
            (2026, [(date(2026, 1, 1), 20.0)]),
        ]

        html = plot_compare(
            series,
            "",
            metric="volume",
            window=42,
            today=date(2026, 11, 11),
            as_html=True,
        )

        self.assertIn('"name":"2025"', html)
        self.assertIn('"name":"2026"', html)
        self.assertIn("2001-01-01", html)
        self.assertIn("2001-12-31", html)
        self.assertIn("2001-11-11", html)
        self.assertIn("today", html)

    def test_compare_chart_writes_file(self):
        series = [(2026, [(date(2026, 1, 1), 20.0)])]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "compare.png"

            result = plot_compare(
                series,
                str(output),
                metric="load",
                window=7,
                today=date(2026, 1, 2),
            )

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())


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

    def test_recovery_chart_draws_readiness_bands(self):
        points = [
            RecoveryPoint(
                D + timedelta(days=offset),
                hrv=50 + offset % 5,
                resting_hr=48 + offset % 3,
                sleep_s=7 * 3600,
                hrv_avg=50,
                resting_hr_avg=48,
                sleep_avg=7 * 3600,
            )
            for offset in range(60)
        ]

        html = plot_recovery(points, "", as_html=True)

        self.assertIn('"type":"rect"', html)
        self.assertIn("rgba(46, 139, 87", html)
        self.assertIn("rgba(255, 193, 7", html)
        self.assertIn("rgba(220, 53, 69", html)
        self.assertIn("normal", html)
        self.assertIn("alert", html)


class Vo2maxChartTests(unittest.TestCase):

    def test_vo2max_chart_writes_file(self):
        points = [
            Vo2maxPoint(D, 60.0, 59.5, 59.0),
            Vo2maxPoint(date(2026, 1, 2), None, 59.6, 59.1),
            Vo2maxPoint(date(2026, 1, 3), 61.0, 60.0, 59.3),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "vo2max.png"

            result = plot_vo2max(points, str(output))

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_vo2max_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_vo2max([], str(Path(tmp) / "vo2max.png"))


if __name__ == "__main__":
    unittest.main()
