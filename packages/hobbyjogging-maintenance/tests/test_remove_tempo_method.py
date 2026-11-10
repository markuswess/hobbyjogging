import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "remove_tempo_method_v1"


class RemoveTempoMethodTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)

    def _activity(self, activity_id="a1", *, excluded=False):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) VALUES (?, ?, ?)",
            (activity_id, "2026-10-01", "run"),
        )
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _seed_methods(self, activity_id, methods, *, source="backfill"):
        # Raw SQL: the vocabulary no longer accepts the retired token.
        self.conn.executemany(
            "INSERT INTO activity_workout_methods "
            "(activity_id, method, source) VALUES (?, ?, ?)",
            [(activity_id, method, source) for method in methods],
        )
        self.conn.commit()

    def _seed_targets(self, activity_id, targets):
        self.conn.executemany(
            "INSERT INTO activity_workout_targets "
            "(activity_id, target, source) VALUES (?, ?, 'backfill')",
            [(activity_id, target) for target in targets],
        )
        self.conn.commit()

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _sets(self, activity_id):
        methods = [
            row["method"]
            for row in self.conn.execute(
                "SELECT method FROM activity_workout_methods "
                "WHERE activity_id = ? ORDER BY method",
                (activity_id,),
            )
        ]
        targets = [
            row["target"]
            for row in self.conn.execute(
                "SELECT target FROM activity_workout_targets "
                "WHERE activity_id = ? ORDER BY target",
                (activity_id,),
            )
        ]
        return methods, targets

    def _sources(self, activity_id):
        return [
            (row["method"], row["source"], row["is_manual"])
            for row in self.conn.execute(
                "SELECT method, source, is_manual FROM activity_workout_methods "
                "WHERE activity_id = ? ORDER BY method",
                (activity_id,),
            )
        ]

    def test_converts_tempo_to_continuous(self):
        activity_id = self._activity()
        self._seed_methods(activity_id, ["tempo"])
        self._seed_targets(activity_id, ["threshold"])

        run = self._run()

        self.assertEqual(1, run.counts["activities"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )
        self.assertEqual([("continuous", "manual", 1)], self._sources(activity_id))

    def test_keeps_other_methods(self):
        activity_id = self._activity()
        self._seed_methods(activity_id, ["tempo", "intervals"])

        self._run()

        self.assertEqual(
            (["continuous", "intervals"], []),
            self._sets(activity_id),
        )

    def test_activity_that_already_has_continuous_gets_one_row(self):
        activity_id = self._activity()
        self._seed_methods(activity_id, ["tempo", "continuous"])

        run = self._run()

        self.assertEqual(1, run.counts["already_continuous"])
        self.assertEqual((["continuous"], []), self._sets(activity_id))

    def test_excluded_activities_are_skipped(self):
        activity_id = self._activity(excluded=True)
        self._seed_methods(activity_id, ["tempo"])

        run = self._run()

        self.assertEqual(1, run.counts["skipped"])
        self.assertEqual((["tempo"], []), self._sets(activity_id))
        self.assertTrue(any("excluded" in note for note in run.notes))

    def test_is_recorded_as_applied_and_idempotent(self):
        activity_id = self._activity()
        self._seed_methods(activity_id, ["tempo"])

        self._run()
        again = self._run(force=True)

        self.assertEqual("No activities used the tempo method.", again.notes[0])
        self.assertEqual((["continuous"], []), self._sets(activity_id))

    def test_dry_run_writes_nothing(self):
        activity_id = self._activity()
        self._seed_methods(activity_id, ["tempo"])

        run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["activities"])
        self.assertEqual((["tempo"], []), self._sets(activity_id))

    def test_no_tempo_rows_is_a_no_op(self):
        self._activity()

        run = self._run()

        self.assertEqual("No activities used the tempo method.", run.notes[0])
        self.assertEqual({}, run.counts)


if __name__ == "__main__":
    unittest.main()
