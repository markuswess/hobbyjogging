import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

EVIDENCE = "workout_classification_evidence_v1"
DRILLS = "drills_from_tags_v1"


class EvidenceBackfillTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _activity(self, *, tags=(), description=""):
        self.counter += 1
        activity_id = f"a{self.counter}"
        values = {
            "local_date": "2026-10-01",
            "sport": "run",
            "name": "Session",
            "duration_s": 3600,
        }
        if description:
            values["description"] = description
        self.writer.upsert_activity(
            activity_id,
            values,
            source="fit",
            source_record_id=None,
        )
        if tags:
            self.writer.replace_activity_tags(
                activity_id, list(tags), source="runalyze"
            )
        self.conn.commit()
        return activity_id

    def _seed_sets(
        self,
        activity_id,
        methods,
        targets,
        *,
        source,
        manual=False,
    ):
        self.writer.replace_activity_workout_methods(
            activity_id,
            methods,
            source=source,
            is_manual=manual,
        )
        self.writer.replace_activity_workout_targets(
            activity_id,
            targets,
            source=source,
            is_manual=manual,
        )
        self.conn.commit()

    def _item(
        self,
        activity_id,
        *,
        evidence_source,
        methods,
        targets,
        stored_methods,
        stored_targets,
    ):
        self.counter += 1
        item_id, _ = self.writer.record_review_item(
            category="workout_classification",
            detail=f"{evidence_source} evidence vs stored classification",
            context={
                "evidence_source": evidence_source,
                "evidence_methods": list(methods),
                "evidence_targets": list(targets),
                "stored_methods": list(stored_methods),
                "stored_targets": list(stored_targets),
            },
            severity="info",
            fingerprint=f"fp-{self.counter}",
            activity_id=activity_id,
        )
        self.conn.commit()
        return item_id

    def _run(self, task, **kwargs):
        return run_task(self.conn, get_task(task), **kwargs)

    def _sets(self, activity_id):
        methods = sorted(
            row["method"]
            for row in self.conn.execute(
                "SELECT method FROM activity_workout_methods "
                "WHERE activity_id = ?",
                (activity_id,),
            )
        )
        targets = sorted(
            row["target"]
            for row in self.conn.execute(
                "SELECT target FROM activity_workout_targets "
                "WHERE activity_id = ?",
                (activity_id,),
            )
        )
        return methods, targets

    def _sources(self, activity_id):
        return [
            (row["method"], row["source"], row["is_manual"])
            for row in self.conn.execute(
                "SELECT method, source, is_manual "
                "FROM activity_workout_methods WHERE activity_id = ?",
                (activity_id,),
            )
        ]

    def test_a_specific_tag_is_accepted_on_a_classifier_set(self):
        activity_id = self._activity(tags=["LT1"])
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["threshold"],
            source="classifier",
        )
        item_id = self._item(
            activity_id,
            evidence_source="tag",
            methods=["intervals"],
            targets=["lt1"],
            stored_methods=["continuous"],
            stored_targets=["threshold"],
        )

        result = self._run(EVIDENCE)

        self.assertEqual(1, result.counts["accepted"])
        self.assertEqual(
            (["intervals"], ["lt1"]),
            self._sets(activity_id),
        )
        self.assertEqual(
            [("intervals", "tag", 0)],
            self._sources(activity_id),
        )
        item = self.writer.review_item(item_id)
        self.assertEqual("resolved", item["status"])
        self.assertEqual("accepted tag evidence", item["resolved_note"])

    def test_a_backfill_projection_with_additive_drills_is_refined(self):
        activity_id = self._activity(tags=["LTT", "LT1"])
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["base"],
            source="backfill",
        )
        self.writer.replace_activity_workout_methods(
            activity_id,
            ["drills"],
            source="tag",
        )
        self.conn.commit()
        self._item(
            activity_id,
            evidence_source="tag",
            methods=["intervals"],
            targets=["lt1"],
            stored_methods=["continuous"],
            stored_targets=["base"],
        )

        result = self._run(EVIDENCE)

        self.assertEqual(1, result.counts["accepted"])
        self.assertEqual(
            (["drills", "intervals"], ["lt1"]),
            self._sets(activity_id),
        )

    def test_a_race_day_tag_is_context_not_a_race_method(self):
        activity_id = self._activity(tags=["Raceday"])
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["base"],
            source="classifier",
        )
        item_id = self._item(
            activity_id,
            evidence_source="tag",
            methods=["race"],
            targets=["other"],
            stored_methods=["continuous"],
            stored_targets=["base"],
        )

        self._run(EVIDENCE)

        self.assertEqual(
            (["continuous"], ["base"]),
            self._sets(activity_id),
        )
        self.assertIn(
            "race-day",
            self.writer.review_item(item_id)["resolved_note"],
        )

    def test_a_manual_set_wins_over_tag_evidence(self):
        activity_id = self._activity(tags=["LT1"])
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["base"],
            source="manual",
            manual=True,
        )
        item_id = self._item(
            activity_id,
            evidence_source="tag",
            methods=["intervals"],
            targets=["lt1"],
            stored_methods=["continuous"],
            stored_targets=["base"],
        )

        result = self._run(EVIDENCE)

        self.assertEqual(1, result.counts["closed"])
        self.assertEqual(
            (["continuous"], ["base"]),
            self._sets(activity_id),
        )
        self.assertEqual(
            "policy: stored set wins",
            self.writer.review_item(item_id)["resolved_note"],
        )

    def test_a_sheet_set_wins_over_tag_evidence(self):
        activity_id = self._activity(tags=["LT1"])
        self._seed_sets(
            activity_id,
            ["long_run"],
            ["base"],
            source="sheet",
        )
        self._item(
            activity_id,
            evidence_source="tag",
            methods=["intervals"],
            targets=["lt1"],
            stored_methods=["long_run"],
            stored_targets=["base"],
        )

        self._run(EVIDENCE)

        self.assertEqual(
            (["long_run"], ["base"]),
            self._sets(activity_id),
        )

    def test_a_comment_only_fills_an_empty_classification(self):
        activity_id = self._activity(description="Tempo run")
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["threshold"],
            source="classifier",
        )
        item_id = self._item(
            activity_id,
            evidence_source="comment",
            methods=["continuous"],
            targets=["threshold"],
            stored_methods=["continuous"],
            stored_targets=["threshold"],
        )

        self._run(EVIDENCE)

        self.assertEqual(
            "policy: comment only fills an empty classification",
            self.writer.review_item(item_id)["resolved_note"],
        )

    def test_generic_other_does_not_override(self):
        activity_id = self._activity(tags=["Something"])
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["threshold"],
            source="classifier",
        )
        item_id = self._item(
            activity_id,
            evidence_source="tag",
            methods=["other"],
            targets=["other"],
            stored_methods=["continuous"],
            stored_targets=["threshold"],
        )

        self._run(EVIDENCE)

        self.assertEqual(
            (["continuous"], ["threshold"]),
            self._sets(activity_id),
        )
        self.assertIn(
            "generic",
            self.writer.review_item(item_id)["resolved_note"],
        )

    def test_a_second_run_is_a_no_op(self):
        activity_id = self._activity(tags=["LT1"])
        self._seed_sets(
            activity_id,
            ["continuous"],
            ["threshold"],
            source="classifier",
        )
        self._item(
            activity_id,
            evidence_source="tag",
            methods=["intervals"],
            targets=["lt1"],
            stored_methods=["continuous"],
            stored_targets=["threshold"],
        )
        self._run(EVIDENCE)

        again = self._run(EVIDENCE, force=True)

        self.assertEqual(0, again.counts.get("items", 0))
        self.assertEqual(
            (["intervals"], ["lt1"]),
            self._sets(activity_id),
        )


class DrillsBackfillTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _activity(self, *, tags=(), with_set=True, manual=False):
        self.counter += 1
        activity_id = f"d{self.counter}"
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "Session",
                "duration_s": 3600,
            },
            source="fit",
            source_record_id=None,
        )
        if tags:
            self.writer.replace_activity_tags(
                activity_id, list(tags), source="runalyze"
            )
        if with_set:
            self.writer.replace_activity_workout_methods(
                activity_id,
                ["intervals"],
                source="sheet",
                is_manual=manual,
            )
            self.writer.replace_activity_workout_targets(
                activity_id,
                ["other"],
                source="sheet",
                is_manual=manual,
            )
        self.conn.commit()
        return activity_id

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(DRILLS), **kwargs)

    def _sets(self, activity_id):
        methods = sorted(
            row["method"]
            for row in self.conn.execute(
                "SELECT method FROM activity_workout_methods "
                "WHERE activity_id = ?",
                (activity_id,),
            )
        )
        targets = sorted(
            row["target"]
            for row in self.conn.execute(
                "SELECT target FROM activity_workout_targets "
                "WHERE activity_id = ?",
                (activity_id,),
            )
        )
        return methods, targets

    def test_a_drills_tag_adds_the_method_without_replacing_the_run(self):
        activity_id = self._activity(tags=["LTT"])

        result = self._run()

        self.assertEqual(1, result.counts["added"])
        self.assertEqual(
            (["drills", "intervals"], ["other"]),
            self._sets(activity_id),
        )
        sources = {
            row["method"]: row["source"]
            for row in self.conn.execute(
                "SELECT method, source FROM activity_workout_methods "
                "WHERE activity_id = ?",
                (activity_id,),
            )
        }
        self.assertEqual("tag", sources["drills"])
        self.assertEqual("sheet", sources["intervals"])

    def test_a_manual_set_is_skipped(self):
        activity_id = self._activity(tags=["Lauftechnik"], manual=True)

        result = self._run()

        self.assertEqual(1, result.counts["skipped_manual"])
        self.assertEqual(
            (["intervals"], ["other"]),
            self._sets(activity_id),
        )

    def test_an_activity_without_a_set_is_skipped(self):
        self._activity(tags=["LTT"], with_set=False)

        result = self._run()

        self.assertEqual(1, result.counts["no_set"])

    def test_a_second_run_is_a_no_op(self):
        activity_id = self._activity(tags=["LTT"])
        self._run()

        again = self._run(force=True)

        self.assertEqual(1, again.counts["unchanged"])
        self.assertEqual(
            (["drills", "intervals"], ["other"]),
            self._sets(activity_id),
        )


if __name__ == "__main__":
    unittest.main()
