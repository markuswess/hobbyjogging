import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core.model import (
    ActivityWeather,
    Equipment,
    Event,
    Lap,
    EventZoneTime,
    ReviewItem,
    WellnessDay,
)
from hobbyjogging_report.dashboard import build_dashboard, resolve_output_dir
from hobbyjogging_report.dashboard.analysis import build_analysis_section
from hobbyjogging_report.dashboard.lab import _bench_guide, build_lab_section
from hobbyjogging_report.links import ActivityLinks
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
    shoe = Equipment(
        id="shoe1",
        type="shoe",
        name="Demo Shoe",
        brand="Acme",
        acquired_on=TODAY - timedelta(days=200),
        target_distance_m=100000,
    )

    return FakeSource(
        equipment=[shoe],
        activities=[
            activity(
                id="run1",
                date=TODAY - timedelta(days=1),
                name="Easy",
                duration_s=3600,
                distance_m=10000,
                avg_hr=140,
                vo2max_garmin=54.2,
                training_load=50,
                pace_zone_times=[1800, 1200, 600, 0],
                feel=2,
                rpe=3,
                workout_methods=["continuous"],
                workout_targets=["base"],
                equipment=[shoe],
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
                rpe=5,
                equipment=[shoe],
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
                id="race1",
                date=TODAY - timedelta(days=10),
                name="Spring 5k",
                duration_s=1200,
                distance_m=5000,
                avg_hr=175,
                training_load=40,
                pace_zone_times=[0, 0, 300, 900],
                workout_methods=["race"],
                workout_targets=["speed"],
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
            "run1": [
                make_interval(300, 1000, avg_hr=160, max_hr=170),
                make_interval(300, 1000, avg_hr=162, max_hr=172),
            ],
        },
        events=[
            Event(
                id="ev-subt",
                date=TODAY + timedelta(days=1),
                name="5x5 subT",
                type="run",
                distance_m=12000,
                duration_s=3000,
                training_load=60,
                workout_methods=["intervals"],
                workout_targets=["threshold"],
                zone_kind="pace",
                zone_times=[
                    EventZoneTime("Z1", 600, 1),
                    EventZoneTime("Z3", 1500, 3),
                    EventZoneTime("Z4", 300, 4),
                ],
            ),
            Event(
                id="ev-long",
                date=TODAY + timedelta(days=3),
                name="Long",
                type="run",
                distance_m=20000,
                duration_s=6000,
                training_load=80,
            ),
            Event(
                id="ev-marathon",
                date=TODAY + timedelta(days=40),
                name="Autumn Marathon",
                type="run",
                distance_m=42195,
                training_load=150,
                zone_kind="pace",
                zone_times=[EventZoneTime("Z1", 3600, 1)],
                workout_methods=["race"],
            ),
            Event(
                date=TODAY + timedelta(days=2),
                name="Travel note",
            ),
            Event(
                id="ev-matched",
                date=TODAY - timedelta(days=1),
                name="Matched easy",
                type="run",
            ),
            Event(
                id="ev-missed",
                date=TODAY - timedelta(days=5),
                name="Missed tempo",
                type="run",
            ),
        ],
        laps={
            "race1": [
                Lap(index=1, duration_s=600, distance_m=2500, avg_hr=172),
                Lap(index=2, duration_s=610, distance_m=2500, avg_hr=178),
            ],
        },
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
        weather={
            "run1": ActivityWeather(temp_c=12.4, wind_speed_ms=3.2),
        },
        links={
            "run1": ActivityLinks(
                intervals="https://intervals.icu/activities/i1",
                garmin="https://connect.garmin.com/app/activity/2",
            ),
        },
        review_items=[
            ReviewItem(
                id=7,
                category="field_conflict",
                severity="warn",
                detail="avg_hr differs by 6 bpm",
                reported_at="2026-11-09T10:00:00Z",
                activity_id="run2",
                activity_date=TODAY - timedelta(days=4),
                activity_name="Tempo",
                sport="run",
                source="intervals",
                external_id="i2",
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
            self.assertTrue((target / "docs.html").exists())
            self.assertTrue((target / "performance.html").exists())
            self.assertFalse((target / "reports.html").exists())
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
            self.assertIn("Run load / week", index)
            self.assertIn("Z3+4 / week", index)
            self.assertIn("7-day EWMA", index)
            self.assertIn("42-day EWMA", index)
            self.assertIn("182-day EWMA", index)
            self.assertIn("Next 14 days (avg/week)", index)
            self.assertIn("1h15", index)
            self.assertIn("16.0", index)
            self.assertIn("15min", index)
            self.assertIn(">Overview</h2>", index)
            self.assertIn("hard 7d", index)
            self.assertIn("hard 42d", index)
            self.assertIn("hard 182d", index)
            self.assertIn("total 7d", index)
            self.assertIn("total 42d", index)
            self.assertIn("total 182d", index)
            self.assertIn("planned hard", index)
            self.assertIn("planned easy", index)
            self.assertIn("minutes", index)
            self.assertIn("2026-09-01", index)
            self.assertIn("2026-11-23", index)
            self.assertIn("Daily Training Report", index)
            self.assertNotIn("Planned Workouts", index)
            self.assertNotIn("Plan vs actual", index)
            self.assertNotIn("Training load", index)
            self.assertNotIn("Quality sessions", index)
            self.assertIn("Plotly.newPlot", index)
            self.assertIn("plotly.min.js", index)
            self.assertIn('class="repo"', index)
            self.assertIn(
                'href="https://github.com/markuswess/hobbyjogging"',
                index,
            )
            self.assertIn("activities with open review items are hidden", index)
            self.assertIn("Recovery and Health", index)
            self.assertIn(">Data Health</a>", index)
            self.assertIn(">Docs</a>", index)
            self.assertIn(">Lab</a>", index)
            self.assertIn(">Performance</a>", index)
            self.assertIn(">Gear</a>", index)

            recovery = (target / "recovery.html").read_text()
            self.assertIn("Recovery and Health", recovery)
            self.assertIn(
                "Recovery and Health · 2024-11-10 → 2026-11-09",
                recovery,
            )
            self.assertIn("Recovery Report — Moving Averages", recovery)
            self.assertIn("7/42/182-day averages ending 2026-11-09", recovery)
            self.assertIn("Sickness report", recovery)
            self.assertIn("No illness periods in this range", recovery)
            self.assertIn("7-day avg", recovery)
            self.assertIn("HRV", recovery)
            self.assertIn("58 ms", recovery)
            self.assertIn('<h3>Night</h3>', recovery)
            self.assertIn("2026-11-08: HRV 60 ms, RHR 45 bpm, Sleep 8h00", recovery)
            self.assertIn("2 of 730 days have wellness data", recovery)
            self.assertIn(
                '"range":["2026-11-07","2026-11-08"]',
                recovery,
            )
            self.assertIn("Plotly.newPlot", recovery)
            self.assertNotIn('class="grid"', recovery)

            activities = (target / "activities.html").read_text()
            self.assertIn("activity/run1.html", activities)
            self.assertIn("Bike", activities)
            self.assertIn("Old run", activities)
            self.assertIn("Methods", activities)
            self.assertIn("Status", activities)
            self.assertIn("planned", activities)
            self.assertIn("missed", activities)
            self.assertIn("Missed tempo", activities)
            self.assertIn("5x5 subT", activities)
            # A matched event is not duplicated, and a typed-less note is not
            # a workout row.
            self.assertNotIn("Matched easy", activities)
            self.assertNotIn("Travel note", activities)
            self.assertIn("Continuous", activities)
            self.assertIn("Base", activities)
            self.assertIn("activities are hidden by import review", activities)
            # Four rows stay below the collapse threshold.
            self.assertNotIn('class="table-toggle"', activities)
            self.assertIn(".table-toggle:not(:checked)", index)
            self.assertIn('href="event/ev-subt.html"', activities)
            self.assertIn('href="event/ev-missed.html"', activities)

            planned = (target / "event" / "ev-subt.html").read_text()
            self.assertIn("Planned 2026-11-10", planned)
            self.assertIn("5x5 subT", planned)
            self.assertIn("Planned pace times", planned)
            self.assertIn("Z3 25:00", planned)
            self.assertIn("Intervals", planned)
            self.assertIn("Threshold", planned)
            self.assertIn("12.0 km", planned)
            self.assertIn('href="../activities.html"', planned)

            # A matched event has no tab row, so its page is reached from the
            # session report's planned block and carries the approximate
            # plan-vs-actual comparison.
            matched = (target / "event" / "ev-matched.html").read_text()
            self.assertIn("Plan vs actual", matched)
            self.assertIn("approximate", matched)
            self.assertIn("../activity/run1.html", matched)
            self.assertFalse((target / "event" / "ev-marathon.html").exists())

            analysis = (target / "analysis.html").read_text()
            self.assertIn("Analysis · 2024-11-09 → 2026-11-09", analysis)
            self.assertIn(
                'href="analysis.html" class="active"',
                analysis,
            )
            self.assertIn("Weekly running volume", analysis)
            self.assertIn(
                "Weekly running time by pace zone",
                analysis,
            )
            self.assertIn("Training load and session RPE", analysis)
            self.assertIn("RPE 7d", analysis)
            self.assertIn("RPE 42d", analysis)
            self.assertIn("RPE 182d", analysis)
            self.assertIn("Pace vs heart rate", analysis)
            self.assertIn("Running streaks", analysis)
            self.assertIn("across all history", analysis)
            self.assertIn("weather on 1 of", analysis)
            # The next 14 days' plan appears on the volume, time and load
            # charts, beyond the actual window.
            self.assertIn("planned km", analysis)
            self.assertIn("planned zones", analysis)
            self.assertIn('"name":"planned run"', analysis)
            self.assertIn("avg HR (bpm)", analysis)
            self.assertNotIn("subT and LT1 intervals", analysis)
            self.assertEqual(4, analysis.count("Plotly.newPlot"))

            nsa = (target / "nsa.html").read_text()
            self.assertIn("NSA · 2025-11-10 → 2026-11-09", nsa)
            self.assertIn('href="nsa.html" class="active"', nsa)
            self.assertIn("subT EWMA Report", nsa)
            self.assertIn("<h3>Pace</h3>", nsa)
            self.assertIn("<h3>Heart rate</h3>", nsa)
            self.assertLess(
                nsa.find("subT EWMA Report"),
                nsa.find("subT and LT1 intervals"),
            )
            self.assertIn("subT and LT1 intervals", nsa)
            self.assertIn("subT Report", nsa)
            self.assertIn("No subT or LT1 sessions", nsa)
            self.assertNotIn("Weekly running volume", nsa)

            compare = (target / "compare.html").read_text()
            self.assertIn('href="compare.html" class="active"', compare)
            self.assertIn("Year comparison", compare)
            self.assertIn("2026 planned", compare)
            self.assertIn("Garmin running VO2max by year", compare)
            self.assertIn("Pace vs heart rate by year", compare)
            self.assertIn("182-day EWMA", compare)
            self.assertIn("volume", compare)
            self.assertIn("time", compare)
            self.assertIn("Training Comparison by Year", compare)
            self.assertIn("Training Comparison by Month", compare)
            self.assertIn("<h1>Compare</h1>", compare)
            self.assertIn("Plotly.newPlot", compare)

            detail = (target / "activity" / "run1.html").read_text()
            self.assertIn("Session 2026-11-08", detail)
            self.assertIn("Easy", detail)
            self.assertIn("Intervals", detail)
            self.assertIn("Work", detail)
            self.assertIn("Methods", detail)
            self.assertIn("Continuous", detail)
            self.assertIn("Targets", detail)
            self.assertIn("Base", detail)
            self.assertIn("https://intervals.icu/activities/i1", detail)
            self.assertIn(
                "https://connect.garmin.com/app/activity/2",
                detail,
            )
            self.assertIn("../index.html", detail)
            self.assertIn('href="../activities.html"', detail)
            self.assertIn('href="../event/ev-matched.html"', detail)
            self.assertIn("Weather: 12 °C, wind 3 m/s", detail)

            health = (target / "health.html").read_text()
            self.assertIn("Data coverage", health)
            self.assertIn("Weather", health)
            self.assertIn("2026", health)
            self.assertIn("Review queue", health)
            self.assertIn("field conflict", health)
            self.assertIn("avg_hr differs by 6 bpm", health)
            self.assertIn('href="activity/run2.html"', health)
            self.assertIn("2026-11-09", health)
            self.assertIn("Flagged", health)
            self.assertIn("hidden", health)
            self.assertIn("Missing data", health)

            docs = (target / "docs.html").read_text()
            self.assertIn(">Docs</a>", docs)
            self.assertIn("Reports guide", docs)
            self.assertIn("class=\"toc\"", docs)

            lab = (target / "lab.html").read_text()
            self.assertIn(">Lab</a>", lab)
            self.assertIn("Lab session ground rules", lab)
            self.assertIn("hr_efficiency_line.py", lab)
            self.assertIn("Experiment scripts", lab)
            self.assertIn("Efficiency (m/excess beat)", lab)
            self.assertIn("Metrics", lab)
            self.assertIn("class=\"toc\"", lab)

            performance = (target / "performance.html").read_text()
            self.assertIn(">Performance</a>", performance)
            self.assertIn("Upcoming races", performance)
            self.assertIn("Autumn Marathon", performance)
            self.assertIn("42.20 km", performance)
            self.assertIn("Spring 5k", performance)
            self.assertIn("Personal bests", performance)
            self.assertIn("PB progression", performance)
            self.assertIn("Riegel estimate", performance)
            self.assertIn("race/race1.html", performance)
            self.assertTrue((target / "race" / "race1.html").exists())

            race = (target / "race" / "race1.html").read_text()
            self.assertIn("Race 2026-10-30", race)
            self.assertIn("Race execution", race)
            self.assertIn("Pace zones", race)

            gear = (target / "gear.html").read_text()
            self.assertIn(">Gear</a>", gear)
            self.assertIn("Demo Shoe", gear)
            self.assertIn("Shoes", gear)
            self.assertIn("15", gear)
            self.assertIn("Retirement candidates", gear)
            self.assertIn("Plotly.newPlot", gear)
            self.assertIn("plotly.min.js", gear)

    def test_reports_flag_is_a_compatibility_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"

            build_dashboard(
                _source(),
                target,
                today=TODAY,
                reports=("overview", "planned"),
            )

            self.assertTrue((target / "docs.html").exists())
            self.assertTrue((target / "performance.html").exists())
            self.assertFalse((target / "reports.html").exists())

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

    def test_recovery_window_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"

            build_dashboard(
                _source(),
                target,
                today=TODAY,
                recovery_days=60,
            )

            recovery = (target / "recovery.html").read_text()

        self.assertIn(
            "Recovery and Health · 2026-09-11 → 2026-11-09",
            recovery,
        )
        self.assertIn("2 of 60 days have wellness data", recovery)

    def test_analysis_streaks_use_all_history(self):
        old_start = TODAY - timedelta(days=100)
        activities = [
            activity(
                id=f"old{index}",
                date=old_start + timedelta(days=index),
                duration_s=1800,
                distance_m=5000,
            )
            for index in range(10)
        ]
        activities.extend(
            activity(
                id=f"new{index}",
                date=TODAY - timedelta(days=index),
                duration_s=1800,
                distance_m=5000,
            )
            for index in range(3)
        )

        section = build_analysis_section(
            FakeSource(activities=activities),
            start=TODAY - timedelta(days=30),
            end=TODAY,
        )

        self.assertIn("<strong>Current:</strong> 3 days", section.streaks_html)
        self.assertIn("13 run days across all history", section.streaks_html)
        # A ten-day streak before the analysis window is still the longest.
        self.assertIn(str(old_start), section.streaks_html)
        self.assertIn(">10</td>", section.streaks_html)
        self.assertIn("today run", section.streaks_html)
        # The current streak is in the top rows, so it is bold with an open
        # end and there is no ellipsis.
        self.assertIn("<strong>3</strong>", section.streaks_html)
        self.assertIn("<strong>?</strong>", section.streaks_html)
        self.assertNotIn("⋮", section.streaks_html)

    def test_analysis_streaks_append_a_long_current_streak_below_the_top(self):
        activities = []
        block_start = TODAY - timedelta(days=200)

        for block in range(6):
            first = block_start - timedelta(days=block * 12)

            for index in range(10):
                activities.append(
                    activity(
                        id=f"old{block}-{index}",
                        date=first + timedelta(days=index),
                        duration_s=1800,
                        distance_m=5000,
                    )
                )

        activities.extend(
            activity(
                id=f"new{index}",
                date=TODAY - timedelta(days=index),
                duration_s=1800,
                distance_m=5000,
            )
            for index in range(3)
        )

        section = build_analysis_section(
            FakeSource(activities=activities),
            start=TODAY - timedelta(days=30),
            end=TODAY,
        )

        html = section.streaks_html

        self.assertIn("⋮", html)
        self.assertIn("<strong>3</strong>", html)
        self.assertIn("<strong>?</strong>", html)
        # The current row follows the ellipsis, after the five top streaks.
        self.assertLess(html.index("⋮"), html.index("<strong>?</strong>"))

    def test_health_tab_covers_all_history(self):
        old = TODAY - timedelta(days=100)
        activities = [
            activity(
                id="old",
                date=old,
                duration_s=1800,
            ),
            activity(
                id="new",
                date=TODAY,
                duration_s=1800,
                distance_m=5000,
                avg_hr=140,
                training_load=40,
                pace_zone_times=[600, 600, 300, 300],
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"

            build_dashboard(
                FakeSource(activities=activities),
                target,
                today=TODAY,
            )

            health = (target / "health.html").read_text()

        self.assertIn(f"Data Health · {old} → {TODAY}", health)
        self.assertIn('<div class="stat-value">2</div>', health)
        # The old activity has no load/zones/HR/distance, hence all-history
        # missing counts rather than a 14-day zero.
        self.assertIn("Activities without load", health)

    def test_recovery_plots_span_the_two_year_window(self):
        wellness = [
            WellnessDay(
                date=TODAY - timedelta(days=index),
                hrv=60.0,
                resting_hr=45.0,
                sleep_s=8 * 3600,
            )
            for index in range(760)
        ]

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "site"

            build_dashboard(
                FakeSource(wellness=wellness),
                target,
                today=TODAY,
            )

            recovery = (target / "recovery.html").read_text()

        # More than a year of points reaches the chart, not just the baseline
        # window used for its readiness bands.
        self.assertIn(
            (TODAY - timedelta(days=700)).isoformat(),
            recovery,
        )

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
            # The plan lives on the activities tab, not Overview.
            self.assertNotIn(
                "Planned Workouts",
                (target / "index.html").read_text(),
            )
            self.assertIn(
                "No wellness data",
                (target / "recovery.html").read_text(),
            )
            analysis_path = target / "analysis.html"
            self.assertTrue(analysis_path.exists())
            analysis = analysis_path.read_text()
            self.assertIn("No running volume", analysis)
            self.assertIn("No running time", analysis)

            nsa_path = target / "nsa.html"
            self.assertTrue(nsa_path.exists())
            self.assertIn(
                "No subT or LT1 sessions",
                nsa_path.read_text(),
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


class LabSectionTests(unittest.TestCase):

    def test_bench_guide_stops_at_the_idea_table(self):
        text = (
            "# Experiments\n\nRules.\n\n"
            "## Lab session ground rules\n\n- one\n\n"
            "## Ideas\n\n| Idea |\n"
        )

        self.assertEqual(
            "# Experiments\n\nRules.\n\n"
            "## Lab session ground rules\n\n- one\n",
            _bench_guide(text),
        )

    def test_bench_guide_is_empty_without_the_idea_table(self):
        self.assertEqual("", _bench_guide("# Experiments\n"))

    def test_demo_section_shows_the_bench_guide_only(self):
        section = build_lab_section(demo=True)

        self.assertTrue(section.demo)
        self.assertEqual("", section.scripts_html)
        self.assertEqual("", section.metrics_html)
        self.assertIn("Lab session ground rules", section.readme_html)
        self.assertNotIn(">Ideas<", section.readme_html)
        self.assertNotIn("Parked notes", section.readme_html)

    def test_demo_guide_does_not_link_to_the_registry(self):
        section = build_lab_section(demo=True)

        self.assertNotIn("../docs/", section.readme_html)
        self.assertIn("<code>docs/METRICS.md</code>", section.readme_html)

    def test_full_section_keeps_the_notebook_and_registry(self):
        section = build_lab_section()

        self.assertFalse(section.demo)
        self.assertIn(">Ideas<", section.readme_html)
        self.assertIn("Experiment", section.scripts_html)
        self.assertIn("Promoted", section.metrics_html)


if __name__ == "__main__":
    unittest.main()
