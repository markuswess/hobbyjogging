import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core import connect, migrate, open_database

from hobbyjogging_maintenance.cli import _print_run
from hobbyjogging_maintenance.registry import get_task, preserve_registry, task
from hobbyjogging_maintenance.runner import run_task


class SnapshotTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "training.db"
        self.conn = open_database(self.path)
        self.addCleanup(self.conn.close)

    def _write_task(self, task_id="snapshot_write", kind="recompute"):
        @task(task_id, kind=kind)
        def write(context):
            context.connection.execute(
                "INSERT OR REPLACE INTO activities (id, local_date, sport) "
                "VALUES ('after', '2026-01-01', 'run')"
            )
            context.count("written")

        return get_task(task_id)

    def _snapshots(self):
        return sorted(self.path.parent.glob(f"{self.path.name}.bak-*"))

    def test_real_run_snapshots_before_the_task(self):
        with preserve_registry():
            item = self._write_task()
            result = run_task(self.conn, item)

        self.assertEqual("ok", result.status)
        self.assertIsNotNone(result.snapshot)
        self.assertTrue(result.snapshot.is_file())
        self.assertEqual(1, len(self._snapshots()))

        snapshot = sqlite3.connect(result.snapshot)
        self.addCleanup(snapshot.close)
        self.assertEqual(
            "ok", snapshot.execute("PRAGMA integrity_check").fetchone()[0]
        )
        self.assertIsNone(
            snapshot.execute(
                "SELECT 1 FROM activities WHERE id = 'after'"
            ).fetchone()
        )
        self.assertIsNotNone(
            self.conn.execute(
                "SELECT 1 FROM activities WHERE id = 'after'"
            ).fetchone()
        )

    def test_dry_run_writes_no_snapshot(self):
        with preserve_registry():
            item = self._write_task()
            result = run_task(self.conn, item, dry_run=True)

        self.assertIsNone(result.snapshot)
        self.assertEqual([], self._snapshots())
        self.assertIsNone(
            self.conn.execute(
                "SELECT 1 FROM activities WHERE id = 'after'"
            ).fetchone()
        )

    def test_retention_keeps_the_last_five(self):
        with preserve_registry():
            item = self._write_task()
            for _ in range(6):
                run_task(self.conn, item)

        self.assertEqual(5, len(self._snapshots()))

    def test_a_skipped_backfill_writes_no_snapshot(self):
        with preserve_registry():
            item = self._write_task("snapshot_once_v1", kind="backfill")
            first = run_task(self.conn, item)
            second = run_task(self.conn, item)

        self.assertIsNotNone(first.snapshot)
        self.assertEqual("skipped", second.status)
        self.assertIsNone(second.snapshot)
        self.assertEqual(1, len(self._snapshots()))

    def test_an_in_memory_database_has_no_snapshot(self):
        memory = connect(":memory:")
        self.addCleanup(memory.close)
        migrate(memory)

        with preserve_registry():
            item = self._write_task()
            result = run_task(memory, item)

        self.assertEqual("ok", result.status)
        self.assertIsNone(result.snapshot)

    def test_a_snapshot_failure_aborts_the_run(self):
        with preserve_registry():
            item = self._write_task()
            with patch(
                "hobbyjogging_maintenance.runner.create_snapshot",
                side_effect=OSError("disk full"),
            ):
                result = run_task(self.conn, item)

        self.assertEqual("failed", result.status)
        self.assertIn("snapshot failed", result.error)
        self.assertIsNone(
            self.conn.execute(
                "SELECT 1 FROM activities WHERE id = 'after'"
            ).fetchone()
        )

    def test_the_cli_prints_the_snapshot_path(self):
        with preserve_registry():
            item = self._write_task()
            result = run_task(self.conn, item)

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            _print_run(result)

        self.assertIn(f"snapshot: {result.snapshot}", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
