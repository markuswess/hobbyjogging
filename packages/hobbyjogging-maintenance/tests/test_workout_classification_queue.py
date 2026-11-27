import json
import unittest
from unittest.mock import patch

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_core.classify import Category

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "workout_classification_queue"
CLASSIFY = "hobbyjogging_maintenance.workouts.classify"

UNKNOWN = Category("unknown")
LONGRUN = Category("quality", "longrun")
TEMPO = Category("quality", "tempo")


class QueueTests(unittest.TestCase):

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
        code=None,
        sheet=True,
        intensity=None,
        description="",
        tags=None,
        sport="run",
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
            "duration_s": 3600,
        }
        if description:
            values["description"] = description
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
                source="runalyze",
            )
        self.conn.commit()
        return activity_id

    def _items(self, status="open"):
        return self.conn.execute(
            """
            SELECT * FROM review_items
            WHERE category = 'workout_classification' AND status = ?
            ORDER BY id
            """,
            (status,),
        ).fetchall()

    def _classify_manually(self, activity_id, methods, targets):
        self.writer.replace_activity_workout_methods(
            activity_id, methods, source="manual", is_manual=True
        )
        self.writer.replace_activity_workout_targets(
            activity_id, targets, source="manual", is_manual=True
        )
        self.conn.commit()

    def test_conflict_creates_one_info_item(self):
        activity_id = self._activity("Long run", code="i")

        with patch(CLASSIFY, return_value=LONGRUN):
            run = self._run()

        self.assertEqual(1, run.counts["opened"])
        items = self._items()
        self.assertEqual(1, len(items))
        self.assertEqual("info", items[0]["severity"])
        self.assertEqual(activity_id, items[0]["activity_id"])
        self.assertEqual("classifier vs sheet (i) disagree", items[0]["detail"])

        context = json.loads(items[0]["context_json"])
        self.assertEqual(["long_run"], context["classifier_methods"])
        self.assertEqual(["base"], context["classifier_targets"])
        self.assertEqual(["intervals"], context["sheet_methods"])
        self.assertEqual("i", context["sheet_code"])

    def test_rerun_does_not_duplicate(self):
        self._activity("Long run", code="i")

        with patch(CLASSIFY, return_value=LONGRUN):
            self._run()
            second = self._run()

        self.assertEqual(1, second.counts["unchanged"])
        self.assertEqual(0, second.counts["opened"])
        self.assertEqual(1, len(self._items()))

    def test_agreeing_proposals_create_nothing(self):
        self._activity("Tempo", code="tdl")

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(0, run.counts["opened"])
        self.assertEqual([], self._items())

    def test_classified_activity_has_no_item(self):
        activity_id = self._activity("Long run", code="i")
        self._classify_manually(activity_id, ["continuous"], ["base"])

        with patch(CLASSIFY, return_value=LONGRUN):
            self._run()

        self.assertEqual([], self._items())

    def _sets(self, activity_id):
        methods = sorted(
            row[0]
            for row in self.conn.execute(
                "SELECT method FROM activity_workout_methods "
                "WHERE activity_id = ?",
                (activity_id,),
            )
        )
        targets = sorted(
            row[0]
            for row in self.conn.execute(
                "SELECT target FROM activity_workout_targets "
                "WHERE activity_id = ?",
                (activity_id,),
            )
        )
        return methods, targets

    def test_classified_evidence_never_opens_an_item(self):
        activity_id = self._activity("Steady run", tags=["LT1"])
        self._classify_manually(activity_id, ["continuous"], ["base"])

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(0, run.counts["opened"])
        self.assertEqual([], self._items())
        self.assertEqual(
            (["continuous"], ["base"]),
            self._sets(activity_id),
        )

    def test_comment_evidence_never_opens_an_item(self):
        activity_id = self._activity(
            "Steady run",
            description="Tempo run",
        )
        self._classify_manually(activity_id, ["intervals"], ["vo2max"])

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(0, run.counts["opened"])
        self.assertEqual([], self._items())

    def test_an_open_evidence_item_is_resolved(self):
        activity_id = self._activity("Steady run", tags=["LT1"])
        self._classify_manually(activity_id, ["continuous"], ["base"])
        item_id, _ = self.writer.record_review_item(
            category="workout_classification",
            detail="tag evidence vs stored classification",
            context={
                "evidence_source": "tag",
                "evidence_methods": ["intervals"],
                "evidence_targets": ["lt1"],
                "stored_methods": ["continuous"],
                "stored_targets": ["base"],
            },
            severity="info",
            fingerprint="fp-stale-evidence",
            activity_id=activity_id,
        )
        self.conn.commit()

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(1, run.counts["resolved"])
        self.assertEqual("resolved", self.writer.review_item(item_id)["status"])
        self.assertEqual("classified", self.writer.review_item(item_id)["resolved_note"])
        self.assertEqual([], self._items())

    def test_agreeing_evidence_creates_nothing(self):
        activity_id = self._activity("Steady run", tags=["LT1"])
        self._classify_manually(activity_id, ["intervals"], ["lt1"])

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(0, run.counts["opened"])
        self.assertEqual([], self._items())

    def test_evidence_is_ignored_for_a_non_run_sport(self):
        activity_id = self._activity("Ride", tags=["LT1"], sport="ride")
        self._classify_manually(activity_id, ["intervals"], ["lt1"])

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(0, run.counts["opened"])
        self.assertEqual([], self._items())

    def test_manual_classification_resolves_an_open_item(self):
        activity_id = self._activity("Long run", code="i")

        with patch(CLASSIFY, return_value=LONGRUN):
            self._run()

        self.assertEqual(1, len(self._items()))
        self._classify_manually(activity_id, ["long_run"], ["base"])

        with patch(CLASSIFY, return_value=LONGRUN):
            run = self._run()

        self.assertEqual(1, run.counts["resolved"])
        self.assertEqual([], self._items())
        self.assertEqual(1, len(self._items(status="resolved")))

    def test_changed_proposals_supersede_the_old_item(self):
        self._activity("Long run", code="i")

        with patch(CLASSIFY, return_value=LONGRUN):
            self._run()

        with patch(CLASSIFY, return_value=TEMPO):
            run = self._run()

        self.assertEqual(1, run.counts["superseded"])
        self.assertEqual(1, run.counts["opened"])
        self.assertEqual(1, len(self._items()))
        resolved = self._items(status="resolved")
        self.assertEqual(1, len(resolved))
        self.assertIn("superseded", resolved[0]["resolved_note"])

    def test_a_resolved_decision_is_not_reopened(self):
        self._activity("Long run", code="i")

        with patch(CLASSIFY, return_value=LONGRUN):
            self._run()

        # Triage "none": resolve without classifying.
        self.writer.set_review_status(
            self._items()[0]["id"], "resolved", note="triage: left unclassified"
        )
        self.conn.commit()

        with patch(CLASSIFY, return_value=LONGRUN):
            run = self._run()

        self.assertEqual([], self._items())
        self.assertEqual(1, run.counts["unchanged"])

    def test_unclassified_and_unproposed_activity_is_ignored(self):
        self._activity("Morning run", sheet=False)

        with patch(CLASSIFY, return_value=UNKNOWN):
            run = self._run()

        self.assertEqual(0, run.counts["opened"])
        self.assertEqual([], self._items())


if __name__ == "__main__":
    unittest.main()
