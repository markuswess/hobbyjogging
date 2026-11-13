import json
import math
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_report.charts import (
    PACE_HR_SYMBOLS,
    PB_COLORS,
    _axis_ceiling,
    compare_color,
    plot_compare,
    plot_equipment,
    plot_pb_progressions,
    plot_races,
    plot_compare_pace_hr,
    plot_compare_vo2max,
    plot_load,
    plot_pace_hr,
    plot_overview,
    plot_recovery,
    plot_subt,
    plot_time,
    plot_vo2max,
    plot_volume,
)
from hobbyjogging_report.analysis import (
    EquipmentStat,
    equivalent_times,
    fit_riegel,
    pb_progressions,
    race_results,
    riegel_reference,
    riegel_time,
)
from hobbyjogging_core.model import Activity, Equipment
from hobbyjogging_report.model import (
    DistancePoint,
    LoadPoint,
    AverageWindows,
    PaceHrPoint,
    RecoveryPoint,
    RpePoint,
    SubtPoint,
    TimePoint,
    Vo2maxMeasurement,
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


class AxisCeilingTests(unittest.TestCase):

    def test_empty_sample_falls_back_to_the_floor(self):
        self.assertEqual(20.0, _axis_ceiling([], step=20, floor=20))

    def test_the_ultra_value_is_dropped_before_rounding(self):
        # 60 each week, plus one 188 km week -> 60 -> 66 -> 80
        self.assertEqual(
            80.0,
            _axis_ceiling([60.0] * 12 + [188.0], step=20, floor=20),
        )

    def test_steady_values_only_round_up_to_the_next_step(self):
        self.assertEqual(
            60.0,
            _axis_ceiling([40.0] * 12, step=20, floor=20),
        )
        self.assertEqual(
            20.0,
            _axis_ceiling([2.0, 3.0], step=20, floor=20),
        )

    def test_a_short_sample_cannot_be_trimmed_below_one_value(self):
        self.assertEqual(60.0, _axis_ceiling([52.0], step=20, floor=20))


class AdaptiveAxisTests(unittest.TestCase):
    """The axis follows the bulk; rare extremes are clipped and marked."""

    def test_volume_axis_ignores_one_huge_week(self):
        weeks = [
            (D + timedelta(days=7 * index), 60.0)
            for index in range(12)
        ]
        weeks.append((D + timedelta(days=7 * 12), 188.0))

        html = plot_volume(weeks, "", as_html=True)

        self.assertIn('"range":[0,80.0]', html)
        self.assertIn("clipped above 80 km", html)
        self.assertIn("188.00 km (bar clipped)", html)

    def test_volume_without_outliers_clips_nothing(self):
        weeks = [
            (D + timedelta(days=7 * index), 40.0 + index)
            for index in range(12)
        ]

        html = plot_volume(weeks, "", as_html=True)

        self.assertNotIn("clipped above", html)
        self.assertIn('"range":[0,60.0]', html)

    def test_volume_axis_grows_with_the_sustained_average(self):
        points = [
            DistancePoint(D, 20.0, 15.0, 15.0, 15.0)
            for _ in range(2)
        ]

        html = plot_volume(
            [(D, 40.0)],
            "",
            distance_points=points,
            as_html=True,
        )

        # The bars alone would fit in 60 km; the 182-day line needs the room.
        self.assertIn('"range":[0,120.0]', html)

    def test_time_axis_and_share_panel(self):
        weeks = [
            TimeZoneWeek(D + timedelta(days=7 * index), [3600, 1800, 0, 0])
            for index in range(12)
        ]
        weeks.append(
            TimeZoneWeek(D + timedelta(days=7 * 12), [22.3 * 3600, 0, 0, 0])
        )

        html = plot_time(weeks, "", as_html=True)

        self.assertIn('"range":[0,2.0]', html)
        self.assertIn('"range":[0,100]', html)
        self.assertIn("clipped above 2 h", html)

    def test_load_axis_ignores_the_ultra_day(self):
        points = [
            LoadPoint(D + timedelta(days=index), 40.0, 35.0, 38.0, 40.0)
            for index in range(30)
        ]
        points.append(
            LoadPoint(D + timedelta(days=30), 349.0, 40.0, 42.0, 60.0)
        )

        html = plot_load(points, "", as_html=True)

        self.assertIn('"range":[0,50.0]', html)
        self.assertIn("349.00 load (bar clipped)", html)

    def test_rpe_overlay_gets_its_own_scale(self):
        html = plot_load(
            [LoadPoint(D, 50, 40, 45, 48)],
            "",
            rpe_points=[RpePoint(D, 7.2, 7.8, 7.2, 7.0)],
            as_html=True,
        )

        # The load axis follows the load; the RPE axis covers its own values.
        self.assertIn('"range":[0,75.0]', html)
        self.assertIn('"range":[0,8.0]', html)

    def test_overview_axis_ignores_the_long_day(self):
        actual_bars = [
            (D + timedelta(days=index), 300.0, 200.0, 0.0)
            for index in range(30)
        ]
        actual_bars.append((D + timedelta(days=30), 24 * 3600.0, 0.0, 0.0))
        series = ZoneGroupSeries(
            points=[
                ZoneGroupPoint(
                    date=day,
                    easy_s=300.0,
                    hard_s=200.0,
                    unzoned_s=0.0,
                    easy_7=300.0,
                    easy_42=300.0,
                    easy_182=300.0,
                    hard_7=200.0,
                    hard_42=200.0,
                    hard_182=200.0,
                    total_7=500.0,
                    total_42=500.0,
                    total_182=500.0,
                )
                for day, _, _, _ in actual_bars
            ]
        )

        html = plot_overview(
            actual_bars,
            [],
            series,
            "",
            start=D,
            end=D + timedelta(days=30),
            today=D,
            as_html=True,
        )

        self.assertIn('"range":[0,45.0]', html)
        self.assertIn("clipped above 45 min", html)
        self.assertIn("1440 min (bar clipped)", html)


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
        self.assertIn('"hoverformat":".2f"', html)

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

    def test_pace_hr_chart_draws_efficiency_lines_for_both_halves(self):
        points = [
            PaceHrPoint(
                D + timedelta(days=index),
                1000 / (2.5 + 0.1 * index),
                125 + 3 * index,
                resting_hr=50,
                distance_m=10000,
                excess_beats=5000,
                steady=True,
            )
            for index in range(8)
        ]

        html = plot_pace_hr(points, "", as_html=True)

        self.assertIn("first half efficiency", html)
        self.assertIn("second half efficiency", html)
        self.assertIn("excess beat", html)
        self.assertIn("RHR 50.00 bpm", html)
        self.assertIn("outlined points", html)
        self.assertIn("all runs are shown", html)

    def test_pace_hr_chart_outlines_only_steady_band_points(self):
        points = [
            PaceHrPoint(
                D + timedelta(days=index),
                300.0 - index,
                150.0 + index,
                category="easy",
                steady=index % 2 == 0,
            )
            for index in range(4)
        ]

        html = plot_pace_hr(points, "", as_html=True)

        self.assertIn('"width":[1.2,0,1.2,0]', html)

    def test_pace_hr_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_pace_hr([], str(Path(tmp) / "pace-hr.png"))

    def test_symbol_map_is_fixed(self):
        self.assertEqual(
            {
                "easy": "circle",
                "recovery": "diamond",
                "intervals": "square",
                "longrun": "triangle-up",
                "race": "star",
                "tempo": "cross",
                "fartlek": "pentagon",
                "race-support": "triangle-down",
                "other": "x",
            },
            PACE_HR_SYMBOLS,
        )

    def test_category_symbols_split_the_scatter_into_traces(self):
        points = [
            PaceHrPoint(D, 300.0, 150.0, "Easy", category="easy"),
            PaceHrPoint(D, 290.0, 152.0, "Recovery", category="recovery"),
            PaceHrPoint(D, 240.0, 165.0, "Tempo", category="tempo"),
        ]

        html = plot_pace_hr(points, "", as_html=True)

        self.assertIn('"name":"Easy"', html)
        self.assertIn('"name":"Recovery"', html)
        self.assertIn('"name":"Tempo"', html)
        self.assertIn('"symbol":"circle"', html)
        self.assertIn('"symbol":"diamond"', html)
        self.assertIn('"symbol":"cross"', html)
        # One shared year colorbar across all category traces.
        self.assertEqual(1, html.count('"showscale":true'))
        self.assertEqual(2, html.count('"showscale":false'))

    def test_unknown_category_uses_the_other_symbol(self):
        html = plot_pace_hr(
            [PaceHrPoint(D, 300.0, 150.0, "Mystery", category="unknown")],
            "",
            as_html=True,
        )

        self.assertIn('"name":"Other"', html)
        self.assertIn('"symbol":"x"', html)


class PbProgressionChartTests(unittest.TestCase):

    def _progressions(self):
        activities = [
            Activity(
                id="a",
                date=date(2025, 3, 1),
                type="run",
                distance_m=5000,
                duration_s=1300,
                workout_methods=["race"],
            ),
            Activity(
                id="b",
                date=date(2025, 6, 1),
                type="run",
                distance_m=5000,
                duration_s=1200,
                workout_methods=["race"],
            ),
            Activity(
                id="c",
                date=date(2025, 9, 1),
                type="run",
                distance_m=10000,
                duration_s=2500,
                workout_methods=["race"],
            ),
            Activity(
                id="near",
                date=date(2025, 7, 1),
                type="run",
                distance_m=5000,
                duration_s=1250,
                workout_methods=["race"],
            ),
            Activity(
                id="slow",
                date=date(2025, 8, 1),
                type="run",
                distance_m=5000,
                duration_s=1350,
                workout_methods=["race"],
            ),
            Activity(
                id="trail",
                date=date(2025, 10, 1),
                type="trail_run",
                distance_m=21000,
                duration_s=9000,
                workout_methods=["race"],
            ),
        ]

        return pb_progressions(race_results(activities))

    def test_draws_step_lines_in_pace_with_current_pb_labels(self):
        html = plot_pb_progressions(
            self._progressions(),
            "",
            as_html=True,
        )

        self.assertIn("PB progression", html)
        # Points connect directly, not with step lines.
        self.assertNotIn('"shape":"hv"', html)
        self.assertIn('"mode":"lines+markers"', html)
        self.assertIn('"name":"5k"', html)
        self.assertIn('"name":"10k"', html)
        self.assertNotIn('"name":"Trail"', html)
        # The axis, the end labels and the hover all read in min/km.
        slash = chr(92) + "u002f"
        self.assertIn("5k 4:00" + slash + "km", html)
        self.assertIn("10k 4:10" + slash + "km", html)
        self.assertIn("pace (min" + slash + "km)", html)
        self.assertIn('"ticktext":["4:00","4:05","4:10"', html)
        # 20:00 over 5 km is 240 s/km, not 1200 s on the axis.
        self.assertIn('"y":[260.0,240.0]', html)
        self.assertIn(
            "20:00 " + chr(92) + "u00b7 4:00" + slash + "km",
            html,
        )

    def test_non_pb_races_are_hollow_dots_without_a_line(self):
        html = plot_pb_progressions(
            self._progressions(),
            "",
            as_html=True,
        )
        index = html.find("Plotly.newPlot(")
        data, _ = json.JSONDecoder().raw_decode(
            html[html.find("[", index):]
        )
        others = next(
            trace for trace in data if trace.get("name") == "non-PB races"
        )

        self.assertEqual("markers", others["mode"])
        self.assertEqual("circle-open", others["marker"]["symbol"])
        self.assertEqual([PB_COLORS["5k"]], others["marker"]["color"])
        self.assertNotIn("line", others)
        self.assertEqual(["2025-07-01"], others["x"])
        self.assertIn("20:50", others["text"][0])

    def test_slow_non_pb_races_are_marked_above_the_axis(self):
        html = plot_pb_progressions(
            self._progressions(),
            "",
            as_html=True,
        )
        index = html.find("Plotly.newPlot(")
        data, _ = json.JSONDecoder().raw_decode(
            html[html.find("[", index):]
        )
        above = next(
            trace
            for trace in data
            if trace.get("name") == "1 races above the axis"
        )

        self.assertEqual("triangle-up", above["marker"]["symbol"])
        self.assertEqual([PB_COLORS["5k"]], above["marker"]["color"])
        self.assertEqual(["2025-08-01"], above["x"])
        self.assertIn("4:30/km, above the axis", above["hovertext"][0])

    def test_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pb.png"

            result = plot_pb_progressions(
                self._progressions(),
                str(output),
            )

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_empty_progressions_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_pb_progressions(
                    [],
                    str(Path(tmp) / "pb.png"),
                )


class RaceChartTests(unittest.TestCase):

    def test_race_chart_shows_points_and_riegel_fit(self):
        activities = [
            Activity(
                id=str(index),
                date=D + timedelta(days=index),
                type="run",
                distance_m=distance,
                duration_s=distance / 1000 * 300,
                workout_methods=["race"],
                workout_targets=["speed"],
            )
            for index, distance in enumerate((5000, 10000, 21097))
        ]
        results = race_results(activities)
        fit = fit_riegel(results)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "races.png"
            result = plot_races(results, fit, str(output))

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

        html = plot_races(results, fit, "", as_html=True)
        self.assertIn("Riegel", html)
        self.assertIn('"type":"log"', html)

    def test_race_chart_draws_the_prediction_line_through_the_reference(self):
        activities = [
            Activity(
                id=label,
                date=D + timedelta(days=index),
                type="run",
                distance_m=distance,
                duration_s=duration,
                workout_methods=["race"],
                workout_targets=["speed"],
            )
            for index, (label, distance, duration) in enumerate(
                (
                    ("5k", 5000, 1200),
                    ("10k", 10000, 2500),
                    ("HM", 21097, 5600),
                )
            )
        ]
        results = race_results(activities)
        fit = fit_riegel(results)
        reference = riegel_reference(results)

        html = plot_races(results, fit, "", as_html=True)
        index = html.find("Plotly.newPlot(")
        data, _ = json.JSONDecoder().raw_decode(
            html[html.find("[", index):]
        )
        line = next(
            trace
            for trace in data
            if trace.get("name")
            == f"Riegel from {reference.activity.date}"
        )
        marker = next(
            trace for trace in data if trace.get("name") == "reference race"
        )

        self.assertEqual(
            [reference.activity.distance_m / 1000],
            marker["x"],
        )
        self.assertAlmostEqual(
            reference.activity.duration_s / 60,
            marker["y"][0],
        )

        low = min(result.activity.distance_m for result in results)
        high = max(result.activity.distance_m for result in results)
        self.assertEqual([low / 1000, high / 1000], line["x"])
        self.assertAlmostEqual(
            riegel_time(reference, fit, low) / 60,
            line["y"][0],
        )

        # The drawn line is the table: same value at every standard distance.
        slope = math.log(line["y"][1] / line["y"][0]) / math.log(
            line["x"][1] / line["x"][0]
        )

        for row in equivalent_times(results, fit):
            distance_km = row.distance_m / 1000
            on_line = line["y"][0] * (
                distance_km / line["x"][0]
            ) ** slope
            self.assertAlmostEqual(row.predicted_s / 60, on_line)


class EquipmentChartTests(unittest.TestCase):

    def test_equipment_chart_writes_and_marks_targets(self):
        stats = [
            EquipmentStat(
                equipment=Equipment(
                    id="shoe-1",
                    type="shoe",
                    name="Demo Shoe",
                    acquired_on=D,
                ),
                sessions=2,
                distance_m=700000,
                target_distance_m=800000,
            ),
            EquipmentStat(
                equipment=Equipment(
                    id="shoe-2",
                    type="shoe",
                    name="Retired Shoe",
                    retired_on=D,
                ),
                sessions=3,
                distance_m=1200000,
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "gear.png"
            result = plot_equipment(stats, str(output))

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

        html = plot_equipment(stats, "", as_html=True)
        self.assertIn("target", html)
        self.assertIn("Demo Shoe", html)

    def test_equipment_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_equipment([], str(Path(tmp) / "gear.png"))


class CompareVo2maxChartTests(unittest.TestCase):

    def test_raw_values_are_grouped_by_year_without_averaging(self):
        measurements = [
            Vo2maxMeasurement(date(2025, 6, 1), 54.2),
            Vo2maxMeasurement(date(2025, 6, 2), 54.2),
            Vo2maxMeasurement(date(2026, 6, 1), 55.1),
        ]

        html = plot_compare_vo2max(measurements, "", as_html=True)

        self.assertIn('"name":"2025"', html)
        self.assertIn('"name":"2026"', html)
        self.assertIn("Garmin running VO2max by year", html)
        self.assertIn('"y":[54.2,54.2]', html)
        self.assertIn('"y":[55.1]', html)
        self.assertIn('"mode":"lines"', html)

    def test_empty_measurements_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_compare_vo2max(
                    [],
                    str(Path(tmp) / "compare-vo2max.png"),
                )


class ComparePaceHrChartTests(unittest.TestCase):

    def test_groups_points_by_year_with_one_trace_per_year(self):
        points = [
            PaceHrPoint(D + timedelta(days=index), 300.0, 150.0)
            for index in range(2)
        ]
        points += [
            PaceHrPoint(date(2025, 6, 1), 280.0, 155.0),
            PaceHrPoint(date(2025, 7, 1), 275.0, 158.0),
        ]

        html = plot_compare_pace_hr(points, "", as_html=True)

        self.assertIn('"name":"2026"', html)
        self.assertIn('"name":"2025"', html)
        self.assertIn('"range":[2.0,5.2]', html)
        self.assertIn("Pace vs heart rate by year", html)
        self.assertEqual(0, html.count('"visible":"legendonly"'))

    def test_only_the_last_five_years_are_visible_by_default(self):
        points = [
            PaceHrPoint(date(year, 6, 1), 300.0, 150.0)
            for year in range(2018, 2027)
        ]

        html = plot_compare_pace_hr(points, "", as_html=True)

        self.assertEqual(4, html.count('"visible":"legendonly"'))
        for year in range(2018, 2027):
            self.assertIn(f'"name":"{year}"', html)

    def test_empty_points_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_compare_pace_hr(
                    [],
                    str(Path(tmp) / "compare-pace-hr.png"),
                )

    def test_marker_symbols_follow_each_point_category(self):
        points = [
            PaceHrPoint(D, 300.0, 150.0, "Easy", category="easy"),
            PaceHrPoint(D, 290.0, 152.0, "Tempo", category="tempo"),
            PaceHrPoint(D, 280.0, 155.0, "Mystery", category="unknown"),
            PaceHrPoint(date(2025, 6, 1), 300.0, 150.0, "Race",
                        category="race"),
        ]

        html = plot_compare_pace_hr(points, "", as_html=True)

        self.assertIn('"symbol":["circle","cross","x"]', html)
        self.assertIn('"symbol":["star"]', html)
        self.assertIn("all runs; colour = calendar year", html)


class CompareChartTests(unittest.TestCase):

    def test_compare_color_is_anchored_on_a_fixed_year(self):
        self.assertEqual("#1f77b4", compare_color(2009))
        self.assertNotEqual(compare_color(2009), compare_color(2026))
        self.assertEqual(compare_color(2023), compare_color(2023))

    def test_all_compare_charts_share_one_year_color(self):
        year = 2023
        color = compare_color(year)

        pace_hr = plot_compare_pace_hr(
            [
                PaceHrPoint(date(2019, 6, 1), 300.0, 150.0),
                PaceHrPoint(date(year, 6, 1), 300.0, 150.0),
            ],
            "",
            as_html=True,
        )
        vo2max = plot_compare_vo2max(
            [Vo2maxMeasurement(date(year, 6, 1), 54.0)],
            "",
            as_html=True,
        )
        ewma = plot_compare(
            [
                (2020, [(date(2020, 1, 1), 8.0)]),
                (year, [(date(year, 1, 1), 10.0)]),
            ],
            "",
            metric="volume",
            window=42,
            today=date(year, 12, 31),
            as_html=True,
        )

        for html in (pace_hr, vo2max, ewma):
            self.assertIn(f'"color":"{color}"', html)

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
        self.assertIn('"y":-0.07', html)
        self.assertIn('"yanchor":"top"', html)

    def test_compare_chart_draws_dashed_planned_lines(self):
        series = [
            (2026, [(date(2026, 1, 1), 10.0), (date(2026, 1, 2), 12.0)])
        ]
        planned = [
            (2026, [(date(2026, 1, 1), 8.0), (date(2026, 1, 2), 9.0)])
        ]

        html = plot_compare(
            series,
            "",
            metric="volume",
            window=42,
            today=date(2026, 11, 11),
            planned_series=planned,
            as_html=True,
        )

        self.assertIn('"name":"2026 planned"', html)
        self.assertIn('"dash":"dash"', html)
        self.assertIn('"y":[56.0,63.0]', html)

    def test_compare_chart_hides_older_years_in_the_legend(self):
        series = [
            (year, [(date(year, 1, 1), float(year - 2000))])
            for year in range(2018, 2027)
        ]

        html = plot_compare(
            series,
            "",
            metric="volume",
            window=42,
            today=date(2026, 11, 11),
            as_html=True,
        )

        self.assertEqual(4, html.count('"visible":"legendonly"'))
        for year in range(2018, 2027):
            self.assertIn(f'"name":"{year}"', html)

    def test_compare_chart_efficiency_axis_names_the_steady_band(self):
        html = plot_compare(
            [(2026, [(date(2026, 1, 1), 2.0)])],
            "",
            metric="efficiency",
            window=42,
            today=date(2026, 11, 11),
            as_html=True,
        )

        self.assertIn("excess beat", html)
        self.assertIn("steady 45", html)

    def test_compare_chart_time_axis_is_weekly_hours(self):
        series = [
            (
                2026,
                [(date(2026, 1, 1), 1.5), (date(2026, 1, 2), 2.0)],
            )
        ]

        html = plot_compare(
            series,
            "",
            metric="time",
            window=42,
            today=date(2026, 11, 11),
            as_html=True,
        )

        self.assertIn("hours \\u002f week", html)
        self.assertIn('"y":[10.5,14.0]', html)

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

    def test_recovery_chart_axis_matches_the_points(self):
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
                date(2026, 1, 3),
                hrv=55,
                resting_hr=46,
                sleep_s=8 * 3600,
                hrv_avg=52.5,
                resting_hr_avg=45.5,
                sleep_avg=7.5 * 3600,
            ),
        ]

        html = plot_recovery(points, "", as_html=True)

        self.assertIn('"range":["2026-01-01","2026-01-03"]', html)

    def test_recovery_chart_axis_keeps_planned_dates_visible(self):
        points = [
            RecoveryPoint(
                D,
                hrv=50,
                resting_hr=45,
                sleep_s=7 * 3600,
                hrv_avg=50,
                resting_hr_avg=45,
                sleep_avg=7 * 3600,
            )
        ]

        html = plot_recovery(
            points,
            "",
            planned_dates=[date(2026, 1, 10)],
            as_html=True,
        )

        self.assertIn('"range":["2026-01-01","2026-01-10"]', html)

    def test_recovery_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_recovery([], str(Path(tmp) / "recovery.png"))

    def test_recovery_chart_bands_use_the_baseline_points(self):
        display = [
            RecoveryPoint(
                D + timedelta(days=offset),
                hrv=60,
                resting_hr=60,
                sleep_s=7 * 3600,
                hrv_avg=60,
                resting_hr_avg=60,
                sleep_avg=7 * 3600,
            )
            for offset in range(30)
        ]
        baseline = [
            RecoveryPoint(
                D + timedelta(days=offset),
                hrv=50,
                resting_hr=50,
            )
            for offset in range(365)
        ]

        html = plot_recovery(
            display,
            "",
            as_html=True,
            baseline_points=baseline,
        )

        # The HRV normal band starts at the 365-day median (50), not at
        # the displayed values' centre (60).
        self.assertIn('"y0":50.0', html)

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
