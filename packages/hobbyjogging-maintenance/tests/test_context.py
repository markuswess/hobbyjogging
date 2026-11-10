import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import connect, migrate

from hobbyjogging_maintenance.context import Scope, TaskContext


class TaskContextTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)

    def _context(self, **kwargs):
        return TaskContext(connection=self.conn, **kwargs)

    def test_count_accumulates(self):
        context = self._context()

        context.count("seen")
        context.count("seen")
        context.count("skipped", 3)

        self.assertEqual({"seen": 2, "skipped": 3}, context.counts)

    def test_order_counts_puts_known_keys_first(self):
        context = self._context()
        context.count("skipped")
        context.count("events")
        context.count("extra")

        context.order_counts(("events", "skipped", "missing"))

        self.assertEqual(
            ["events", "skipped", "missing", "extra"],
            list(context.counts),
        )
        self.assertEqual(0, context.counts["missing"])

    def test_scope_defaults_to_everything(self):
        self.assertEqual(Scope(), self._context().scope)

    def test_write_output_needs_a_path(self):
        context = self._context()
        context.output_lines.append("nothing")

        self.assertIsNone(context.write_output())

    def test_write_output_writes_the_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "report.txt"
            context = self._context(output=path)
            context.output_lines.extend(["first", "second"])

            written = context.write_output()

            self.assertEqual(path, written)
            self.assertEqual("first\nsecond\n", path.read_text())

    def test_empty_output_writes_an_empty_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.txt"
            context = self._context(output=path)

            context.write_output()

            self.assertEqual("", path.read_text())


if __name__ == "__main__":
    unittest.main()
