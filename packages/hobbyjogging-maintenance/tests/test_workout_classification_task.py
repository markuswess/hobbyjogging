import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_core.classify import Category

from hobbyjogging_maintenance.context import Scope
from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "workout_classification_v1"
CLASSIFY = "hobbyjogging_maintenance.workouts.classify"

UNKNOWN = Category("unknown")


class WorkoutClassificationTests(unittest.TestCase):

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
        name,
        *,
        sport="run",
        avg_hr=None,
        intensity=None,
        duration_s=3600,
        code=None,
        sheet=True,
        tags=None,
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
            "sport": sport,
            "name": name,
            "duration_s": duration_s,
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
        if tags:
            self.writer.replace_activity_tags(
                activity_id,
                tags,
                source="sheet",
                source_record_id=record_id,
            )
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

    def _tags(self, activity_id):
        return [
            row["tag"]
            for row in self.conn.execute(
                "SELECT tag FROM activity_tags "
                "WHERE activity_id = ? ORDER BY tag",
                (activity_id,),
            )
        ]

    # --- proposals -------------------------------------------------------

    def test_classifier_only_uses_the_real_classifier(self):
        activity_id = self._activity("Easy", intensity=0.7, sheet=False)

        run = self._run()

        self.assertEqual("ok", run.status)
        self.assertEqual(1, run.counts["classifier_only"])
        self.assertEqual((["continuous"], ["base"]), self._sets(activity_id))

    def test_classifier_quality_session(self):
        activity_id = self._activity(
            "6x900m subT short",
            intensity=0.9,
            sheet=False,
        )

        self._run()

        self.assertEqual(
            (["intervals"], ["subthreshold"]),
            self._sets(activity_id),
        )

    def test_sheet_only_uses_the_trainigstyp_code(self):
        activity_id = self._activity("Sessions", code="tdl")

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["sheet_only"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )

    def test_agreeing_proposals_are_merged(self):
        activity_id = self._activity("Tempo", code="tdl")

        with patch(CLASSIFY, return_value=Category("quality", "tempo")):
            run = self._run()

        self.assertEqual(1, run.counts["both"])
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )

    def test_conflict_is_left_unclassified_and_reported(self):
        activity_id = self._activity("Long run", code="i")

        with patch(CLASSIFY, return_value=Category("quality", "longrun")):
            run = self._run()

        self.assertEqual(1, run.counts["conflicts"])
        self.assertEqual(([], []), self._sets(activity_id))
        self.assertEqual(1, len(run.details["conflicts"]))
        conflict = run.details["conflicts"][0]
        self.assertEqual(activity_id, conflict["activity_id"])
        self.assertEqual("i", conflict["sheet_code"])
        self.assertEqual(["long_run"], conflict["classifier_methods"])
        self.assertEqual(["intervals"], conflict["sheet_methods"])
        self.assertTrue(any("conflicts" in note for note in run.notes))

    # --- defaults --------------------------------------------------------

    def test_low_hr_sheet_run_without_a_code_is_easy(self):
        activity_id = self._activity("", avg_hr=120, code="")

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["easy_default"])
        self.assertEqual((["continuous"], ["base"]), self._sets(activity_id))

    def test_high_hr_sheet_run_without_a_code_stays_unclassified(self):
        activity_id = self._activity("", avg_hr=150, code="")

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["unclassified"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_non_running_activity_is_not_an_easy_default(self):
        activity_id = self._activity(
            "",
            sport="ride",
            avg_hr=120,
            code="",
        )

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["unclassified"])
        self.assertEqual(([], []), self._sets(activity_id))

    # --- tags and manual values -----------------------------------------

    def test_sheet_tags_are_merged_without_dropping_existing_ones(self):
        activity_id = self._activity("Gym", code="k", tags=["hills"])

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(["hills", "strength"], self._tags(activity_id))
        self.assertEqual(1, run.counts["tagged_activities"])
        self.assertEqual(1, run.counts["tags_added"])

    def test_manual_values_survive_a_rerun(self):
        activity_id = self._activity("Easy", intensity=0.7, sheet=False)
        self.writer.replace_activity_workout_methods(
            activity_id,
            ["progression"],
            source="manual",
            is_manual=True,
        )
        self.writer.replace_activity_workout_targets(
            activity_id,
            ["threshold"],
            source="manual",
            is_manual=True,
        )
        self.conn.commit()

        self._run()

        self.assertEqual(
            (["continuous", "progression"], ["base", "threshold"]),
            self._sets(activity_id),
        )

    # --- runner integration ---------------------------------------------

    def test_rerun_does_not_echo_the_stored_sets(self):
        self._activity("Easy", intensity=0.7, sheet=False)
        self._activity("Sessions", code="tdl")

        first = self._run()
        second = self._run(force=True)

        self.assertEqual(first.counts, second.counts)

    def test_rerun_is_idempotent(self):
        activity_id = self._activity("Easy", intensity=0.7, sheet=False)
        self._run()

        self._run(force=True)

        self.assertEqual((["continuous"], ["base"]), self._sets(activity_id))
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM activity_workout_methods"
            ).fetchone()[0],
        )

    def test_dry_run_writes_nothing(self):
        activity_id = self._activity("Easy", intensity=0.7, sheet=False)

        run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["classified"])
        self.assertEqual(([], []), self._sets(activity_id))

    def test_scope_limits_to_one_activity(self):
        first = self._activity("Easy", intensity=0.7, sheet=False)
        second = self._activity("Tempo", intensity=0.9, sheet=False)

        self._run(scope=Scope(entity_id=second))

        self.assertEqual(([], []), self._sets(first))
        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(second),
        )

    def test_report_file_lists_conflicts(self):
        activity_id = self._activity("Long run", code="i")

        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "conflicts.txt"
            with patch(CLASSIFY, return_value=Category("quality", "longrun")):
                run = self._run(output=report)

            text = report.read_text()

        self.assertEqual(report, run.output)
        self.assertIn("Conflicts (left unclassified for review):", text)
        self.assertIn(f"[{activity_id}]", text)
        self.assertIn("sheet (i):", text)


if __name__ == "__main__":
    unittest.main()
