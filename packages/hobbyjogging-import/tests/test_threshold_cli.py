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
        self.counter = 0

    def _activity(self, day, *, sport="run", excluded=False):
        self.counter += 1
        connection = open_database(self.database)
        try:
            connection.execute(
                """
                INSERT INTO activities
                    (id, local_date, sport, excluded_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    f"a{self.counter}",
                    day,
                    sport,
                    "2026-01-01" if excluded else None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

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
        self.assertIn("Zones apply from 2026-01-01", text)

        code, text = self._run("list")
        self.assertEqual(0, code)
        self.assertIn("run", text)
        self.assertIn("2026-01-01", text)
        self.assertIn("190", text)
        self.assertIn("170", text)
        self.assertIn("4:30 /km", text)
        self.assertIn("manual", text)

    def test_from_first_anchors_on_the_earliest_activity_of_the_sport(self):
        self._activity("2020-01-01")
        self._activity("2019-06-01")
        self._activity("2018-01-01", sport="ride")

        code, text = self._run(
            "add",
            "--sport",
            "run",
            "--from",
            "first",
            "--lthr",
            "170",
        )

        self.assertEqual(0, code)
        self.assertIn("threshold saved: run from 2019-06-01", text)
        self.assertIn("no earlier run activity stays unzoned", text)

        connection = open_database(self.database)
        try:
            rows = TrainingRepository(connection).athlete_thresholds()
        finally:
            connection.close()
        self.assertEqual(1, len(rows))
        self.assertEqual("2019-06-01", rows[0].effective_from.isoformat())

    def test_earlier_unzoned_activities_are_counted_for_the_sport(self):
        self._activity("2020-01-01")
        self._activity("2020-06-01")
        self._activity("2020-03-01", excluded=True)
        self._activity("2020-03-01", sport="ride")

        code, text = self._run(
            "add",
            "--sport",
            "run",
            "--from",
            "2021-01-01",
            "--lthr",
            "170",
        )

        self.assertEqual(0, code)
        self.assertIn(
            "Zones apply from 2021-01-01; 2 earlier run activities stay "
            "unzoned",
            text,
        )

    def test_from_first_without_activities_is_an_error(self):
        with self.assertRaises(SystemExit):
            self._run(
                "add",
                "--sport",
                "run",
                "--from",
                "first",
                "--lthr",
                "170",
            )

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
