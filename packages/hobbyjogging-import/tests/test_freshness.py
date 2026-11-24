import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from hobbyjogging_core import connect, migrate

from hobbyjogging_import.freshness import (
    SourceRun,
    imported_strava_exports,
    last_success,
    last_success_date,
    latest_runs,
    newest_unimported_export,
    stale_sources,
    strava_exports,
)


class FreshnessTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def _run(self, source, *, status="success", started_at=None, path=None):
        parameters = {"path": path} if path else None
        self.conn.execute(
            """
            INSERT INTO import_runs
                (source, status, started_at, records_imported,
                 parameters_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                source,
                status,
                started_at or "2026-11-01 10:00:00",
                3,
                json.dumps(parameters) if parameters else None,
            ),
        )
        self.conn.commit()

    def test_latest_runs_keeps_the_newest_per_source(self):
        self._run("garmin", started_at="2026-10-01 10:00:00")
        self._run("garmin", started_at="2026-11-01 10:00:00")
        self._run("fit", status="failed", started_at="2026-11-02 10:00:00")

        runs = latest_runs(self.conn)

        self.assertEqual(
            date(2026, 11, 1),
            runs["garmin"].date,
        )
        self.assertEqual("failed", runs["fit"].status)

    def test_last_success_skips_failed_runs(self):
        self._run("runalyze", status="success", started_at="2026-10-01 10:00:00")
        self._run("runalyze", status="failed", started_at="2026-11-01 10:00:00")

        run = last_success(self.conn, "runalyze")

        self.assertEqual(date(2026, 10, 1), run.date)
        self.assertEqual(date(2026, 10, 1), last_success_date(self.conn, "runalyze"))
        self.assertIsNone(last_success(self.conn, "strava"))
        self.assertIsNone(last_success_date(self.conn, "strava"))

    def test_a_run_with_bad_parameters_is_still_a_run(self):
        self.conn.execute(
            """
            INSERT INTO import_runs (source, status, parameters_json)
            VALUES ('fit', 'success', 'not json')
            """
        )
        self.conn.commit()

        self.assertEqual({}, latest_runs(self.conn)["fit"].parameters)

    def test_strava_exports_are_newest_first(self):
        older = self.directory / "export_old.zip"
        newer = self.directory / "export_new.zip"
        older.write_bytes(b"old")
        newer.write_bytes(b"new")
        os.utime(older, (1_000_000, 1_000_000))
        os.utime(newer, (2_000_000, 2_000_000))

        self.assertEqual([newer, older], strava_exports(self.directory))
        self.assertEqual([], strava_exports(self.directory / "missing"))

    def test_only_the_newest_unimported_export_is_picked(self):
        older = self.directory / "export_old.zip"
        newer = self.directory / "export_new.zip"
        older.write_bytes(b"old")
        newer.write_bytes(b"new")
        os.utime(older, (1_000_000, 1_000_000))
        os.utime(newer, (2_000_000, 2_000_000))

        self._run("strava", path=str(newer))

        self.assertEqual({newer.resolve()}, imported_strava_exports(self.conn))
        self.assertEqual(older, newest_unimported_export(self.conn, self.directory))

        self._run("strava", path=str(older))

        self.assertIsNone(newest_unimported_export(self.conn, self.directory))

    def test_stale_sources_report_never_and_age(self):
        today = date(2026, 11, 20)
        self._run("garmin", started_at="2026-09-01 10:00:00")
        self._run("fit", started_at="2026-11-15 10:00:00")

        stale = stale_sources(
            self.conn,
            today=today,
            sources=("garmin", "fit", "runalyze"),
            threshold_days=30,
        )

        self.assertEqual(
            [("garmin", 80), ("runalyze", None)],
            stale,
        )


if __name__ == "__main__":
    unittest.main()
