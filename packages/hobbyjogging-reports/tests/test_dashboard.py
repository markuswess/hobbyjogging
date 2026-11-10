import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core.model import Event, EventZoneTime, WellnessDay
from hobbyjogging_report.dashboard import build_dashboard, resolve_output_dir
from hobbyjogging_report.overview import overview_ewma, planned_overview
from hobbyjogging_report.zone_groups import (
    planned_bars_without_actual,
    zone_group_series,
)
from hobbyjogging_report.model import AverageWindows
from support import FakeSource, activity_factory, make_interval

TODAY = date(2026, 11, 9)
activity = activity_factory()


def _source():
    return FakeSource(
        activities=[
            activity(
                id="run1",
                date=TODAY - timedelta(days=1),
                name="Easy",
                duration_s=3600,
                distance_m=10000,
                avg_hr=140,
                training_load=50,
                pace_zone_times=[1800, 1200, 600, 0],
                feel=2,
                workout_methods=["continuous"],
                workout_targets=["base"],
            ),
            activity(
                id="run2",
                date=TODAY - timedelta(days=4),
                name="Tempo",
                duration_s=1800,
                distance_m=5000,
                avg_hr=150,
                training_load=30,
                pace_zone_times=[600, 600, 300, 300],
                feel=2,
            ),
            activity(
                id="ride1",
                date=TODAY - timedelta(days=3),
                type="ride",
                name="Bike",
                duration_s=3600,
                training_load=20,
            ),
            activity(
                id="bad",
                date=TODAY - timedelta(days=2),
                name="Flagged",
                duration_s=1800,
                distance_m=5000,
                needs_review=True,
            ),
            activity(
                id="old",
                date=TODAY - timedelta(days=20),
                name="Old run",
                duration_s=2400,
                distance_m=8000,
                avg_hr=145,
                training_load=40,
                pace_zone_times=[1200, 600, 300, 0],
            ),
        ],
        intervals={
            "run1": [make_interval(300, 1000, avg_hr=160, max_hr=170)],
        },
        events=[
            Event(
                date=TODAY + timedelta(days=1),
                name="5x5 subT",
                type="run",
                distance_m=12000,
                duration_s=3000,
                training_load=60,
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 600, 1),
                    EventZoneTime("Z3", 1500, 3),
                    EventZoneTime("Z4", 300, 4),
                ],
            ),
            Event(
                date=TODAY + timedelta(days=3),
                name="Long",
                type="run",
                distance_m=20000,
                duration_s=6000,
                training_load=80,
            ),
            Event(
                date=TODAY + timedelta(days=40),
                name="Autumn Marathon",
                type="run",
                distance_m=42195,
                training_load=150,
                zone_kind="pace",
                workout_methods=["race"],
            ),
            Event(
                date=TODAY + timedelta(days=2),
                name="Travel note",
            ),
        ],
        wellness=[
            WellnessDay(
                date=TODAY - timedelta(days=1),
                hrv=60,
                resting_hr=45,
                sleep_s=8 * 3600,
            ),
            WellnessDay(
                date=TODAY - timedelta(days=2),
                hrv=55,
                resting_hr=46,
                sleep_s=7.5 * 3600,
            ),
        ],
    )


class DashboardBuildTests(unittest.TestCase):

    def test_builds_pages_and_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"

            result = build_dashboard(
                _source(),
                target,
                days=14,
                activity_limit=10,
                today=TODAY,
            )

            self.assertEqual(target, result)
            self.assertTrue((target / "index.html").exists())
            self.assertTrue((target / "activities.html").exists())
            self.assertTrue((target / "recovery.html").exists())
            self.assertTrue((target / "health.html").exists())
            self.assertTrue((target / "reports.html").exists())
            self.assertTrue((target / "activity" / "run1.html").exists())
            self.assertTrue((target / ".hobbyjogging-dashboard").exists())
            self.assertGreater(
                (target / "plotly.min.js").stat().st_size,
                1000,
            )

            index = (target / "index.html").read_text()
            self.assertIn("Training overview", index)
            self.assertIn("Runs / week", index)
            self.assertIn("Cross / week", index)
            self.assertIn("Run time / week", index)
            self.assertIn("Run km / week", index)
            self.assertIn("Load / week", index)
            self.assertIn("Z3+4 / week", index)
            self.assertIn("7-day EWMA", index)
            self.assertIn("42-day EWMA", index)
            self.assertIn("182-day EWMA", index)
            self.assertIn("Next 14 days (avg/week)", index)
            self.assertIn("1h15", index)
            self.assertIn("16.0", index)
            self.assertIn("15min", index)
            self.assertIn("5x5 subT", index)
            self.assertIn("Daily running minutes", index)
            self.assertIn("Hard 7d", index)
            self.assertIn("Hard 42d", index)
            self.assertIn("Hard 182d", index)
            self.assertIn("Total 7d", index)
            self.assertIn("Total 42d", index)
            self.assertIn("Total 182d", index)
            self.assertIn("planned hard", index)
            self.assertIn("planned easy", index)
            self.assertIn("minutes", index)
            self.assertIn("2026-09-01", index)
            self.assertIn("2026-11-23", index)
            self.assertIn("Daily Training Report", index)
            self.assertIn("Planned Workouts", index)
            self.assertIn("Z3+4 uses each event's planned zone kind", index)
            self.assertIn("Upcoming races", index)
            self.assertIn("Autumn Marathon", index)
            self.assertIn("42.2 km", index)
            self.assertNotIn("Plan vs actual", index)
            self.assertNotIn("Training load", index)
            self.assertNotIn("Quality sessions", index)
            self.assertIn("Plotly.newPlot", index)
            self.assertIn("plotly.min.js", index)
            self.assertIn("activities with open review items are hidden", index)
            self.assertIn("Recovery and Health", index)
            self.assertIn(">Data Health</a>", index)
            self.assertIn(">Reports</a>", index)

            recovery = (target / "recovery.html").read_text()
            self.assertIn("Recovery and Health", recovery)
            self.assertIn("Recovery Report — Moving Averages", recovery)
            self.assertIn("7/42/182-day averages ending 2026-11-09", recovery)
            self.assertIn("7-day avg", recovery)
            self.assertIn("HRV", recovery)
            self.assertIn("58 ms", recovery)
            self.assertIn('<h3>Night</h3>', recovery)
            self.assertIn("2026-11-08: HRV 60 ms, RHR 45 bpm, Sleep 8h00", recovery)
            self.assertIn("2 of 186 days have wellness data", recovery)
            self.assertIn("Plotly.newPlot", recovery)
            self.assertNotIn('class="grid"', recovery)

            activities = (target / "activities.html").read_text()
            self.assertIn("activity/run1.html", activities)
            self.assertIn("Bike", activities)
            self.assertIn("Old run", activities)
            self.assertIn("Methods", activities)
            self.assertIn("Continuous", activities)
            self.assertIn("Base", activities)
            self.assertIn("activities are hidden by import review", activities)

            detail = (target / "activity" / "run1.html").read_text()
            self.assertIn("Easy", detail)
            self.assertIn("Intervals", detail)
            self.assertIn("Work", detail)
            self.assertIn("Methods", detail)
            self.assertIn("Continuous", detail)
            self.assertIn("Targets", detail)
            self.assertIn("Base", detail)
            self.assertIn("../index.html", detail)
            self.assertIn('href="../activities.html"', detail)

            health = (target / "health.html").read_text()
            self.assertIn("Flagged", health)
            self.assertIn("hidden", health)
            self.assertIn("Missing data", health)

            reports = (target / "reports.html").read_text()
            self.assertIn(
                "No Markdown reports selected",
                reports,
            )

    def test_selected_markdown_reports_are_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"

            build_dashboard(
                _source(),
                target,
                today=TODAY,
                reports=("overview", "planned"),
            )

            reports = (target / "reports.html").read_text()
            self.assertIn("Training Overview — EWMA", reports)
            self.assertIn("Planned Workouts", reports)
            self.assertIn("5x5 subT", reports)
            self.assertIn("<table>", reports)

    def test_unknown_markdown_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                build_dashboard(
                    _source(),
                    Path(tmp) / "site",
                    today=TODAY,
                    reports=("nope",),
                )

    def test_include_review_links_flagged_activities(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"

            build_dashboard(
                _source(),
                target,
                today=TODAY,
                include_review=True,
            )

            index = (target / "index.html").read_text()
            self.assertIn(
                "activities with open review items are included",
                index,
            )
            self.assertTrue(
                (target / "activity" / "bad.html").exists()
            )
            health = (target / "health.html").read_text()
            self.assertIn("bad.html", health)
            self.assertIn("included", health)

    def test_empty_source_still_renders_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"

            build_dashboard(
                FakeSource(),
                target,
                today=TODAY,
            )

            self.assertTrue((target / "index.html").exists())
            self.assertTrue((target / "recovery.html").exists())
            self.assertIn(
                "No activities found",
                (target / "activities.html").read_text(),
            )
            self.assertIn(
                "No planned sessions",
                (target / "index.html").read_text(),
            )
            self.assertIn(
                "No wellness data",
                (target / "recovery.html").read_text(),
            )

    def test_second_build_replaces_dashboard_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"
            build_dashboard(_source(), target, today=TODAY)
            (target / "stale.txt").write_text("old")

            build_dashboard(_source(), target, today=TODAY)

            self.assertFalse((target / "stale.txt").exists())
            self.assertTrue((target / "index.html").exists())

    def test_refuses_to_replace_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "other"
            target.mkdir()
            (target / "keep.txt").write_text("keep")

            with self.assertRaises(ValueError):
                build_dashboard(_source(), target, today=TODAY)

            self.assertTrue((target / "keep.txt").exists())


class DashboardOutputTests(unittest.TestCase):

    def test_explicit_output_wins(self):
        self.assertEqual(
            Path("/tmp/dashboard"),
            resolve_output_dir("/tmp/dashboard"),
        )

    def test_env_var_adds_dashboard_subfolder(self):
        with patch.dict(
            os.environ,
            {"HOBBYJOGGING_DASHBOARD_DIR": "/tmp/reports"},
        ):
            self.assertEqual(
                Path("/tmp/reports/dashboard"),
                resolve_output_dir(),
            )

    def test_default_is_repo_data_dashboard(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                Path("data/dashboard"),
                resolve_output_dir(),
            )


class DashboardEwmaTests(unittest.TestCase):

    def test_planned_bars_include_today_without_an_actual_run(self):
        events = [
            Event(
                date=TODAY,
                name="Today plan",
                type="run",
                duration_s=3600,
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 600, 1),
                    EventZoneTime("Z3", 300, 3),
                ],
            ),
            Event(
                date=TODAY + timedelta(days=1),
                name="Tomorrow plan",
                type="run",
                duration_s=3600,
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 600, 1),
                    EventZoneTime("Z3", 300, 3),
                ],
            ),
        ]
        actual_bars = [
            (TODAY, 0.0, 0.0, 0.0),
            (TODAY - timedelta(days=1), 600.0, 0.0, 0.0),
        ]

        bars = planned_bars_without_actual(
            events,
            actual_bars,
            TODAY,
            TODAY + timedelta(days=1),
        )

        self.assertEqual(
            [TODAY, TODAY + timedelta(days=1)],
            [row[0] for row in bars],
        )

    def test_planned_bars_drop_today_after_an_actual_run(self):
        events = [
            Event(
                date=TODAY,
                name="Today plan",
                type="run",
                duration_s=3600,
                zone_kind="pace",
                zone_times=[EventZoneTime("Z1", 600, 1)],
            ),
            Event(
                date=TODAY + timedelta(days=1),
                name="Tomorrow plan",
                type="run",
                duration_s=3600,
                zone_kind="pace",
                zone_times=[EventZoneTime("Z1", 600, 1)],
            ),
        ]
        actual_bars = [(TODAY, 600.0, 0.0, 0.0)]

        bars = planned_bars_without_actual(
            events,
            actual_bars,
            TODAY,
            TODAY + timedelta(days=1),
        )

        self.assertEqual(
            [TODAY + timedelta(days=1)],
            [row[0] for row in bars],
        )

    def test_zone_group_series_uses_planned_when_no_actual(self):
        events = [
            Event(
                date=TODAY,
                type="run",
                duration_s=3600,
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 600, 1),
                    EventZoneTime("Z3", 300, 3),
                ],
            )
        ]

        series = zone_group_series(
            [],
            events,
            TODAY,
            TODAY,
            windows=AverageWindows(),
        )

        self.assertEqual(1, len(series.points))
        point = series.points[0]
        self.assertTrue(point.projected)
        self.assertEqual(600, point.easy_s)
        self.assertEqual(300, point.hard_s)
        self.assertGreater(point.easy_7, 0)
        self.assertGreater(point.hard_7, 0)
        self.assertGreater(point.total_7, 0)

    def test_zone_group_series_prefers_actual_over_planned(self):
        events = [
            Event(
                date=TODAY,
                type="run",
                duration_s=3600,
                zone_kind="pace",
                zone_times=[EventZoneTime("Z3", 1800, 3)],
            )
        ]
        activities = [
            activity(
                id="actual",
                date=TODAY,
                duration_s=3600,
                distance_m=10000,
                pace_zone_times=[600, 600, 1800, 600],
            )
        ]

        series = zone_group_series(
            activities,
            events,
            TODAY,
            TODAY,
            windows=AverageWindows(),
        )

        point = series.points[0]
        self.assertFalse(point.projected)
        self.assertEqual(1200, point.easy_s)
        self.assertEqual(2400, point.hard_s)
        self.assertGreater(point.total_7, 0)

    def test_planned_overview_totals_next_period(self):
        source = _source()
        planned = planned_overview(
            source._events,
            TODAY + timedelta(days=1),
            TODAY + timedelta(days=14),
        )

        self.assertEqual(2, planned.runs)
        self.assertEqual(0, planned.cross)
        self.assertEqual(9000, planned.run_time_s)
        self.assertEqual(32000, planned.run_distance_m)
        self.assertEqual(140, planned.load)
        self.assertEqual(1800, planned.z3_z4_s)

    def test_ewma_rows_are_weekly_equivalents(self):
        activities = [
            activity(
                id=f"run{index}",
                date=TODAY - timedelta(days=index),
                duration_s=3600,
                distance_m=10000,
            )
            for index in range(100)
        ]

        rows = {
            row.label: row
            for row in overview_ewma(
                activities,
                TODAY - timedelta(days=99),
                TODAY,
            )
        }

        runs = rows["Runs / week"]
        self.assertGreater(runs.values[7], runs.values[42])
        self.assertGreater(runs.values[42], runs.values[182])
        self.assertLessEqual(runs.values[7], 7)

        run_time = rows["Run time / week"]
        self.assertGreater(run_time.values[7], run_time.values[42])
        self.assertGreater(run_time.values[42], run_time.values[182])
        self.assertLessEqual(run_time.values[7], 7 * 3600)


if __name__ == "__main__":
    unittest.main()
