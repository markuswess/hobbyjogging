import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_core import open_database
from hobbyjogging_report.cli import parse_demo_args
from hobbyjogging_report.commands import COMMANDS
from hobbyjogging_report.demo import generate_demo_database
from hobbyjogging_report.dashboard import build_dashboard
from hobbyjogging_report.sources import create_source
from hobbyjogging_report.sources.cache import CachedDataSource

TODAY = date(2026, 11, 12)

SNAPSHOT_QUERIES = {
    "activities": (
        "SELECT id, local_date, started_at_utc, sport, name, description, "
        "duration_s, elapsed_s, moving_s, distance_m, avg_hr, training_load, "
        "rpe, feel, intensity, vo2max_garmin FROM activities ORDER BY id"
    ),
    "wellness": (
        "SELECT local_date, hrv, resting_hr, sleep_s "
        "FROM wellness_days ORDER BY local_date"
    ),
    "events": (
        "SELECT id, local_date, name, type, description, duration_s, "
        "distance_m, training_load FROM events ORDER BY id"
    ),
    "equipment": (
        "SELECT id, type, name, brand, model, acquired_on, retired_on, "
        "target_distance_m FROM equipment ORDER BY id"
    ),
    "intervals": (
        "SELECT activity_id, interval_index, group_id, type, duration_s, "
        "distance_m, avg_hr, max_hr FROM activity_intervals "
        "ORDER BY activity_id, interval_index"
    ),
    "zones": (
        "SELECT activity_id, kind, zone_index, seconds "
        "FROM activity_zone_times ORDER BY activity_id, kind, zone_index"
    ),
    "activity_methods": (
        "SELECT activity_id, method FROM activity_workout_methods "
        "ORDER BY activity_id, method"
    ),
    "activity_targets": (
        "SELECT activity_id, target FROM activity_workout_targets "
        "ORDER BY activity_id, target"
    ),
    "event_zones": (
        "SELECT event_id, zone_index, zone_label, seconds "
        "FROM event_zone_times ORDER BY event_id, zone_index"
    ),
    "links": (
        "SELECT activity_id, equipment_id, role FROM activity_equipment "
        "ORDER BY activity_id"
    ),
}


def _snapshot(path: Path) -> dict[str, list[tuple]]:
    connection = sqlite3.connect(path)
    try:
        return {
            name: connection.execute(query).fetchall()
            for name, query in SNAPSHOT_QUERIES.items()
        }
    finally:
        connection.close()


class DemoGeneratorTests(unittest.TestCase):

    def test_same_seed_writes_identical_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = generate_demo_database(
                Path(tmp) / "a.db",
                today=TODAY,
                seed=7,
            )
            second = generate_demo_database(
                Path(tmp) / "b.db",
                today=TODAY,
                seed=7,
            )

            self.assertEqual(_snapshot(first.path), _snapshot(second.path))

    def test_different_seed_changes_the_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = generate_demo_database(
                Path(tmp) / "a.db",
                today=TODAY,
                seed=7,
            )
            second = generate_demo_database(
                Path(tmp) / "b.db",
                today=TODAY,
                seed=99,
            )

            self.assertNotEqual(
                _snapshot(first.path)["activities"],
                _snapshot(second.path)["activities"],
            )

    def test_counts_are_in_range_and_match_the_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )

            self.assertGreaterEqual(summary.activities, 1000)
            self.assertLessEqual(summary.activities, 1300)
            self.assertGreater(summary.wellness_days, 500)
            self.assertGreaterEqual(summary.events, 20)
            self.assertEqual(4, summary.equipment)

            connection = open_database(summary.path)
            try:
                for table, expected in (
                    ("activities", summary.activities),
                    ("wellness_days", summary.wellness_days),
                    ("events", summary.events),
                    ("equipment", summary.equipment),
                ):
                    count = connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    self.assertEqual(expected, count, table)
            finally:
                connection.close()

    def test_every_run_has_the_analysis_fields_and_complete_zones(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )
            connection = open_database(summary.path)
            try:
                runs = connection.execute(
                    """
                    SELECT id, duration_s, distance_m, avg_hr, training_load
                    FROM activities
                    WHERE sport IN ('run', 'trail_run')
                    """
                ).fetchall()

                self.assertTrue(runs)

                for run in runs:
                    self.assertGreater(run["distance_m"], 0)
                    self.assertIsNotNone(run["avg_hr"])
                    self.assertIsNotNone(run["training_load"])

                    zone_total = connection.execute(
                        """
                        SELECT COALESCE(SUM(seconds), 0)
                        FROM activity_zone_times
                        WHERE activity_id = ? AND kind = 'pace'
                        """,
                        (run["id"],),
                    ).fetchone()[0]
                    self.assertAlmostEqual(
                        run["duration_s"],
                        zone_total,
                        delta=1.0,
                    )
            finally:
                connection.close()

    def test_work_and_recovery_intervals_alternate(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )
            connection = open_database(summary.path)
            try:
                rows = connection.execute(
                    """
                    SELECT activity_id, type
                    FROM activity_intervals
                    ORDER BY activity_id, interval_index
                    """
                ).fetchall()
            finally:
                connection.close()

            by_activity: dict[str, list[str]] = {}

            for row in rows:
                by_activity.setdefault(row["activity_id"], []).append(
                    row["type"]
                )

            self.assertTrue(by_activity)

            for types in by_activity.values():
                self.assertEqual("WARMUP", types[0])
                self.assertEqual("COOLDOWN", types[-1])

                middle = types[1:-1]
                self.assertTrue(middle)
                self.assertEqual("WORK", middle[0])
                self.assertEqual("WORK", middle[-1])

                for left, right in zip(middle, middle[1:]):
                    self.assertNotEqual(left, right)

    def test_vo2max_is_a_smooth_daily_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )
            connection = open_database(summary.path)
            try:
                rows = connection.execute(
                    """
                    SELECT local_date, MIN(vo2max_garmin), MAX(vo2max_garmin)
                    FROM activities
                    WHERE vo2max_garmin IS NOT NULL
                    GROUP BY local_date
                    ORDER BY local_date
                    """
                ).fetchall()

                self.assertTrue(rows)
                self.assertTrue(
                    all(row[1] == row[2] for row in rows)
                )

                values = [row[1] for row in rows]
                self.assertLessEqual(
                    max(
                        abs(values[index + 1] - values[index])
                        for index in range(len(values) - 1)
                    ),
                    0.2,
                )
            finally:
                connection.close()

    def test_easy_runs_use_only_z1_and_z2(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )
            connection = open_database(summary.path)
            try:
                rows = connection.execute(
                    """
                    SELECT
                        a.id,
                        GROUP_CONCAT(DISTINCT m.method) AS methods,
                        SUM(
                            CASE WHEN z.zone_index > 2
                                 THEN z.seconds ELSE 0 END
                        ) AS hard
                    FROM activities a
                    JOIN activity_zone_times z
                      ON z.activity_id = a.id AND z.kind = 'pace'
                    LEFT JOIN activity_workout_methods m
                      ON m.activity_id = a.id
                    WHERE a.sport IN ('run', 'trail_run')
                    GROUP BY a.id
                    """
                ).fetchall()

                easy = 0
                quality = 0

                for row in rows:
                    methods = (row["methods"] or "").split(",")

                    if "intervals" in methods or "race" in methods:
                        self.assertGreater(row["hard"], 0)
                        quality += 1
                    else:
                        self.assertEqual(0, row["hard"])
                        easy += 1

                self.assertGreater(easy, 100)
                self.assertGreater(quality, 50)
            finally:
                connection.close()

    def test_future_plan_mirrors_the_recent_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )
            connection = open_database(summary.path)
            try:
                recent_names = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT DISTINCT name
                        FROM activities
                        WHERE local_date BETWEEN ? AND ?
                        """,
                        (
                            (TODAY - timedelta(days=28)).isoformat(),
                            TODAY.isoformat(),
                        ),
                    )
                }
                future = connection.execute(
                    """
                    SELECT e.name
                    FROM events e
                    WHERE e.local_date > ?
                      AND NOT EXISTS (
                          SELECT 1 FROM event_workout_methods m
                          WHERE m.event_id = e.id AND m.method = 'race'
                      )
                    """,
                    (TODAY.isoformat(),),
                ).fetchall()

                self.assertGreaterEqual(len(future), 40)
                self.assertTrue(
                    {row[0] for row in future} <= recent_names
                )
                self.assertTrue(
                    any(
                        "subT" in row[0] or "LT1" in row[0]
                        for row in future
                    )
                )
            finally:
                connection.close()

    def test_races_are_in_the_future_and_events_extend_the_horizon(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )
            connection = open_database(summary.path)
            try:
                races = connection.execute(
                    """
                    SELECT e.local_date, e.name
                    FROM events e
                    JOIN event_workout_methods m ON m.event_id = e.id
                    WHERE m.method = 'race' AND e.excluded_at IS NULL
                    ORDER BY e.local_date
                    """
                ).fetchall()

                self.assertEqual(2, len(races))

                for race in races:
                    day = date.fromisoformat(race["local_date"])
                    self.assertGreater(day, TODAY)
                    self.assertLessEqual(day, TODAY + timedelta(days=180))

                last_plan = connection.execute(
                    "SELECT MAX(local_date) FROM events WHERE excluded_at IS NULL"
                ).fetchone()[0]
                self.assertGreaterEqual(
                    date.fromisoformat(last_plan),
                    TODAY + timedelta(days=90),
                )
            finally:
                connection.close()

    def test_no_source_records_or_open_review_items_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )
            connection = open_database(summary.path)
            try:
                self.assertEqual(
                    0,
                    connection.execute(
                        "SELECT COUNT(*) FROM source_records"
                    ).fetchone()[0],
                )
                self.assertEqual(
                    0,
                    connection.execute(
                        "SELECT COUNT(*) FROM review_items "
                        "WHERE status = 'open'"
                    ).fetchone()[0],
                )
            finally:
                connection.close()

    def test_review_items_are_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
                with_review_items=True,
            )
            connection = open_database(summary.path)
            try:
                self.assertEqual(
                    2,
                    connection.execute(
                        "SELECT COUNT(*) FROM review_items "
                        "WHERE status = 'open'"
                    ).fetchone()[0],
                )
            finally:
                connection.close()

    def test_database_is_small(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )

            self.assertLess(summary.path.stat().st_size, 5 * 1024 * 1024)

    def test_existing_file_is_refused_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.db"
            generate_demo_database(path, today=TODAY)

            with self.assertRaises(FileExistsError):
                generate_demo_database(path, today=TODAY)

            summary = generate_demo_database(
                path,
                today=TODAY,
                force=True,
            )
            self.assertTrue(summary.path.exists())

    def test_generated_database_builds_a_badged_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_demo_database(
                Path(tmp) / "demo.db",
                today=TODAY,
            )
            site = Path(tmp) / "site"
            source = create_source(database_path=summary.path)
            cached = CachedDataSource(source)
            timings: dict[str, float] = {}

            try:
                build_dashboard(
                    cached,
                    site,
                    days=14,
                    activity_limit=20,
                    chart_days=90,
                    today=TODAY,
                    demo_label="Synthetic demo data",
                    timings=timings,
                )
            finally:
                source.close()

            self.assertLessEqual(cached.query_counts["activities"], 10)
            self.assertLessEqual(
                cached.query_counts["activity_intervals"],
                1200,
            )
            self.assertLessEqual(cached.query_counts["activity_laps"], 40)
            self.assertGreaterEqual(
                set(timings),
                {
                    "data",
                    "recovery",
                    "analysis",
                    "nsa",
                    "compare",
                    "performance",
                    "reports",
                    "health+gear",
                    "pages",
                },
            )

            for name in (
                "index.html",
                "activities.html",
                "analysis.html",
                "nsa.html",
                "compare.html",
                "recovery.html",
                "performance.html",
                "gear.html",
                "docs.html",
                "lab.html",
                "health.html",
            ):
                self.assertTrue((site / name).exists(), name)

            markers = {
                "index.html": ("Training overview", "Daily Training Report"),
                "activities.html": ("Activities", "Easy"),
                "analysis.html": ("Analysis", "Pace vs heart rate"),
                "nsa.html": ("NSA", "subT"),
                "compare.html": ("Compare", "Year comparison"),
                "recovery.html": ("Recovery Report", "Data completeness"),
                "performance.html": (
                    "Upcoming races",
                    "Personal bests",
                    "PB progression",
                    "Equivalent times",
                    "PB pace",
                ),
                "gear.html": ("Gear", "Coverage"),
                "docs.html": ("Reports guide", "hobbyjogging-reports"),
                "lab.html": (
                    "Lab session ground rules",
                    "bench rules only",
                ),
                "health.html": ("Data Health", "Open review items"),
            }

            for name, required in markers.items():
                page = (site / name).read_text()
                self.assertGreater(len(page), 1000, name)
                for marker in required:
                    self.assertIn(marker, page, name)

            index = (site / "index.html").read_text()
            self.assertIn("Synthetic demo data", index)
            performance = (site / "performance.html").read_text()
            self.assertIn("Upcoming races", performance)

            health = (site / "health.html").read_text()
            self.assertIn("The review queue is empty.", health)
            self.assertIn("Synthetic demo data", health)

            # The public demo must not publish the lab notebook, the experiment
            # scripts, or the metric registry: they carry this athlete's own
            # results.
            lab = (site / "lab.html").read_text()
            for leaked in (
                "Parked notes",
                "Efficiency frontier",
                "hr_efficiency_line.py",
                "median RHR 51",
                "<h2>Experiment scripts</h2>",
                "<h2>Metrics</h2>",
            ):
                self.assertNotIn(leaked, lab)


class DemoCommandTests(unittest.TestCase):

    def test_command_is_registered_without_a_source(self):
        command = COMMANDS["demo-db"]

        self.assertFalse(command.needs_source)
        self.assertIn("--out", command.usage)

    def test_parse_defaults_and_validation(self):
        parsed = parse_demo_args(["--out", "build/demo.db"])

        self.assertEqual(
            ("build/demo.db", 48, 7, None, False, False),
            parsed,
        )

        with self.assertRaises(ValueError):
            parse_demo_args([])

        with self.assertRaises(ValueError):
            parse_demo_args(["--out", "x.db", "--months", "0"])

    def test_parse_all_options(self):
        parsed = parse_demo_args(
            [
                "--out", "x.db",
                "--months", "12",
                "--seed", "3",
                "--today", "2026-11-12",
                "--with-review-items",
                "--force",
            ]
        )

        self.assertEqual(
            ("x.db", 12, 3, TODAY, True, True),
            parsed,
        )


if __name__ == "__main__":
    unittest.main()
