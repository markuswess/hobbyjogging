import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import open_database
from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.period_cli import run_period


class PeriodCliTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "periods.db"

        connection = open_database(self.database)
        self.addCleanup(connection.close)
        connection.close()

    def _run(self, *argv):
        parser = build_parser()
        args = parser.parse_args(list(argv))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_period(args, parser)
        return code, out.getvalue()

    def _periods(self):
        connection = open_database(self.database)
        try:
            return connection.execute(
                "SELECT id, kind, label, start_date, end_date, source, "
                "excluded_at FROM training_periods ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

    def test_add_writes_a_manual_period(self):
        code, out = self._run(
            "period", "--database", str(self.database),
            "add", "--kind", "illness", "--start", "2026-05-01",
            "--end", "2026-05-08", "--label", "Flu",
        )

        self.assertEqual(0, code)
        self.assertIn("period saved", out)

        row = self._periods()[0]
        self.assertEqual("manual:illness:2026-05-01", row["id"])
        self.assertEqual("illness", row["kind"])
        self.assertEqual("Flu", row["label"])
        self.assertEqual("2026-05-08", row["end_date"])
        self.assertEqual("manual", row["source"])
        self.assertIsNone(row["excluded_at"])

    def test_add_is_idempotent_per_kind_and_start(self):
        for label in ("Flu", "Cold"):
            self._run(
                "period", "--database", str(self.database),
                "add", "--kind", "illness", "--start", "2026-05-01",
                "--label", label,
            )

        rows = self._periods()
        self.assertEqual(1, len(rows))
        self.assertEqual("Cold", rows[0]["label"])

    def test_an_end_before_the_start_is_rejected(self):
        with self.assertRaises(SystemExit):
            self._run(
                "period", "--database", str(self.database),
                "add", "--kind", "travel", "--start", "2026-05-08",
                "--end", "2026-05-01",
            )

    def test_list_prints_open_periods(self):
        self._run(
            "period", "--database", str(self.database),
            "add", "--kind", "plan", "--start", "2026-01-01",
            "--label", "Spring block",
        )

        code, out = self._run(
            "period", "--database", str(self.database), "list",
        )

        self.assertEqual(0, code)
        self.assertIn("open", out)
        self.assertIn("Spring block", out)

    def test_remove_soft_excludes(self):
        self._run(
            "period", "--database", str(self.database),
            "add", "--kind", "illness", "--start", "2026-05-01",
        )

        code, _ = self._run(
            "period", "--database", str(self.database),
            "remove", "manual:illness:2026-05-01",
        )

        self.assertEqual(0, code)
        self.assertIsNotNone(self._periods()[0]["excluded_at"])


if __name__ == "__main__":
    unittest.main()
