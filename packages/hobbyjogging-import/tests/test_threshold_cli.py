import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from hobbyjogging_core import TrainingRepository, open_database

from hobbyjogging_import.cli import main
from hobbyjogging_import.values import parse_pace_mps


class PaceParserTests(unittest.TestCase):

    def test_minutes_per_km(self):
        self.assertAlmostEqual(1000.0 / 270.0, parse_pace_mps("4:30"))

    def test_explicit_mps(self):
        self.assertAlmostEqual(3.7, parse_pace_mps("3.7mps"))
        self.assertAlmostEqual(3.7, parse_pace_mps("3.7 m/s"))
        self.assertAlmostEqual(3.7, parse_pace_mps("3.7"))

    def test_minutes_per_km_with_suffix(self):
        self.assertAlmostEqual(1000.0 / 300.0, parse_pace_mps("5:00/km"))

    def test_invalid_values_are_rejected(self):
        for text in ("", "0", "abc", "0:00"):
            with self.assertRaises(ValueError):
                parse_pace_mps(text)


class ThresholdCommandTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / "thresholds.db"

    def _run(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(
                ["threshold", "--database", str(self.database), *args]
            )
        return code, output.getvalue()

    def test_add_and_list_a_manual_snapshot(self):
        code, text = self._run(
            "add",
            "--sport",
            "run",
            "--from",
            "2026-01-01",
            "--max-hr",
            "190",
            "--lthr",
            "170",
            "--threshold-pace",
            "4:30",
        )
        self.assertEqual(0, code)
        self.assertIn("threshold saved", text)

        code, text = self._run("list")
        self.assertEqual(0, code)
        self.assertIn("run", text)
        self.assertIn("2026-01-01", text)
        self.assertIn("190", text)
        self.assertIn("170", text)
        self.assertIn("4:30 /km", text)
        self.assertIn("manual", text)

    def test_a_re_add_for_the_same_date_replaces_the_values(self):
        self._run("add", "--from", "2026-01-01", "--lthr", "170")
        self._run("add", "--from", "2026-01-01", "--lthr", "172")

        connection = open_database(self.database)
        try:
            rows = TrainingRepository(connection).athlete_thresholds()
        finally:
            connection.close()

        self.assertEqual(1, len(rows))
        self.assertEqual(172, rows[0].lthr)
        self.assertEqual("manual", rows[0].source)

    def test_add_requires_at_least_one_value(self):
        with self.assertRaises(SystemExit):
            self._run("add")

    def test_list_filters_by_sport(self):
        self._run("add", "--sport", "run", "--lthr", "170")
        self._run("add", "--sport", "ride", "--lthr", "160")

        _, text = self._run("list", "--sport", "ride")

        self.assertIn("ride", text)
        self.assertNotIn("run", text)


if __name__ == "__main__":
    unittest.main()
