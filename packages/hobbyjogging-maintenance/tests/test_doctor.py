import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core import SCHEMA_VERSION, connect, migrate

from hobbyjogging_maintenance.doctor import (
    format_doctor,
    initialize,
    run_doctor,
)
from hobbyjogging_maintenance.registry import all_tasks

SOURCES = """
[sources.fit]
enabled = true

[sources.garmin]
enabled = true

[sources.intervals]
enabled = true

[sources.runalyze]
enabled = true

[sources.strava]
enabled = true
"""


class InitializeTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_creates_and_migrates_then_is_a_noop(self):
        path = self.root / "db" / "training.db"
        fit_dir = self.root / "fit"

        created_path, version, created = initialize(path, fit_dir=fit_dir)

        self.assertTrue(created)
        self.assertEqual(path.resolve(), created_path)
        self.assertEqual(SCHEMA_VERSION, version)
        self.assertTrue(fit_dir.is_dir())

        _, version, created = initialize(path, fit_dir=fit_dir)

        self.assertFalse(created)
        self.assertEqual(SCHEMA_VERSION, version)


class DoctorTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root / "training.db"
        self.fit_dir = self.root / "fit"
        self.fit_dir.mkdir()
        self.strava_dir = self.root / "strava"
        self.strava_dir.mkdir()
        self.sources = self.root / "sources.toml"
        self.sources.write_text(SOURCES, encoding="utf-8")

    def _doctor(self, *, probe=None, today=date(2026, 11, 24), **kwargs):
        with patch(
            "hobbyjogging_maintenance.doctor.garmin_api_key",
            return_value=kwargs.pop("garmin_key", "key"),
        ), patch(
            "hobbyjogging_maintenance.doctor.intervals_credentials",
            return_value=kwargs.pop("intervals", ("athlete", "key")),
        ), patch(
            "hobbyjogging_maintenance.doctor.runalyze_api_key",
            return_value=kwargs.pop("runalyze_key", "key"),
        ):
            return run_doctor(
                database=self.database,
                fit_dir=self.fit_dir,
                strava_dir=self.strava_dir,
                sources_path=self.sources,
                today=today,
                probe=probe,
                **kwargs,
            )

    def test_a_fresh_database_points_at_sync(self):
        initialize(self.database, fit_dir=self.fit_dir)

        report = self._doctor(network=False)

        statuses = {check.name: check.status for check in report.checks}
        self.assertEqual("warn", statuses["strava"])
        self.assertEqual("skip", statuses["liveness"])
        self.assertTrue(report.database_empty)
        self.assertNotEqual("./dashboard.sh", report.next_command)
        self.assertEqual("./sync.sh", report.next_command)

    def test_a_missing_database_points_at_init(self):
        report = self._doctor(network=False)

        statuses = {check.name: check.status for check in report.checks}
        self.assertEqual("warn", statuses["database"])
        self.assertEqual("skip", statuses["schema"])
        self.assertEqual("./init.sh", report.next_command)

    def test_an_old_schema_points_at_init(self):
        connection = connect(self.database)
        migrate(connection)
        connection.execute("PRAGMA user_version = 23")
        connection.commit()
        connection.close()

        report = self._doctor(network=False)

        statuses = {check.name: check.status for check in report.checks}
        self.assertEqual("warn", statuses["schema"])
        self.assertEqual("./init.sh", report.next_command)

    def test_missing_credentials_are_warnings(self):
        initialize(self.database, fit_dir=self.fit_dir)

        report = self._doctor(
            network=False,
            garmin_key=None,
            intervals=(None, None),
            runalyze_key=None,
        )

        checks = {check.name: check for check in report.checks}
        for name in ("garmin", "intervals", "runalyze"):
            self.assertEqual("warn", checks[name].status)
            self.assertTrue(checks[name].hint)
        self.assertFalse(report.failed)

    def test_a_failed_liveness_probe_is_a_warning(self):
        initialize(self.database, fit_dir=self.fit_dir)

        report = self._doctor(probe=lambda source, timeout: (False, "down"))

        checks = {check.name: check for check in report.checks}
        self.assertEqual("warn", checks["garmin api"].status)
        self.assertIn("down", checks["garmin api"].detail)

    def test_all_applied_and_fresh_points_at_the_dashboard(self):
        initialize(self.database, fit_dir=self.fit_dir)
        connection = connect(self.database)
        connection.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-11-01', 'run')"
        )
        for task in all_tasks():
            if task.applied_once:
                connection.execute(
                    "INSERT INTO data_migrations (id) VALUES (?)",
                    (task.id,),
                )
        for source in ("fit", "garmin", "intervals", "runalyze"):
            connection.execute(
                """
                INSERT INTO import_runs
                    (source, status, started_at, finished_at)
                VALUES (?, 'success', '2026-11-20 10:00:00',
                        '2026-11-20 10:01:00')
                """,
                (source,),
            )
        (self.strava_dir / "export_1.zip").write_bytes(b"zip")
        export_path = self.strava_dir / "export_1.zip"
        connection.execute(
            """
            INSERT INTO import_runs (source, status, started_at, parameters_json)
            VALUES ('strava', 'success', '2026-11-20 10:00:00', ?)
            """,
            ('{"path": "' + str(export_path) + '"}',),
        )
        connection.commit()
        connection.close()

        report = self._doctor(network=False)

        statuses = {check.name: check.status for check in report.checks}
        self.assertEqual("ok", statuses["backfills"])
        self.assertEqual("ok", statuses["freshness"])
        self.assertEqual("./dashboard.sh", report.next_command)

    def test_pending_backfills_are_reported(self):
        initialize(self.database, fit_dir=self.fit_dir)

        report = self._doctor(network=False)

        checks = {check.name: check for check in report.checks}
        self.assertEqual("warn", checks["backfills"].status)
        self.assertIn("pending:", checks["backfills"].detail)

    def test_a_waiting_strava_export_is_reported(self):
        initialize(self.database, fit_dir=self.fit_dir)
        connection = connect(self.database)
        for task in all_tasks():
            if task.applied_once:
                connection.execute(
                    "INSERT INTO data_migrations (id) VALUES (?)",
                    (task.id,),
                )
        for source in ("fit", "garmin", "intervals", "runalyze"):
            connection.execute(
                """
                INSERT INTO import_runs
                    (source, status, started_at, finished_at)
                VALUES (?, 'success', '2026-11-20 10:00:00',
                        '2026-11-20 10:01:00')
                """,
                (source,),
            )
        connection.commit()
        connection.close()
        (self.strava_dir / "export_1.zip").write_bytes(b"zip")

        report = self._doctor(network=False)

        checks = {check.name: check for check in report.checks}
        self.assertIn("strava export waiting", checks["freshness"].detail)

    def test_format_names_the_next_command(self):
        report = self._doctor(network=False)

        text = format_doctor(report)

        self.assertIn("hobbyjogging doctor", text)
        self.assertIn("Next:", text)
        self.assertIn("database", text)


if __name__ == "__main__":
    unittest.main()
