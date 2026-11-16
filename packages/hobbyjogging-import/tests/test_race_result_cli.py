import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import TrainingWriter, open_database
from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.race_result_cli import run_race_result


class RaceResultCliTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "race.db"

        seed = open_database(self.database)
        self.addCleanup(seed.close)
        writer = TrainingWriter(seed)
        writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-04-12",
                "sport": "run",
                "duration_s": 9469,
                "distance_m": 42450,
                "name": "Linz Marathon",
            },
            source="fit",
            source_record_id=None,
        )
        seed.commit()

    def _run(self, *argv):
        parser = build_parser()
        args = parser.parse_args(list(argv))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_race_result(args, parser)
        return code, out.getvalue()

    def _rows(self):
        connection = open_database(self.database)
        try:
            return connection.execute(
                "SELECT activity_id, official_distance_m, official_time_s, "
                "place_total, participants_total, officially_measured, "
                "priority_level, status, source, excluded_at "
                "FROM race_results"
            ).fetchall()
        finally:
            connection.close()

    def test_add_writes_the_official_result(self):
        code, out = self._run(
            "race-result", "--database", str(self.database),
            "add", "a1", "--distance", "42.195km",
            "--time", "2:37:49",
            "--name", "Linz Marathon",
            "--place", "412",
            "--participants", "3100",
            "--officially-measured",
            "--priority", "A",
        )

        self.assertEqual(0, code)
        self.assertIn("race result saved", out)

        row = self._rows()[0]
        self.assertEqual("a1", row["activity_id"])
        self.assertAlmostEqual(42195.0, row["official_distance_m"])
        self.assertAlmostEqual(9469.0, row["official_time_s"])
        self.assertEqual(412, row["place_total"])
        self.assertEqual(3100, row["participants_total"])
        self.assertEqual(1, row["officially_measured"])
        self.assertEqual("A", row["priority_level"])
        self.assertEqual("completed", row["status"])
        self.assertEqual("manual", row["source"])
        self.assertIsNone(row["excluded_at"])

    def test_a_second_add_replaces_the_row(self):
        for time in ("2:40:00", "2:37:49"):
            self._run(
                "race-result", "--database", str(self.database),
                "add", "a1", "--time", time,
            )

        rows = self._rows()
        self.assertEqual(1, len(rows))
        self.assertAlmostEqual(9469.0, rows[0]["official_time_s"])

    def test_list_prints_the_stored_rows(self):
        self._run(
            "race-result", "--database", str(self.database),
            "add", "a1", "--distance", "42.195km", "--time", "2:37:49",
        )

        code, out = self._run(
            "race-result", "--database", str(self.database), "list",
        )

        self.assertEqual(0, code)
        self.assertIn("42.20 km", out)
        self.assertIn("2:37:49", out)

    def test_remove_soft_excludes(self):
        self._run(
            "race-result", "--database", str(self.database),
            "add", "a1", "--time", "2:37:49",
        )

        code, _ = self._run(
            "race-result", "--database", str(self.database),
            "remove", "a1",
        )

        self.assertEqual(0, code)
        self.assertIsNotNone(self._rows()[0]["excluded_at"])

    def test_an_unknown_activity_is_an_error(self):
        with self.assertRaises(SystemExit):
            self._run(
                "race-result", "--database", str(self.database),
                "add", "nope", "--time", "2:37:49",
            )


if __name__ == "__main__":
    unittest.main()
