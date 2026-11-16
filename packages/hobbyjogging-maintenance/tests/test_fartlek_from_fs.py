import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "fartlek_from_fs_v1"


class FartlekFromFsTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test", {})

    def _activity(self, activity_id="a1", *, code="fs", excluded=False):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) VALUES (?, ?, ?)",
            (activity_id, "2020-06-01", "run"),
        )
        record_id = self.writer.upsert_source_record(
            source="sheet",
            record_type="activity",
            external_id=f"sheet-{activity_id}",
            checksum=f"c-{activity_id}",
            import_run_id=self.run_id,
            payload_json=json.dumps({"values": {"Trainigstyp": code}}),
        )
        self.conn.execute(
            "INSERT INTO activity_sources "
            "(activity_id, source_record_id, match_method) VALUES (?, ?, 'test')",
            (activity_id, record_id),
        )
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _seed(self, activity_id, methods, targets=(), *, manual=False):
        self.conn.executemany(
            "INSERT INTO activity_workout_methods "
            "(activity_id, method, source, is_manual) VALUES (?, ?, ?, ?)",
            [
                (activity_id, method, "manual" if manual else "backfill",
                 1 if manual else 0)
                for method in methods
            ],
        )
        self.conn.executemany(
            "INSERT INTO activity_workout_targets "
            "(activity_id, target, source, is_manual) VALUES (?, ?, ?, ?)",
            [
                (activity_id, target, "manual" if manual else "backfill",
                 1 if manual else 0)
                for target in targets
            ],
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

    def test_converts_intervals_to_fartlek_and_fills_a_missing_target(self):
        self._activity("a1")
        self._seed("a1", ["intervals"])

        result = self._run()

        self.assertEqual(1, result.counts["converted"])
        self.assertEqual(1, result.counts["targets_filled"])
        self.assertEqual((["fartlek"], ["vo2max"]), self._sets("a1"))

    def test_manual_methods_win_and_the_activity_is_skipped(self):
        self._activity("a1")
        self._seed("a1", ["intervals"], manual=True)

        result = self._run()

        self.assertEqual(1, result.counts["skipped_manual"])
        self.assertEqual((["intervals"], []), self._sets("a1"))

    def test_existing_targets_are_left_alone(self):
        self._activity("a1")
        self._seed("a1", ["intervals"], ["other"])

        self._run()

        self.assertEqual((["fartlek"], ["other"]), self._sets("a1"))

    def test_excluded_activities_are_skipped(self):
        self._activity("a1", excluded=True)
        self._seed("a1", ["intervals"])

        result = self._run()

        self.assertEqual(1, result.counts["skipped_excluded"])
        self.assertEqual((["intervals"], []), self._sets("a1"))

    def test_other_sheet_codes_are_untouched(self):
        self._activity("a1", code="i")
        self._seed("a1", ["intervals"], ["vo2max"])

        result = self._run()

        self.assertEqual(0, result.counts.get("activities", 0))
        self.assertEqual((["intervals"], ["vo2max"]), self._sets("a1"))

    def test_the_runner_skips_an_applied_backfill(self):
        self._activity("a1")
        self._seed("a1", ["intervals"])

        self._run()
        result = self._run()

        self.assertEqual({}, result.counts)
        self.assertEqual((["fartlek"], ["vo2max"]), self._sets("a1"))

    def test_a_forced_rerun_is_a_no_op(self):
        self._activity("a1")
        self._seed("a1", ["intervals"])

        self._run()
        result = self._run(force=True)

        self.assertEqual(0, result.counts.get("converted", 0))
        self.assertEqual(1, result.counts["unchanged"])
        self.assertEqual((["fartlek"], ["vo2max"]), self._sets("a1"))

    def test_dry_run_writes_nothing(self):
        self._activity("a1")
        self._seed("a1", ["intervals"])

        self._run(dry_run=True)

        self.assertEqual((["intervals"], []), self._sets("a1"))


if __name__ == "__main__":
    unittest.main()
