import json
import unittest
from unittest.mock import patch

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_report.classify import Category

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "workout_sets_current"
QUEUE = "workout_classification_queue"
CLASSIFY = "hobbyjogging_maintenance.workouts.classify"

UNKNOWN = Category("unknown")
LONGRUN = Category("quality", "longrun")
TEMPO = Category("quality", "tempo")


class WorkoutSetsCurrentTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _activity(
        self,
        name="Easy",
        *,
        code=None,
        sheet=True,
        avg_hr=None,
        intensity=None,
    ):
        self.counter += 1
        activity_id = f"a{self.counter}"
        source = "sheet" if sheet else "intervals"
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=activity_id,
            checksum=f"c-{activity_id}",
            payload_json=json.dumps({"values": {"Trainigstyp": code or ""}}),
            import_run_id=self.run_id,
        )
        values = {
            "local_date": "2026-10-01",
            "sport": "run",
            "name": name,
            "duration_s": 3600,
        }
        if avg_hr is not None:
            values["avg_hr"] = avg_hr
        if intensity is not None:
            values["intensity"] = intensity
        self.writer.upsert_activity(
            activity_id,
            values,
            source=source,
            source_record_id=record_id,
        )
        if sheet:
            self.writer.link_activity_source(activity_id, record_id)
        self.conn.commit()
        return activity_id

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
                "SELECT method, source, is_manual "
                "FROM activity_workout_methods "
                "WHERE activity_id = ? ORDER BY method",
                (activity_id,),
            )
        ]

    def test_derives_the_classifier_sets(self):
        activity_id = self._activity(sheet=False)

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )
        self.assertEqual([("continuous", "classifier", 0)], self._sources(activity_id))

    def test_derives_the_sheet_sets_when_the_classifier_has_none(self):
        activity_id = self._activity("Sessions", code="tdl")

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )

    def test_agreeing_proposals_are_merged(self):
        activity_id = self._activity("Tempo", code="tdl")

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )

    def test_disagreement_stays_empty_and_the_queue_records_it(self):
        activity_id = self._activity("Long run", code="i")

        with patch(CLASSIFY, return_value=LONGRUN):
            run = self._run()

        self.assertEqual(1, run.counts["conflict"])
        self.assertEqual(([], []), self._sets(activity_id))
        self.assertTrue(any("queue" in note for note in run.notes))

        with patch(CLASSIFY, return_value=LONGRUN):
            run_task(self.conn, get_task(QUEUE))

        item = self.conn.execute(
            "SELECT category, activity_id FROM review_items "
            "WHERE status = 'open' AND category = 'workout_classification'"
        ).fetchone()
        self.assertIsNotNone(item)
        self.assertEqual(activity_id, item["activity_id"])

    def test_existing_sets_are_never_touched(self):
        activity_id = self._activity(sheet=False)
        self.writer.replace_activity_workout_methods(
            activity_id, ["progression"], source="manual", is_manual=True
        )
        self.writer.replace_activity_workout_targets(
            activity_id, ["base"], source="manual", is_manual=True
        )
        self.conn.commit()

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(1, run.counts["already_classified"])
        self.assertEqual(0, run.counts["derived"])
        self.assertEqual(
            (["progression"], ["base"]),
            self._sets(activity_id),
        )

    def test_easy_default_for_a_low_hr_sheet_run_without_a_code(self):
        activity_id = self._activity("", avg_hr=120, code="")

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(
            (["continuous"], ["base"]),
            self._sets(activity_id),
        )

    def test_high_hr_sheet_run_without_a_code_stays_empty(self):
        activity_id = self._activity("", avg_hr=150, code="")

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["no_proposal"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_second_run_is_a_no_op(self):
        self._activity(sheet=False)

        with patch(CLASSIFY, return_value=TEMPO):
            self._run()
            second = self._run()

        self.assertEqual(0, second.counts["derived"])
        self.assertEqual(1, second.counts["already_classified"])

    def test_dry_run_writes_nothing(self):
        activity_id = self._activity(sheet=False)

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_scope_limits_to_one_activity(self):
        first = self._activity(sheet=False)
        second = self._activity(sheet=False)

        from hobbyjogging_maintenance.context import Scope

        with patch(CLASSIFY, return_value=TEMPO):
            self._run(scope=Scope(entity_id=second))

        self.assertEqual(([], []), self._sets(first))
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(second),
        )


if __name__ == "__main__":
    unittest.main()
