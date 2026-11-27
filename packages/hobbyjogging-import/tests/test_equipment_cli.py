import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import TrainingWriter, open_database
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


    def _seed_activity(self, activity_id="ride-1", sport="ride"):
        connection = open_database(self.database)
        try:
            writer = TrainingWriter(connection)
            writer.upsert_activity(
                activity_id,
                {
                    "local_date": "2026-10-01",
                    "sport": sport,
                    "distance_m": 10000,
                    "duration_s": 3600,
                },
                source="fit",
                source_record_id=None,
            )
            connection.commit()
        finally:
            connection.close()

    def _links(self):
        connection = open_database(self.database)
        try:
            return [
                tuple(row)
                for row in connection.execute(
                    """
                    SELECT equipment_id, role, source, is_manual
                    FROM activity_equipment
                    WHERE activity_id = 'ride-1'
                    ORDER BY role, equipment_id
                    """
                )
            ]
        finally:
            connection.close()

    def test_link_appends_secondary_and_keeps_the_primary(self):
        self._seed_activity()
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Katy", "--type", "bike",
        )
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Bob", "--type", "other",
        )
        self._run(
            "equipment", "--database", str(self.database),
            "link", "ride-1", "Katy", "--role", "primary",
        )

        code, out = self._run(
            "equipment", "--database", str(self.database),
            "link", "ride-1", "Bob",
        )

        self.assertEqual(0, code)
        self.assertIn("equipment linked", out)
        self.assertEqual(
            [
                ("manual:equipment:katy", "primary", "manual", 1),
                ("manual:equipment:bob", "secondary", "manual", 1),
            ],
            self._links(),
        )

        code, out = self._run(
            "equipment", "--database", str(self.database),
            "link", "ride-1", "Bob",
        )
        self.assertEqual(0, code)
        self.assertIn("already linked", out)
        self.assertEqual(2, len(self._links()))

    def test_link_writes_an_activity_edit_log_row(self):
        self._seed_activity()
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Bob", "--type", "other",
        )

        self._run(
            "equipment", "--database", str(self.database),
            "link", "ride-1", "Bob",
        )

        log = self._log()[-1]
        self.assertEqual("equipment", log["field"])
        self.assertIn("manual:equipment:bob", log["new_json"])
        self.assertIn("equipment link", log["note"])

    def test_unlink_removes_only_that_link(self):
        self._seed_activity()
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Katy", "--type", "bike",
        )
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Bob", "--type", "other",
        )
        self._run(
            "equipment", "--database", str(self.database),
            "link", "ride-1", "Katy", "--role", "primary",
        )
        self._run(
            "equipment", "--database", str(self.database),
            "link", "ride-1", "Bob",
        )

        code, out = self._run(
            "equipment", "--database", str(self.database),
            "unlink", "ride-1", "Bob",
        )

        self.assertEqual(0, code)
        self.assertIn("equipment unlinked", out)
        self.assertEqual(
            [("manual:equipment:katy", "primary", "manual", 1)],
            self._links(),
        )

        code, out = self._run(
            "equipment", "--database", str(self.database),
            "unlink", "ride-1", "Bob",
        )
        self.assertIn("not linked", out)

    def test_a_dry_run_link_writes_nothing(self):
        self._seed_activity()
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Bob", "--type", "other",
        )
        before = len(self._log())

        code, out = self._run(
            "equipment", "--database", str(self.database),
            "link", "ride-1", "Bob", "--dry-run",
        )

        self.assertEqual(0, code)
        self.assertIn("Dry run", out)
        self.assertEqual([], self._links())
        self.assertEqual(before, len(self._log()))

    def test_unknown_link_targets_error(self):
        self._seed_activity()
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Bob", "--type", "other",
        )

        with self.assertRaises(SystemExit):
            self._run(
                "equipment", "--database", str(self.database),
                "link", "nope", "Bob",
            )
        with self.assertRaises(SystemExit):
            self._run(
                "equipment", "--database", str(self.database),
                "link", "ride-1", "nope",
            )

    def test_a_link_survives_an_activity_reimport(self):
        self._seed_activity()
        self._run(
            "equipment", "--database", str(self.database),
            "add", "Bob", "--type", "other",
        )
        self._run(
            "equipment", "--database", str(self.database),
            "link", "ride-1", "Bob",
        )

        connection = open_database(self.database)
        try:
            writer = TrainingWriter(connection)
            writer.upsert_activity(
                "ride-1",
                {
                    "local_date": "2026-10-01",
                    "sport": "ride",
                    "distance_m": 10100,
                    "duration_s": 3610,
                },
                source="intervals",
                source_record_id=None,
            )
            connection.commit()
        finally:
            connection.close()

        self.assertEqual(
            [("manual:equipment:bob", "secondary", "manual", 1)],
            self._links(),
        )


if __name__ == "__main__":
    unittest.main()
