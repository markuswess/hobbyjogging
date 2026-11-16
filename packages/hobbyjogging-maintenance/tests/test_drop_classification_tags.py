import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "drop_classification_tags_v1"


class DropClassificationTagsTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)

    def _activity(self, activity_id="a1", *, excluded=False):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) VALUES (?, ?, ?)",
            (activity_id, "2019-01-23", "run"),
        )
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _tags(self, activity_id, tags, *, source="sheet", manual=False):
        self.conn.executemany(
            "INSERT INTO activity_tags "
            "(activity_id, tag, source, is_manual) VALUES (?, ?, ?, ?)",
            [
                (activity_id, tag, "manual" if manual else source,
                 1 if manual else 0)
                for tag in tags
            ],
        )
        self.conn.commit()

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _remaining(self, activity_id):
        return [
            row["tag"]
            for row in self.conn.execute(
                "SELECT tag FROM activity_tags WHERE activity_id = ? "
                "ORDER BY tag",
                (activity_id,),
            )
        ]

    def test_drops_the_type_code_and_keeps_the_area(self):
        self._activity()
        self._tags("a1", ["ll", "w"])

        result = self._run()

        self.assertEqual(1, result.counts["tags_removed"])
        self.assertEqual(["w"], self._remaining("a1"))

    def test_manual_tags_are_never_touched(self):
        self._activity()
        self._tags("a1", ["ll"], manual=True)

        result = self._run()

        self.assertEqual(0, result.counts.get("activities", 0))
        self.assertEqual(["ll"], self._remaining("a1"))

    def test_other_sources_are_untouched(self):
        self._activity()
        self._tags("a1", ["ll"], source="intervals")

        self._run()

        self.assertEqual(["ll"], self._remaining("a1"))

    def test_an_activity_with_only_area_tags_is_unchanged(self):
        self._activity()
        self._tags("a1", ["w", "wb"])

        result = self._run()

        self.assertEqual(0, result.counts.get("activities", 0))
        self.assertEqual(["w", "wb"], self._remaining("a1"))

    def test_excluded_activities_are_skipped(self):
        self._activity(excluded=True)
        self._tags("a1", ["ll", "w"])

        result = self._run()

        self.assertEqual(1, result.counts["skipped"])
        self.assertEqual(["ll", "w"], self._remaining("a1"))

    def test_a_forced_rerun_is_a_no_op(self):
        self._activity()
        self._tags("a1", ["ll", "w"])

        self._run()
        result = self._run(force=True)

        self.assertEqual(0, result.counts.get("activities", 0))
        self.assertEqual(["w"], self._remaining("a1"))

    def test_dry_run_writes_nothing(self):
        self._activity()
        self._tags("a1", ["ll", "w"])

        self._run(dry_run=True)

        self.assertEqual(["ll", "w"], self._remaining("a1"))


if __name__ == "__main__":
    unittest.main()
