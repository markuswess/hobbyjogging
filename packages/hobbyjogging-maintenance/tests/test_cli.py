import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import SCHEMA_VERSION, open_database

from hobbyjogging_maintenance.cli import main


class MaintenanceCliTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "maintenance.db"
        open_database(self.database).close()

    def _main(self, *argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([*argv, "--database", str(self.database)])
        return code, output.getvalue()

    def test_list_shows_pending_tasks(self):
        code, output = self._main("list")

        self.assertEqual(0, code)
        self.assertIn("event_zones_v1", output)
        self.assertIn("workout_classification_v1", output)
        self.assertIn("pending", output)

    def test_list_filters_by_kind(self):
        code, output = self._main("list", "--kind", "recompute")

        self.assertEqual(0, code)
        self.assertIn("No tasks registered.", output)

    def test_status_reports_the_schema_version(self):
        code, output = self._main("status")

        self.assertEqual(0, code)
        self.assertIn(f"Schema version: {SCHEMA_VERSION}", output)
        self.assertIn("Pending backfills:", output)
        self.assertIn("No maintenance runs yet.", output)

    def test_run_applies_a_backfill_and_lists_it(self):
        code, output = self._main("run", "event_zones_v1")

        self.assertEqual(0, code)
        self.assertIn("event_zones_v1 (backfill)", output)
        self.assertIn("No events in scope.", output)
        self.assertIn("Applied.", output)

        _, listing = self._main("list")
        self.assertIn("applied", listing)

        _, status = self._main("status")
        self.assertIn("Recent runs:", status)
        self.assertIn("event_zones_v1", status)
        self.assertIn("write", status)

    def test_second_run_is_skipped_unless_forced(self):
        self._main("run", "event_zones_v1")

        code, output = self._main("run", "event_zones_v1")
        self.assertEqual(0, code)
        self.assertIn("already applied", output)

        code, output = self._main("run", "event_zones_v1", "--force")
        self.assertEqual(0, code)
        self.assertIn("Applied.", output)

    def test_dry_run_rolls_back(self):
        code, output = self._main("run", "event_zones_v1", "--dry-run")

        self.assertEqual(0, code)
        self.assertIn("Dry run: transaction rolled back", output)

        _, status = self._main("status")
        self.assertIn("dry-run", status)
        self.assertIn("Applied backfills: 0", status)

    def test_all_runs_pending_backfills(self):
        code, output = self._main("run", "--all")

        self.assertEqual(0, code)
        self.assertIn("event_zones_v1 (backfill)", output)
        self.assertIn("workout_classification_v1 (backfill)", output)

        _, status = self._main("status")
        self.assertNotIn("Pending backfills:", status)

    def test_output_is_rejected_for_all(self):
        with self.assertRaises(SystemExit) as raised:
            self._main("run", "--all", "--output", "x.txt")

        self.assertEqual(2, raised.exception.code)

    def test_missing_task_arguments_are_rejected(self):
        with self.assertRaises(SystemExit) as raised:
            self._main("run")

        self.assertEqual(2, raised.exception.code)

    def test_unknown_task_is_rejected(self):
        with self.assertRaises(SystemExit) as raised:
            self._main("run", "nope_v1")

        self.assertEqual(2, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
