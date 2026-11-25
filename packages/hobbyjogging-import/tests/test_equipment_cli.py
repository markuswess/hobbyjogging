import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import open_database
from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.equipment_cli import run_equipment


class EquipmentCliTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "equipment.db"
        connection = open_database(self.database)
        connection.close()

    def _run(self, *argv):
        parser = build_parser()
        args = parser.parse_args(list(argv))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_equipment(args, parser)
        return code, out.getvalue()

    def _rows(self):
        connection = open_database(self.database)
        try:
            return connection.execute(
                "SELECT * FROM equipment ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

    def _log(self):
        connection = open_database(self.database)
        try:
            return connection.execute(
                "SELECT field, old_json, new_json, source, note "
                "FROM edit_log ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

    def test_add_list_edit_retire_round_trip(self):
        code, out = self._run(
            "equipment", "--database", str(self.database),
            "add", "Pegasus 40",
            "--brand", "Nike",
            "--model", "Pegasus 40",
            "--acquired", "2026-01-02",
            "--target-distance", "800km",
            "--notes", "daily",
        )
        self.assertEqual(0, code)
        self.assertIn("equipment added: manual:equipment:pegasus-40", out)

        row = self._rows()[0]
        self.assertEqual("manual:equipment:pegasus-40", row["id"])
        self.assertEqual("Nike", row["brand"])
        self.assertEqual(800000.0, row["target_distance_m"])
        self.assertEqual(1, row["is_manual"])
        self.assertEqual(7, len(self._log()))

        code, out = self._run(
            "equipment", "--database", str(self.database), "list"
        )
        self.assertEqual(0, code)
        self.assertIn("Pegasus 40", out)
        self.assertIn("manual", out)

        code, out = self._run(
            "equipment", "--database", str(self.database),
            "edit", "Pegasus 40", "--notes", "retired from daily",
        )
        self.assertEqual(0, code)
        self.assertIn("equipment updated", out)
        self.assertEqual("retired from daily", self._rows()[0]["notes"])

        code, out = self._run(
            "equipment", "--database", str(self.database),
            "retire", "Pegasus 40", "--on", "2026-11-01",
        )
        self.assertEqual(0, code)
        self.assertEqual("2026-11-01", self._rows()[0]["retired_on"])

        code, out = self._run(
            "equipment", "--database", str(self.database),
            "history", "Pegasus 40",
        )
        self.assertEqual(0, code)
        self.assertIn("notes", out)
        self.assertIn("retired_on", out)

    def test_a_duplicate_normalized_name_is_refused(self):
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Pegasus 40", "--brand", "Nike",
        )

        code, out = self._run(
            "equipment", "--database", str(self.database),
            "add", "  pegasus   40 ", "--brand", "Nike",
        )

        self.assertEqual(1, code)
        self.assertIn("already exists", out)
        self.assertEqual(1, len(self._rows()))

    def test_dry_run_writes_nothing(self):
        code, out = self._run(
            "equipment", "--database", str(self.database),
            "add", "Dry shoe", "--dry-run",
        )

        self.assertEqual(0, code)
        self.assertIn("Dry run", out)
        self.assertEqual([], self._rows())
        self.assertEqual([], self._log())

    def test_edit_and_retire_by_id_work(self):
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Pegasus 40",
        )
        equipment_id = self._rows()[0]["id"]

        self._run(
            "equipment", "--database", str(self.database),
            "edit", equipment_id, "--name", "Pegasus 41",
        )
        self.assertEqual("Pegasus 41", self._rows()[0]["name"])

        self._run(
            "equipment", "--database", str(self.database),
            "retire", equipment_id,
        )
        self.assertIsNotNone(self._rows()[0]["retired_on"])


if __name__ == "__main__":
    unittest.main()
