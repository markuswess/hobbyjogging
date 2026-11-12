import unittest
from datetime import date

from hobbyjogging_core import Interval, TrainingWriter, connect, migrate

from hobbyjogging_maintenance.context import Scope
from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task
from hobbyjogging_maintenance.store import is_applied

TASK = "drop_empty_intervals_v1"

WORK = "WORK"
RECOVERY = "RECOVERY"


class DropEmptyIntervalsTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _activity(
        self,
        activity_id="a1",
        *,
        local_date="2026-10-01",
        excluded=False,
    ):
        record_id = self.writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id=activity_id,
            checksum=f"activity-{activity_id}",
            payload_json="{}",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            activity_id,
            {"local_date": local_date, "sport": "run"},
            source="intervals",
            source_record_id=record_id,
        )
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _seed(self, activity_id, intervals):
        record_id = self.writer.upsert_source_record(
            source="intervals",
            record_type="intervals",
            external_id=activity_id,
            checksum=f"intervals-{activity_id}",
            payload_json="[]",
            import_run_id=self.run_id,
        )
        self.writer.replace_activity_intervals(
            activity_id,
            intervals,
            source_record_id=record_id,
        )
        self.conn.commit()
        return record_id

    def _rows(self, activity_id):
        return [
            (
                row["type"],
                row["duration_s"],
                row["distance_m"],
                row["source_record_id"],
            )
            for row in self.conn.execute(
                """
                SELECT type, duration_s, distance_m, source_record_id
                FROM activity_intervals
                WHERE activity_id = ?
                ORDER BY interval_index
                """,
                (activity_id,),
            )
        ]

    def test_drops_the_trailing_recovery(self):
        activity_id = self._activity()
        source_id = self._seed(
            activity_id,
            [
                Interval(type=WORK, duration_s=600, distance_m=2000),
                Interval(type=RECOVERY, duration_s=1, distance_m=0),
            ],
        )

        run = self._run()

        self.assertEqual(1, run.counts["activities"])
        self.assertEqual(1, run.counts["dropped"])
        self.assertEqual(1, run.counts["kept"])
        self.assertEqual(
            [(WORK, 600, 2000, source_id)],
            self._rows(activity_id),
        )

    def test_keeps_a_genuine_short_segment(self):
        activity_id = self._activity()
        source_id = self._seed(
            activity_id,
            [
                Interval(type=WORK, duration_s=600, distance_m=2000),
                Interval(type=WORK, duration_s=2, distance_m=5),
                Interval(type=RECOVERY, duration_s=1, distance_m=0),
            ],
        )

        self._run()

        self.assertEqual(
            [
                (WORK, 600, 2000, source_id),
                (WORK, 2, 5, source_id),
            ],
            self._rows(activity_id),
        )

    def test_activity_with_only_the_artifact_ends_empty(self):
        activity_id = self._activity()
        self._seed(
            activity_id,
            [Interval(type=RECOVERY, duration_s=1, distance_m=0)],
        )

        run = self._run()

        self.assertEqual(1, run.counts["dropped"])
        self.assertEqual(0, run.counts["kept"])
        self.assertEqual(1, run.counts["cleared"])
        self.assertEqual([], self._rows(activity_id))
        self.assertTrue(any("no intervals" in note for note in run.notes))

    def test_rerun_is_a_no_op(self):
        activity_id = self._activity()
        self._seed(
            activity_id,
            [
                Interval(type=WORK, duration_s=600, distance_m=2000),
                Interval(type=RECOVERY, duration_s=1, distance_m=0),
            ],
        )
        self._run()

        again = self._run(force=True)

        self.assertEqual(1, again.counts["activities"])
        self.assertEqual(1, again.counts["unchanged"])
        self.assertEqual(0, again.counts["dropped"])
        self.assertEqual(1, len(self._rows(activity_id)))

    def test_dry_run_writes_nothing(self):
        activity_id = self._activity()
        self._seed(
            activity_id,
            [
                Interval(type=WORK, duration_s=600, distance_m=2000),
                Interval(type=RECOVERY, duration_s=1, distance_m=0),
            ],
        )

        run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["dropped"])
        self.assertEqual(2, len(self._rows(activity_id)))
        self.assertFalse(is_applied(self.conn, TASK))

    def test_activity_without_the_artifact_is_unchanged(self):
        activity_id = self._activity()
        self._seed(
            activity_id,
            [Interval(type=WORK, duration_s=600, distance_m=2000)],
        )

        run = self._run()

        self.assertEqual(1, run.counts["unchanged"])
        self.assertEqual(0, run.counts["dropped"])
        self.assertEqual(1, len(self._rows(activity_id)))

    def test_scope_limits_to_one_activity(self):
        first = self._activity("a1", local_date="2026-10-01")
        second = self._activity("a2", local_date="2026-10-02")
        for activity_id in (first, second):
            self._seed(
                activity_id,
                [
                    Interval(type=WORK, duration_s=600, distance_m=2000),
                    Interval(type=RECOVERY, duration_s=1, distance_m=0),
                ],
            )

        self._run(scope=Scope(entity_id=second))

        self.assertEqual(2, len(self._rows(first)))
        self.assertEqual(1, len(self._rows(second)))

    def test_scope_limits_by_date(self):
        first = self._activity("a1", local_date="2026-10-01")
        second = self._activity("a2", local_date="2026-10-02")
        for activity_id in (first, second):
            self._seed(
                activity_id,
                [
                    Interval(type=WORK, duration_s=600, distance_m=2000),
                    Interval(type=RECOVERY, duration_s=1, distance_m=0),
                ],
            )

        self._run(scope=Scope(start=date(2026, 10, 2)))

        self.assertEqual(2, len(self._rows(first)))
        self.assertEqual(1, len(self._rows(second)))

    def test_scope_limits_by_count(self):
        first = self._activity("a1", local_date="2026-10-01")
        second = self._activity("a2", local_date="2026-10-02")
        for activity_id in (first, second):
            self._seed(
                activity_id,
                [
                    Interval(type=WORK, duration_s=600, distance_m=2000),
                    Interval(type=RECOVERY, duration_s=1, distance_m=0),
                ],
            )

        self._run(scope=Scope(limit=1))

        self.assertEqual(1, len(self._rows(first)))
        self.assertEqual(2, len(self._rows(second)))

    def test_excluded_activities_are_untouched(self):
        activity_id = self._activity(excluded=True)
        self._seed(
            activity_id,
            [
                Interval(type=WORK, duration_s=600, distance_m=2000),
                Interval(type=RECOVERY, duration_s=1, distance_m=0),
            ],
        )

        run = self._run()

        self.assertEqual({}, run.counts)
        self.assertEqual(2, len(self._rows(activity_id)))

    def test_unknown_entity_fails(self):
        run = self._run(scope=Scope(entity_id="missing"))

        self.assertEqual("failed", run.status)
        self.assertIn("unknown or excluded activity", run.error)


if __name__ == "__main__":
    unittest.main()
