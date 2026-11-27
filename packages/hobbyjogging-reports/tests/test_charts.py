import json
import math
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_report.charts import (
    PACE_HR_SPEED_RANGE,
    PACE_HR_SYMBOLS,
    PB_COLORS,
    _axis_ceiling,
    compare_color,
    plot_compare,
    plot_equipment,
    plot_gear_mileage,
    plot_pb_progressions,
    plot_races,
    plot_compare_pace_hr,
    plot_compare_vo2max,
    plot_devices,
    plot_load,
    plot_pace_hr,
    plot_overview,
    plot_recovery,
    plot_subt,
    plot_thresholds,
    plot_time,
    plot_vo2max_methods,
    plot_volume,
    plot_weight,
)
from hobbyjogging_report.analysis import (
    DeviceStat,
    EquipmentStat,
    GearDetail,
    RacePacePoint,
    ThresholdPoint,
    equivalent_times,
    fit_riegel,
    official_by_activity,
    pb_progressions,
    race_results,
    riegel_reference,
    riegel_time,
)
from hobbyjogging_report.model import WeightPoint
from hobbyjogging_core.model import (
    Activity,
    Device,
    Equipment,
    RaceResult as OfficialRaceResult,
)
from hobbyjogging_core.model import ActivityWeather, TrainingPeriod
from hobbyjogging_report.model import (
    DistancePoint,
    LoadPoint,
    AverageWindows,
    PaceHrPoint,
    RecoveryPoint,
    RpePoint,
    SubtPoint,
    TimePoint,
    GarminVo2maxDevice,
    TimeZoneWeek,
    Vo2maxMeasurement,
    Vo2maxMethods,
    Vo2maxPoint,
    ZoneAveragePoint,
)
from hobbyjogging_report.zone_groups import ZoneGroupPoint, ZoneGroupSeries

D = date(2026, 1, 1)


def plotly_data(html):
    """The data array from a rendered plotly figure."""
    index = html.index("Plotly.newPlot(")
    data, _ = json.JSONDecoder().raw_decode(
        html[html.index("[", index):]
    )
    return data


def plotly_layout(html):
    """The layout object from a rendered plotly figure."""
    index = html.index("Plotly.newPlot(")
    start = html.index("[", index)
    _, consumed = json.JSONDecoder().raw_decode(html[start:])
    rest = html[start + consumed:]
    layout, _ = json.JSONDecoder().raw_decode(
        rest[rest.index("{"):]
    )
    return layout


def hoverable_unnamed(data):
    """Traces the unified hover would label "trace N"."""
    return [
        trace
        for trace in data
        if (trace.get("x") or [])
        and not trace.get("name")
        and trace.get("hoverinfo") not in ("skip", "none")
    ]


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


class PeriodBandTests(unittest.TestCase):

    def test_volume_shades_only_seasons_behind_the_bars(self):
        data = [
            (date(2026, 1, 5), 30.0),
            (date(2026, 1, 12), 40.0),
        ]
        periods = [
            TrainingPeriod(
                id="s",
                kind="season",
                label="Base",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 2, 1),
            ),
            TrainingPeriod(
                id="i",
                kind="illness",
                label="Sick",
                start_date=date(2026, 1, 6),
                end_date=date(2026, 1, 8),
            ),
        ]

        html = plot_volume(data, "", periods=periods, as_html=True)
        traces = plotly_data(html)
        bands = [trace for trace in traces if trace.get("hoveron") == "fills"]

        self.assertEqual(1, len(bands))
        band = bands[0]
        # Clamped to the visible weeks, while the hover keeps the real span.
        self.assertEqual(
            [
                "2026-01-05",
                "2026-01-05",
                "2026-01-20",
                "2026-01-20",
            ],
            band["x"],
        )
        self.assertEqual("rgba(46, 139, 87, 0.07)", band["fillcolor"])
        self.assertIn("Base: 2026-01-01", band["text"])
        self.assertLess(
            traces.index(band),
            next(
                index
                for index, trace in enumerate(traces)
                if trace.get("name") == "weekly km"
            ),
        )
        self.assertIn('"text":"Base"', html)

    def test_one_day_period_is_a_thin_band_and_others_are_filtered(self):
        data = [(date(2026, 1, 5), 30.0)]
        periods = [
            TrainingPeriod(
                id="one",
                kind="season",
                label="One day",
                start_date=date(2026, 1, 6),
                end_date=date(2026, 1, 6),
            ),
            TrainingPeriod(
                id="old",
                kind="season",
                label="Old",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 2, 1),
            ),
        ]

        html = plot_volume(data, "", periods=periods, as_html=True)
        bands = [
            trace
            for trace in plotly_data(html)
            if trace.get("hoveron") == "fills"
        ]

        self.assertEqual(1, len(bands))
        first = date.fromisoformat(bands[0]["x"][0])
        right = date.fromisoformat(bands[0]["x"][2])
        self.assertEqual(1, (right - first).days)
        self.assertNotIn("Old", html)

    def test_load_shades_seasons_with_their_label(self):
        points = [
            LoadPoint(D + timedelta(days=index), 40.0, 35.0, 38.0, 40.0)
            for index in range(7)
        ]
        periods = [
            TrainingPeriod(
                id="s",
                kind="season",
                label="Marathon build",
                start_date=D,
                end_date=D + timedelta(days=6),
            )
        ]

        html = plot_load(points, "", periods=periods, as_html=True)
        bands = [
            trace
            for trace in plotly_data(html)
            if trace.get("hoveron") == "fills"
        ]

        self.assertEqual(1, len(bands))
        self.assertIn("Marathon build:", bands[0]["text"])
        self.assertIn('"text":"Marathon build"', html)
        marker = next(
            shape
            for shape in plotly_layout(html).get("shapes", [])
            if shape.get("type") == "line"
            and shape.get("x0") == "2026-01-01"
        )
        self.assertEqual("below", marker["layer"])

    def test_a_season_start_is_marked_with_a_faint_line(self):
        data = [
            (date(2026, 1, 5), 30.0),
            (date(2026, 1, 12), 40.0),
        ]
        periods = [
            TrainingPeriod(
                id="s",
                kind="season",
                label="Base",
                start_date=date(2026, 1, 12),
                end_date=date(2026, 2, 1),
            )
        ]

        html = plot_volume(data, "", periods=periods, as_html=True)
        shapes = plotly_layout(html).get("shapes", [])
        marker = next(
            shape
            for shape in shapes
            if shape.get("type") == "line"
            and shape.get("x0") == "2026-01-12"
            and shape.get("x0") == shape.get("x1")
        )

        self.assertEqual("below", marker["layer"])
        self.assertEqual("dot", marker["line"]["dash"])
        self.assertEqual(
            "rgba(46, 139, 87, 0.35)",
            marker["line"]["color"],
        )

    def test_a_season_started_before_the_window_is_not_marked(self):
        data = [(date(2026, 1, 5), 30.0)]
        periods = [
            TrainingPeriod(
                id="s",
                kind="season",
                label="Old",
                start_date=date(2025, 1, 1),
                end_date=date(2026, 2, 1),
            )
        ]

        html = plot_volume(data, "", periods=periods, as_html=True)
        shapes = plotly_layout(html).get("shapes", [])

        self.assertFalse(
            [
                shape
                for shape in shapes
                if shape.get("x0") == "2025-01-01"
            ]
        )

    def test_recovery_shades_illness_on_every_panel(self):
        points = [
            RecoveryPoint(
                D + timedelta(days=index),
                hrv=50.0 + index,
                resting_hr=50.0,
                sleep_s=7.5 * 3600,
                hrv_avg=50.0 + index,
                resting_hr_avg=50.0,
                sleep_avg=7.5 * 3600,
            )
            for index in range(5)
        ]
        periods = [
            TrainingPeriod(
                id="i",
                kind="illness",
                label="Injury",
                start_date=D + timedelta(days=1),
                end_date=D + timedelta(days=2),
            )
        ]

        html = plot_recovery(points, "", periods=periods, as_html=True)
        bands = [
            trace
            for trace in plotly_data(html)
            if trace.get("hoveron") == "fills"
        ]

        self.assertEqual(3, len(bands))
        self.assertTrue(
            all("Injury: " in band["text"] for band in bands)
        )
        # Illness bands carry no quiet label, only the hover.
        self.assertNotIn('"text":"Injury"', html)

    def test_charts_are_unchanged_without_periods(self):
        html = plot_volume(
            [(date(2026, 1, 5), 30.0)],
            "",
            as_html=True,
        )

        self.assertNotIn('"hoveron":"fills"', html)


class SubtChartTests(unittest.TestCase):

    def test_combined_pace_and_hr_chart_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "subt.png"

            result = plot_subt(POINTS, str(output))

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_efficiency_panel_shows_the_rep_range(self):
        points = [
            SubtPoint(
                D + timedelta(days=index),
                "short",
                220,
                count=5,
                efficiency=2.0 + index * 0.05,
                lowest_efficiency=1.8 + index * 0.05,
                highest_efficiency=2.2 + index * 0.05,
            )
            for index in range(4)
        ]

        html = plot_subt(points, "", as_html=True)

        # Range sticks and the dot's hover, but no extra trend lines.
        self.assertIn("reps 1.80", html)
        self.assertIn("n=5", html)
        self.assertNotIn('"dash"', html)

    def test_efficiency_axis_follows_the_bulk_not_one_extreme_rep(self):
        points = [
            SubtPoint(
                D + timedelta(days=index),
                "short",
                220,
                efficiency=2.5,
                lowest_efficiency=2.4,
                highest_efficiency=2.6,
            )
            for index in range(10)
        ]
        points[0] = SubtPoint(
            D,
            "short",
            220,
            efficiency=2.5,
            lowest_efficiency=2.4,
            highest_efficiency=9.0,
        )

        html = plot_subt(points, "", as_html=True)

        index = html.index("Plotly.newPlot(")
        bracket = html.index("[", index)
        _data, end = json.JSONDecoder().raw_decode(html[bracket:])
        brace = html.index("{", bracket + end)
        layout, _ = json.JSONDecoder().raw_decode(html[brace:])

        low, high = layout["yaxis3"]["range"]
        self.assertGreaterEqual(low, 2.0)
        self.assertLess(high, 3.0)

    def test_every_hoverable_trace_is_named(self):
        html = plot_subt(POINTS, "", as_html=True)

        self.assertEqual([], hoverable_unnamed(plotly_data(html)))

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

    def test_planned_weeks_stack_on_the_actual_and_use_the_hatch(self):
        data = [(date(2026, 1, 5), 30.0)]
        distance_points = [DistancePoint(D, 8.0, 7.0, 7.5, 7.8)]

        html = plot_volume(
            data,
            "",
            distance_points=distance_points,
            planned_distance=[
                (date(2026, 1, 5), 12.0),
                (date(2026, 1, 12), 45.0),
            ],
            as_html=True,
        )

        self.assertIn('"name":"planned km"', html)
        # The current week's plan sits on top of its actual bar.
        self.assertIn('"base":[30.0,0.0]', html)
        self.assertIn('"fgcolor":"#9aa5b1"', html)
        self.assertIn('"solidity":0.45', html)
        self.assertIn('"barmode":"overlay"', html)

    def test_average_lines_get_the_pale_halo_before_the_lines(self):
        distance_points = [
            DistancePoint(D + timedelta(days=index), 8.0, 7.0, 7.5, 7.8)
            for index in range(3)
        ]

        html = plot_volume(
            [(D, 30.0)],
            "",
            distance_points=distance_points,
            as_html=True,
        )

        halo = "rgba(255, 255, 255, 0.85)"
        self.assertGreaterEqual(html.count(halo), 3)
        self.assertLess(html.index(halo), html.index('"name":"7d avg'))

    def test_average_lines_use_the_shared_line_scheme(self):
        distance_points = [
            DistancePoint(D + timedelta(days=index), 8.0, 7.0, 7.5, 7.8)
            for index in range(3)
        ]

        html = plot_volume(
            [(D, 30.0)],
            "",
            distance_points=distance_points,
            as_html=True,
        )

        self.assertIn('"name":"7d avg (weekly)"', html)
        self.assertIn('"name":"42d avg (weekly)"', html)
        self.assertIn('"name":"182d avg (weekly)"', html)
        self.assertIn('"dash":"dash"', html)
        self.assertIn('"dash":"dashdot"', html)
        # Shortest window first, so the smoothest line ends up on top.
        self.assertLess(
            html.index('"name":"7d avg (weekly)"'),
            html.index('"name":"42d avg (weekly)"'),
        )
        self.assertLess(
            html.index('"name":"42d avg (weekly)"'),
            html.index('"name":"182d avg (weekly)"'),
        )

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

    def test_current_week_plan_stacks_on_the_actual_time(self):
        week = date(2026, 1, 5)
        weeks = [TimeZoneWeek(week, [1800, 1800, 0, 0], 0)]
        points = [TimePoint(D, 3600, 3000, 3200, 3300)]
        planned = [TimeZoneWeek(week, [3600, 0, 0, 0])]

        html = plot_time(
            weeks,
            "",
            time_points=points,
            planned_zone_weeks=planned,
            windows=AverageWindows(),
            as_html=True,
        )

        index = html.index("Plotly.newPlot(")
        data, _ = json.JSONDecoder().raw_decode(
            html[html.index("[", index):]
        )
        stacked = [
            trace
            for trace in data
            if trace.get("type") == "bar"
            and trace.get("base") == [1.0]
        ]

        self.assertTrue(stacked)

    def test_zones_stack_hard_done_hard_planned_easy_done_easy_planned(self):
        week = date(2026, 1, 5)
        weeks = [TimeZoneWeek(week, [3600, 3600, 3600, 3600], 0)]
        planned = [TimeZoneWeek(week, [3600, 3600, 3600, 3600])]
        points = [TimePoint(D, 3600, 3000, 3200, 3300)]

        html = plot_time(
            weeks,
            "",
            time_points=points,
            planned_zone_weeks=planned,
            windows=AverageWindows(),
            as_html=True,
        )

        index = html.index("Plotly.newPlot(")
        data, _ = json.JSONDecoder().raw_decode(
            html[html.index("[", index):]
        )
        bars = [
            trace
            for trace in data
            if trace.get("type") == "bar"
            and trace.get("yaxis") == "y"
            and trace.get("x") == [week.isoformat()]
            and trace.get("base")
        ]

        self.assertEqual(
            [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
            [trace["base"][0] for trace in bars],
        )

    def test_the_projected_zone_area_is_transparent(self):
        weeks = [TimeZoneWeek(date(2026, 1, 5), [3600, 1800, 0, 0], 0)]
        points = [TimePoint(D, 7200, 6000, 6500, 7000)]
        zone_points = [
            ZoneAveragePoint(D, [1200, 900, 300, 0]),
            ZoneAveragePoint(
                date(2026, 1, 20),
                [1400, 800, 400, 100],
                projected=True,
            ),
        ]

        html = plot_time(
            weeks,
            "",
            time_points=points,
            zone_points=zone_points,
            zone_window_days=42,
            windows=AverageWindows(),
            as_html=True,
        )

        self.assertIn('"stackgroup":"projected"', html)
        self.assertIn('"opacity":0.35', html)

    def test_share_panel_carries_the_planned_zones(self):
        weeks = [TimeZoneWeek(date(2026, 1, 5), [3600, 1800, 0, 0], 0)]
        points = [TimePoint(D, 7200, 6000, 6500, 7000)]
        planned = [
            TimeZoneWeek(date(2026, 1, 19), [3600, 1800, 900, 0]),
        ]

        html = plot_time(
            weeks,
            "",
            time_points=points,
            planned_zone_weeks=planned,
            windows=AverageWindows(),
            as_html=True,
        )

        index = html.index("Plotly.newPlot(")
        data, _ = json.JSONDecoder().raw_decode(
            html[html.index("[", index):]
        )
        planned_shares = [
            trace
            for trace in data
            if trace.get("type") == "bar"
            and trace.get("yaxis") == "y2"
            and str(trace.get("marker", {}).get("color", "")).startswith(
                "rgba("
            )
        ]

        self.assertEqual(4, len(planned_shares))

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
        self.assertIn(
            "hard minutes " + chr(92) + "u002f week",
            html,
        )

        index = html.index("Plotly.newPlot(")
        data, end = json.JSONDecoder().raw_decode(
            html[html.index("[", index):]
        )
        hard = [
            trace
            for trace in data
            if str(trace.get("name", "")).startswith("hard ")
        ]

        self.assertTrue(hard)
        self.assertTrue(
            all(trace.get("yaxis") == "y3" for trace in hard)
        )
        # 1000 s/week of hard running is 116.7 minutes, not 1.94 hours.
        self.assertIn("116.66", html)

        layout, _ = json.JSONDecoder().raw_decode(
            html[html.find("{", index + end):]
        )
        hours = layout["yaxis"]["range"]
        minutes = layout["yaxis3"]["range"]

        # The minutes axis mirrors the hour axis rather than zooming to the
        # hard series, so a line and a bar of the same duration sit at the
        # same height.
        self.assertEqual([0, hours[1] * 60], minutes)
        self.assertEqual(120.0, layout["yaxis3"]["dtick"])
        self.assertFalse(layout["yaxis3"]["showgrid"])
        self.assertAlmostEqual(
            hard[0]["y"][0] / minutes[1],
            hard[0]["y"][0] / 60 / hours[1],
        )

    def test_hard_ewmas_project_through_the_plan(self):
        weeks = [TimeZoneWeek(date(2026, 1, 5), [3600, 1800, 900, 0], 0)]
        hard = [
            TimePoint(D, 1200, 1000, 1100, 1150),
            TimePoint(
                date(2026, 1, 12),
                1800,
                1100,
                1200,
                1250,
                projected=True,
            ),
        ]

        html = plot_time(weeks, "", hard_points=hard, as_html=True)

        self.assertIn("hard projection", html)

        index = html.index("Plotly.newPlot(")
        data, _ = json.JSONDecoder().raw_decode(
            html[html.index("[", index):]
        )
        projected = [
            trace
            for trace in data
            if trace.get("yaxis") == "y3"
            and trace.get("opacity") == 0.55
            and trace.get("line", {}).get("dash") == "dash"
        ]

        self.assertEqual(3, len(projected))
        self.assertTrue(
            all(len(trace["x"]) == 2 for trace in projected)
        )

    def test_every_hoverable_trace_is_named(self):
        week = date(2026, 1, 5)
        weeks = [TimeZoneWeek(week, [3600, 1800, 900, 300], 300)]
        planned = [TimeZoneWeek(week, [1800, 900, 600, 300])]
        time_points = [
            TimePoint(D, 3600, 3000, 3200, 3300),
            TimePoint(
                date(2026, 1, 12),
                3600,
                3100,
                3300,
                3400,
                projected=True,
            ),
        ]
        hard_points = [
            TimePoint(D, 1200, 1000, 1100, 1150),
            TimePoint(
                date(2026, 1, 12),
                1800,
                1100,
                1200,
                1250,
                projected=True,
            ),
        ]
        zone_points = [
            ZoneAveragePoint(D, [1200, 900, 300, 0]),
            ZoneAveragePoint(
                date(2026, 1, 20),
                [1400, 800, 400, 100],
                projected=True,
            ),
        ]

        html = plot_time(
            weeks,
            "",
            time_points=time_points,
            hard_points=hard_points,
            planned_zone_weeks=planned,
            zone_points=zone_points,
            zone_window_days=42,
            windows=AverageWindows(),
            as_html=True,
        )

        data = plotly_data(html)
        names = [trace.get("name") for trace in data]

        self.assertEqual([], hoverable_unnamed(data))
        self.assertIn("Z4 planned", names)
        self.assertIn("hard 7d avg (weekly)", names)
        self.assertEqual(2, names.count("7d avg (weekly)"))

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
            [trace.get("name") for trace in absolute if trace.get("name")],
        )
        self.assertEqual(
            ["Unzoned", "Z4", "Z3", "Z2", "Z1"],
            [trace.get("name") for trace in percent if trace.get("name")],
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
            Vo2maxPoint(D, 65.0, 65.0, 65.0, 65.0),
            Vo2maxPoint(date(2026, 1, 2), 65.5, 65.4, 65.2, 65.2),
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


class OverviewReadabilityTests(unittest.TestCase):

    def test_overview_is_tall_with_a_two_row_legend_in_compact_names(self):
        bars = [(D, 300.0, 200.0, 0.0)]
        series = ZoneGroupSeries(
            points=[
                ZoneGroupPoint(
                    D,
                    easy_s=200.0,
                    hard_s=300.0,
                    unzoned_s=0.0,
                    easy_7=200.0,
                    easy_42=200.0,
                    easy_182=200.0,
                    hard_7=300.0,
                    hard_42=300.0,
                    hard_182=300.0,
                    total_7=500.0,
                    total_42=500.0,
                    total_182=500.0,
                )
            ]
        )

        html = plot_overview(
            bars,
            [],
            series,
            "",
            start=D,
            end=D,
            today=D,
            as_html=True,
        )

        self.assertIn('"height":700', html)
        self.assertIn('"font":{"size":10}', html)
        self.assertIn('"entrywidth":0.1429', html)
        self.assertIn('"traceorder":"normal"', html)
        self.assertIn('"name":"hard"', html)
        self.assertIn('"name":"hard 7d"', html)
        self.assertIn('"tickfont":{"size":10}', html)
        # Window-major, shortest first: every 7-day line, then 42, then 182.
        self.assertLess(
            html.index('"name":"hard 7d"'),
            html.index('"name":"total 7d"'),
        )
        self.assertLess(
            html.index('"name":"total 7d"'),
            html.index('"name":"hard 42d"'),
        )
        self.assertLess(
            html.index('"name":"hard 42d"'),
            html.index('"name":"total 42d"'),
        )
        self.assertLess(
            html.index('"name":"total 42d"'),
            html.index('"name":"hard 182d"'),
        )

        index = html.find("Plotly.newPlot(")
        data, _ = json.JSONDecoder().raw_decode(
            html[html.find("[", index):]
        )
        # Bars first, then the pale outlines, then the lines themselves.
        first_bar = next(
            i for i, trace in enumerate(data) if trace.get("type") == "bar"
        )
        last_bar = max(
            i for i, trace in enumerate(data) if trace.get("type") == "bar"
        )
        outlines = [
            i
            for i, trace in enumerate(data)
            if (trace.get("line") or {})
            .get("color", "")
            .startswith("rgba(255, 255, 255")
        ]
        hard_7d = next(
            i for i, trace in enumerate(data) if trace.get("name") == "hard 7d"
        )

        self.assertLess(first_bar, min(outlines))
        self.assertLess(last_bar, min(outlines))
        self.assertLess(max(outlines), hard_7d)


def _layout_of(html: str) -> dict:
    index = html.find("Plotly.newPlot(")
    bracket = html.find("[", index)
    _data, end = json.JSONDecoder().raw_decode(html[bracket:])
    brace = html.find("{", bracket + end)
    layout, _ = json.JSONDecoder().raw_decode(html[brace:])
    return layout


class CrosshairTests(unittest.TestCase):
    """Both spikes, so a value can be read off either axis."""

    def test_pace_hr_scatter_has_both_spikes(self):
        layout = _layout_of(
            plot_pace_hr(
                [PaceHrPoint(D, 300.0, 150.0, "Easy")],
                "",
                as_html=True,
            )
        )

        self.assertTrue(layout["xaxis"]["showspikes"])
        self.assertTrue(layout["yaxis"]["showspikes"])
        self.assertEqual("across", layout["xaxis"]["spikemode"])
        self.assertEqual("data", layout["xaxis"]["spikesnap"])
        self.assertEqual("cursor", layout["yaxis"]["spikesnap"])

    def test_overview_spikes_reach_the_second_axis(self):
        bars = [(D, 300.0, 200.0, 0.0)]
        series = ZoneGroupSeries(
            points=[
                ZoneGroupPoint(
                    D,
                    easy_s=200.0,
                    hard_s=300.0,
                    unzoned_s=0.0,
                    easy_7=200.0,
                    easy_42=200.0,
                    easy_182=200.0,
                    hard_7=300.0,
                    hard_42=300.0,
                    hard_182=300.0,
                    total_7=500.0,
                    total_42=500.0,
                    total_182=500.0,
                )
            ]
        )
        html = plot_overview(
            bars,
            [],
            series,
            "",
            start=D,
            end=D,
            today=D,
            vo2max_points=[Vo2maxPoint(D, 52.0, 52.0, 52.0, 52.0)],
            as_html=True,
        )
        layout = _layout_of(html)

        self.assertTrue(layout["yaxis2"]["showspikes"])
        self.assertEqual("cursor", layout["yaxis2"]["spikesnap"])
        self.assertEqual("cursor", layout["yaxis"]["spikesnap"])
        self.assertEqual("data", layout["xaxis"]["spikesnap"])
        # The axis ceiling survives the spike update.
        self.assertEqual([0, 45.0], layout["yaxis"]["range"])

    def test_pb_progression_keeps_its_pace_range(self):
        activities = [
            Activity(
                id=str(index),
                date=D + timedelta(days=index),
                type="run",
                distance_m=5000,
                duration_s=1200 + index * 20,
                workout_methods=["race"],
            )
            for index in range(3)
        ]
        html = plot_pb_progressions(
            pb_progressions(race_results(activities)),
            "",
            as_html=True,
        )
        layout = _layout_of(html)

        self.assertTrue(layout["yaxis"]["showspikes"])
        self.assertIn("range", layout["yaxis"])


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

    def test_load_axis_ignores_the_ultra_week(self):
        # Twelve Monday-to-Sunday weeks, the last with one 349-load day.
        start = date(2025, 12, 29)
        points = [
            LoadPoint(
                start + timedelta(days=index),
                40.0,
                35.0,
                38.0,
                40.0,
            )
            for index in range(12 * 7)
        ]
        points[-1] = LoadPoint(
            start + timedelta(days=12 * 7 - 1),
            349.0,
            40.0,
            42.0,
            60.0,
        )

        html = plot_load(points, "", as_html=True)

        self.assertIn('"range":[0,400.0]', html)
        self.assertIn("589.00 load (bar clipped)", html)

    def test_rpe_overlay_gets_its_own_scale(self):
        html = plot_load(
            [LoadPoint(D, 50, 40, 45, 48)],
            "",
            rpe_points=[RpePoint(D, 7.2, 7.8, 7.2, 7.0)],
            as_html=True,
        )

        # The weekly load axis follows the load; the RPE axis covers RPE.
        self.assertIn('"range":[0,400.0]', html)
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

    def test_pace_hr_chart_carries_weather_in_the_hover_and_a_note(self):
        points = [
            PaceHrPoint(
                D,
                300.0,
                150.0,
                weather=ActivityWeather(temp_c=12.4, wind_speed_ms=3.2),
            ),
            PaceHrPoint(D + timedelta(days=1), 290.0, 152.0),
        ]

        html = plot_pace_hr(points, "", as_html=True)

        degree = chr(92) + "u00b0C"
        slash = chr(92) + "u002f"
        self.assertIn("12 " + degree + ", wind 3 m" + slash + "s", html)
        self.assertIn(
            "weather on 1 of 2 runs (median 12 " + degree
            + ", 12 to 12 " + degree + ")",
            html,
        )

    def test_compare_pace_hr_chart_notes_weather_coverage(self):
        points = [
            PaceHrPoint(
                D,
                300.0,
                150.0,
                weather=ActivityWeather(temp_c=12.4),
            ),
            PaceHrPoint(D + timedelta(days=1), 290.0, 152.0),
        ]

        html = plot_compare_pace_hr(points, "", as_html=True)

        self.assertIn("weather on 1 of 2 runs", html)

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
        self.assertIn('"dash":"longdash"', html)
        self.assertEqual(
            2,
            html.count('"color":"rgba(255, 255, 255, 0.85)"'),
        )
        # The halos are drawn before the lines they lift off the points.
        self.assertLess(
            html.index('"color":"rgba(255, 255, 255, 0.85)"'),
            html.index("first half efficiency"),
        )

        lines = [
            trace
            for trace in plotly_data(html)
            if trace.get("name") == "first half efficiency"
        ]
        self.assertEqual(1, len(lines))
        self.assertEqual(list(PACE_HR_SPEED_RANGE), lines[0]["x"])

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

    def _official_results(self):
        activities = [
            Activity(
                id="a",
                date=D,
                type="run",
                name="Morning Run",
                distance_m=5000,
                duration_s=1500,
                workout_methods=["race"],
            )
        ]
        return race_results(
            activities,
            official_by_activity([
                OfficialRaceResult(
                    activity_id="a",
                    name="City 5k",
                    official_distance_m=5000.0,
                    official_time_s=1500.0,
                )
            ]),
        )

    def test_race_chart_hover_shows_the_official_title(self):
        results = self._official_results()

        html = plot_races(results, fit_riegel(results), "", as_html=True)

        self.assertIn("Morning Run", html)
        self.assertIn("City 5k", html)

    def test_pb_chart_hover_shows_the_official_title(self):
        results = self._official_results()

        html = plot_pb_progressions(
            pb_progressions(results),
            "",
            as_html=True,
        )

        self.assertIn("Morning Run", html)
        self.assertIn("City 5k", html)

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

    def test_equipment_chart_groups_categories_with_colours(self):
        stats = [
            EquipmentStat(
                equipment=Equipment(id="s", type="shoe", name="Shoe"),
                sessions=1,
                distance_m=100000,
            ),
            EquipmentStat(
                equipment=Equipment(id="b", type="bike", name="Bike"),
                sessions=1,
                distance_m=300000,
            ),
            EquipmentStat(
                equipment=Equipment(id="o", type="other", name="Other"),
                sessions=1,
                distance_m=50000,
            ),
        ]

        html = plot_equipment(stats, "", as_html=True)
        data = plotly_data(html)
        traces = [trace for trace in data if trace.get("type") == "bar"]

        # Traces are added bottom-up so shoes sit at the top.
        self.assertEqual(
            ["Other", "Bikes", "Shoes"],
            [trace["name"] for trace in traces],
        )
        self.assertEqual(
            ["#9467bd", "#2ca02c", "#1f77b4"],
            [trace["marker"]["color"][0] for trace in traces],
        )
        self.assertEqual(
            {"Shoes": 1, "Bikes": 2, "Other": 3},
            {
                trace["name"]: trace["legendrank"]
                for trace in traces
            },
        )

    def test_equipment_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_equipment([], str(Path(tmp) / "gear.png"))


class ThresholdChartTests(unittest.TestCase):

    def test_threshold_steps_and_official_race_pace(self):
        thresholds = [
            ThresholdPoint(D, 174.0, 192.0, 222.0),
            ThresholdPoint(date(2026, 6, 1), 174.0, 192.0, 214.0),
        ]
        races = [
            RacePacePoint(
                date(2026, 10, 1),
                230.0,
                "Autumn 10k",
                10000.0,
                242.0,
            )
        ]

        html = plot_thresholds(
            thresholds,
            races,
            "",
            today=date(2026, 11, 1),
            as_html=True,
        )
        data = plotly_data(html)
        traces = {trace.get("name"): trace for trace in data}

        self.assertEqual(
            {
                "LTHR",
                "Max HR",
                "Threshold pace",
                "Official race pace",
                "Race 60 min pace",
            },
            set(traces),
        )
        self.assertEqual("y2", traces["Threshold pace"]["yaxis"])
        self.assertEqual("y2", traces["Official race pace"]["yaxis"])
        self.assertEqual([230.0], traces["Official race pace"]["y"])
        self.assertEqual("y2", traces["Race 60 min pace"]["yaxis"])
        self.assertEqual([242.0], traces["Race 60 min pace"]["y"])
        self.assertIn("Autumn 10k (10.0 km)", html)
        self.assertIn("60 min %{customdata}", html)
        self.assertIn("3:42", html)


class DeviceChartTests(unittest.TestCase):

    def test_device_timeline_marks_periods_and_counts(self):
        stats = [
            DeviceStat(
                device=Device(id="w", name="Watch"),
                activities=12,
                first_used=D,
                last_used=date(2026, 1, 1),
            ),
            DeviceStat(
                device=Device(id="b", name="Bike"),
                activities=3,
                first_used=date(2026, 1, 1),
            ),
        ]

        html = plot_devices(stats, "", as_html=True)
        data = plotly_data(html)
        traces = [trace for trace in data if trace.get("type") == "scatter"]

        self.assertEqual(2, len(traces))
        self.assertEqual(["Watch", "Bike"], [trace["y"][0] for trace in traces])
        self.assertIn("12 activities", html)
        self.assertIn("2026-01-01", html)


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
        self.assertIn('"hovermode":"x unified"', html)

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

    def test_efficiency_lines_follow_each_year(self):
        points = [
            PaceHrPoint(
                date(2025, 3, 1),
                300.0,
                150.0,
                resting_hr=50,
                distance_m=10000,
                excess_beats=5000,
                steady=True,
            ),
            PaceHrPoint(
                date(2025, 9, 1),
                300.0,
                150.0,
                resting_hr=50,
                distance_m=10000,
                excess_beats=5000,
                steady=True,
            ),
            PaceHrPoint(
                date(2026, 3, 1),
                300.0,
                121.0,
                resting_hr=40,
                distance_m=12500,
                excess_beats=5000,
                steady=True,
            ),
            PaceHrPoint(
                date(2026, 9, 1),
                300.0,
                121.0,
                resting_hr=40,
                distance_m=12500,
                excess_beats=5000,
                steady=True,
            ),
        ]

        html = plot_compare_pace_hr(points, "", as_html=True)

        self.assertIn('"dash":"longdash"', html)
        self.assertIn("2026 efficiency: E = 2.50", html)
        self.assertEqual(
            2,
            html.count('"color":"rgba(255, 255, 255, 0.85)"'),
        )
        self.assertIn(
            "dashed: steady efficiency per year (2025 2.00, 2026 2.50)",
            html,
        )

        lines = [
            trace
            for trace in plotly_data(html)
            if str(trace.get("name", "")).endswith(" efficiency")
        ]
        self.assertEqual(2, len(lines))
        self.assertTrue(
            all(trace["x"] == list(PACE_HR_SPEED_RANGE) for trace in lines)
        )

    def test_no_efficiency_lines_without_steady_runs(self):
        points = [
            PaceHrPoint(date(2025, 6, 1), 300.0, 150.0),
            PaceHrPoint(date(2025, 7, 1), 290.0, 152.0),
        ]

        html = plot_compare_pace_hr(points, "", as_html=True)

        self.assertNotIn('"dash":"longdash"', html)
        self.assertNotIn(
            '"color":"rgba(255, 255, 255, 0.85)"',
            html,
        )
        self.assertNotIn("steady efficiency per year", html)

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

    def test_compare_color_gives_the_newest_years_the_strongest_colors(self):
        # The anchor year gets the first (saturated) palette colour, then the
        # recent years follow; the oldest years fade into the pale tail.
        self.assertEqual("#1f77b4", compare_color(2026))
        self.assertEqual("#ff7f0e", compare_color(2025))
        self.assertEqual("#2ca02c", compare_color(2024))
        self.assertNotEqual(compare_color(2009), compare_color(2026))

    def test_compare_color_is_stable_per_year(self):
        self.assertEqual(compare_color(2023), compare_color(2023))
        self.assertNotEqual(compare_color(2022), compare_color(2023))
        self.assertEqual(
            len({compare_color(year) for year in range(2009, 2027)}),
            18,
        )

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
        self.assertIn("steady 40", html)

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

    def test_load_bars_are_weekly_and_the_lines_match_that_unit(self):
        points = [
            LoadPoint(date(2025, 12, 29), 30.0, 30.0, 31.0, 32.0),
            LoadPoint(date(2025, 12, 30), 20.0, 32.0, 33.0, 34.0),
            LoadPoint(date(2026, 1, 5), 50.0, 34.0, 35.0, 36.0),
        ]

        html = plot_load(points, "", as_html=True)
        data = plotly_data(html)
        bars = {
            trace["name"]: trace
            for trace in data
            if trace.get("type") == "bar"
        }
        lines = [
            trace
            for trace in data
            if trace.get("name")
            and trace.get("name", "").endswith("d)")
        ]

        self.assertEqual({"running load"}, set(bars))
        self.assertEqual(
            ["2025-12-29", "2026-01-05"],
            bars["running load"]["x"],
        )
        self.assertEqual([50.0, 50.0], bars["running load"]["y"])
        self.assertEqual(
            7 * 24 * 60 * 60 * 1000,
            bars["running load"]["width"],
        )

        # Every average is 7x the daily EWMA, so it reads in load per week.
        self.assertEqual(
            ["Fatigue (7d)", "Fitness (42d)", "Base (182d)"],
            [trace["name"] for trace in lines],
        )
        for trace in lines:
            attribute = trace["name"].split(" ")[0].lower()
            self.assertEqual(
                [
                    round(getattr(point, attribute) * 7, 6)
                    for point in points
                ],
                [round(value, 6) for value in trace["y"]],
            )

        self.assertEqual([], hoverable_unnamed(data))

    def test_load_stacks_cross_load_and_its_own_plan(self):
        points = [
            LoadPoint(D, 50.0, 40.0, 45.0, 48.0),
            LoadPoint(D + timedelta(days=1), 0.0, 40.0, 45.0, 48.0,
                      cross_load=30.0),
        ]

        html = plot_load(
            points,
            "",
            planned_load=[(D + timedelta(days=3), 20.0)],
            planned_cross_load=[(D + timedelta(days=3), 10.0)],
            as_html=True,
        )
        data = plotly_data(html)
        bars = {
            trace["name"]: trace
            for trace in data
            if trace.get("type") == "bar"
        }

        self.assertEqual(50.0, bars["running load"]["y"][0])
        self.assertEqual([50.0], bars["cross load"]["base"])
        self.assertEqual(30.0, bars["cross load"]["y"][0])
        self.assertEqual([80.0], bars["planned run"]["base"])
        self.assertEqual([20.0], bars["planned run"]["y"])
        self.assertEqual([100.0], bars["planned cross"]["base"])
        self.assertEqual([10.0], bars["planned cross"]["y"])

    def test_planned_load_stacks_on_the_partial_week(self):
        points = [LoadPoint(D, 50.0, 40.0, 45.0, 48.0)]

        html = plot_load(
            points,
            "",
            planned_load=[
                (D, 55.0),
                (date(2026, 1, 3), 20.0),
                (date(2026, 1, 5), 60.0),
            ],
            as_html=True,
        )
        data = plotly_data(html)
        planned = [
            trace
            for trace in data
            if trace.get("name") == "planned run"
        ]

        self.assertEqual(1, len(planned))
        # The planned day with an actual is dropped; the rest stacks on the
        # current week and an empty week starts at zero.
        self.assertEqual(
            ["2025-12-29", "2026-01-05"],
            planned[0]["x"],
        )
        self.assertEqual([20.0, 60.0], planned[0]["y"])
        self.assertEqual([50.0, 0.0], planned[0]["base"])
        self.assertEqual(
            "/",
            planned[0]["marker"]["pattern"]["shape"],
        )
        self.assertIn('"barmode":"overlay"', html)
        self.assertEqual([], hoverable_unnamed(data))

    def test_load_chart_draws_shortest_window_first(self):
        points = [
            LoadPoint(D + timedelta(days=index), 50.0, 40.0, 45.0, 48.0)
            for index in range(6)
        ]

        html = plot_load(points, "", as_html=True)

        self.assertLess(
            html.index('"name":"Fatigue (7d)"'),
            html.index('"name":"Fitness (42d)"'),
        )
        self.assertLess(
            html.index('"name":"Fitness (42d)"'),
            html.index('"name":"Base (182d)"'),
        )

    def test_load_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_load([], str(Path(tmp) / "load.png"))


class WeightChartTests(unittest.TestCase):

    def test_points_and_mean_share_the_kg_axis_with_a_gap(self):
        points = [
            WeightPoint(
                date(2026, 1, 1),
                weight_kg=80.0,
                average_kg=80.0,
            ),
            WeightPoint(date(2026, 1, 2)),
            WeightPoint(
                date(2026, 1, 3),
                weight_kg=78.0,
                average_kg=79.0,
            ),
        ]

        html = plot_weight(points, "", as_html=True)
        data = plotly_data(html)
        traces = {trace.get("name"): trace for trace in data}

        self.assertEqual({"measured", "7-day avg"}, set(traces))
        self.assertEqual([80.0, None, 78.0], traces["measured"]["y"])
        self.assertEqual([80.0, None, 79.0], traces["7-day avg"]["y"])
        self.assertFalse(traces["7-day avg"]["connectgaps"])
        self.assertEqual("kg", plotly_layout(html)["yaxis"]["title"]["text"])
        # No readiness bands: one trace pair, no shapes.
        self.assertEqual(2, len(data))
        self.assertNotIn("shapes", plotly_layout(html))

    def test_weight_chart_rejects_empty_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_weight(
                    [WeightPoint(date(2026, 1, 1))],
                    str(Path(tmp) / "weight.png"),
                )

    def test_weight_chart_writes_a_file(self):
        points = [WeightPoint(D, weight_kg=80.0, average_kg=80.0)]

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "weight.png"
            self.assertEqual(
                str(output),
                plot_weight(points, str(output)),
            )
            self.assertTrue(output.exists())


class GearMileageChartTests(unittest.TestCase):

    def _detail(self, target=500000.0):
        return GearDetail(
            stat=EquipmentStat(
                equipment=Equipment(id="shoe", type="shoe", name="Demo Shoe"),
                sessions=2,
                distance_m=12000,
                target_distance_m=target,
            ),
            activities=[],
            co_used=[],
            monthly=[
                (date(2026, 8, 1), 7.0),
                (date(2026, 9, 1), 5.0),
            ],
        )

    def test_monthly_bars_and_cumulative_line(self):
        html = plot_gear_mileage(self._detail(), as_html=True)
        data = plotly_data(html)
        traces = {trace.get("name"): trace for trace in data}

        self.assertEqual({"monthly km", "cumulative km"}, set(traces))
        self.assertEqual([7.0, 5.0], traces["monthly km"]["y"])
        self.assertEqual([7.0, 12.0], traces["cumulative km"]["y"])
        self.assertEqual(
            "cumulative km",
            plotly_layout(html)["yaxis2"]["title"]["text"],
        )

    def test_target_line_is_drawn_when_the_item_has_one(self):
        html = plot_gear_mileage(self._detail(target=10000.0), as_html=True)
        shapes = plotly_layout(html)["shapes"]

        self.assertTrue(
            any(
                shape.get("y1") == 10.0
                for shape in shapes
            )
        )
        self.assertIn("target 10 km", html)

    def test_empty_gear_has_no_chart(self):
        detail = GearDetail(
            stat=EquipmentStat(
                equipment=Equipment(id="shoe", type="shoe", name="Demo Shoe"),
            ),
            activities=[],
            co_used=[],
            monthly=[],
        )

        with self.assertRaises(ValueError):
            plot_gear_mileage(detail, as_html=True)


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


def vo2max_methods():
    latest = date(2026, 1, 2)
    return Vo2maxMethods(
        all_runs=[
            Vo2maxPoint(D, 60.0, 59.7, 59.5, 59.0),
            Vo2maxPoint(latest, None, 59.65, 59.6, 59.1),
        ],
        garmin=[
            GarminVo2maxDevice(
                device_id="w1",
                label="Garmin Forerunner 645",
                measurements=[Vo2maxMeasurement(D, 58.0)],
                avg_42=[(D, 58.0)],
                avg_182=[(D, 58.0)],
            ),
            GarminVo2maxDevice(
                device_id="w2",
                label="Garmin Enduro",
                measurements=[Vo2maxMeasurement(latest, 61.0)],
                avg_42=[(latest, 61.0)],
                avg_182=[(latest, 61.0)],
            ),
        ],
        runalyze=[
            Vo2maxPoint(D, None, 61.0, 60.5, 60.2),
            Vo2maxPoint(latest, None, 61.2, 60.6, 60.3),
        ],
        races=[(D, 62.0)],
    )


class Vo2maxChartTests(unittest.TestCase):

    def test_the_methods_chart_labels_every_series(self):
        html = plot_vo2max_methods(
            vo2max_methods(),
            "",
            as_html=True,
        )
        names = [trace.get("name") for trace in plotly_data(html)]

        self.assertEqual(
            [
                "Estimate 42d",
                "Estimate 182d",
                "Runalyze 42d",
                "Runalyze 182d",
                "Garmin Forerunner 645",
                "Garmin Enduro",
                "Garmin Enduro 42d",
                "Garmin Enduro 182d",
                "Race VDOT",
            ],
            names,
        )
        self.assertIn('"mode":"lines"', html)
        self.assertIn('"symbol":"star"', html)

    def test_the_latest_device_gets_both_ewma_lines(self):
        html = plot_vo2max_methods(
            vo2max_methods(),
            "",
            as_html=True,
        )
        data = plotly_data(html)

        names = [trace.get("name") for trace in data]

        self.assertNotIn("Garmin Forerunner 645 42d", names)
        self.assertIn("Garmin Enduro 42d", names)
        self.assertIn("Garmin Enduro 182d", names)

    def test_runalyze_is_lines_not_dots(self):
        html = plot_vo2max_methods(
            vo2max_methods(),
            "",
            as_html=True,
        )
        runalyze = [
            trace
            for trace in plotly_data(html)
            if (trace.get("name") or "").startswith("Runalyze")
        ]

        self.assertEqual(2, len(runalyze))
        self.assertTrue(
            all(trace.get("mode") == "lines" for trace in runalyze)
        )

    def test_vo2max_chart_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "vo2max.png"

            result = plot_vo2max_methods(
                vo2max_methods(),
                str(output),
            )

            self.assertEqual(str(output), result)
            self.assertTrue(output.exists())

    def test_vo2max_chart_rejects_empty_data(self):
        empty = Vo2maxMethods([], [], [], [])

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                plot_vo2max_methods(empty, str(Path(tmp) / "vo2max.png"))


if __name__ == "__main__":
    unittest.main()
