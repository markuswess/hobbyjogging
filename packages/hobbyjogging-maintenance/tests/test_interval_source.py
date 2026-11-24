import unittest

from hobbyjogging_core import (
    Interval,
    TrainingWriter,
    connect,
    migrate,
)

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "interval_source_v1"


class IntervalSourceBackfillTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run"},
            source="intervals",
            source_record_id=None,
        )
        self.writer.replace_activity_intervals(
            "a1",
            [Interval(type="WORK", duration_s=60)],
        )
        self.conn.commit()

    def _sources(self):
        return [
            row["source"]
            for row in self.conn.execute(
                "SELECT source FROM activity_intervals"
            )
        ]

    def test_stamps_the_existing_rows(self):
        result = run_task(self.conn, get_task(TASK))

        self.assertEqual(1, result.counts["rows"])
        self.assertEqual(1, result.counts["stamped"])
        self.assertEqual(["intervals"], self._sources())

    def test_a_second_run_is_a_noop(self):
        run_task(self.conn, get_task(TASK))

        result = run_task(self.conn, get_task(TASK), force=True)

        self.assertEqual(0, result.counts["rows"])
        self.assertEqual(0, result.counts["stamped"])
        self.assertEqual(["intervals"], self._sources())

    def test_a_dry_run_writes_nothing(self):
        result = run_task(self.conn, get_task(TASK), dry_run=True)

        self.assertEqual(1, result.counts["stamped"])
        self.assertEqual([""], self._sources())


if __name__ == "__main__":
    unittest.main()
