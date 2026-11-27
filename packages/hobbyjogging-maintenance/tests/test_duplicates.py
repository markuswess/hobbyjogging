import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.context import Scope
from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

DETECT = "duplicate_candidates_current"
CLEAN = "sheet_duplicates_v1"


class DuplicateTasksTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _activity(
        self,
        activity_id,
        *,
        source="fit",
        day="2026-10-01",
        sport="run",
        distance=10000.0,
        duration=3600.0,
        start="2026-10-01T08:00:00Z",
        avg_hr=None,
        description="",
    ):
        self.counter += 1
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=f"{source}-{activity_id}-{self.counter}",
            checksum=f"c-{source}-{activity_id}-{self.counter}",
            import_run_id=self.run_id,
        )
        values = {
            "local_date": day,
            "sport": sport,
            "distance_m": distance,
            "duration_s": duration,
        }
        if start is not None:
            values["started_at_utc"] = start
        if avg_hr is not None:
            values["avg_hr"] = avg_hr
        if description:
            values["description"] = description
        self.writer.upsert_activity(
            activity_id,
            values,
            source=source,
            source_record_id=record_id,
        )
        self.writer.link_activity_source(activity_id, record_id)
        self.conn.commit()
        return activity_id

    def _run(self, task, **kwargs):
        result = run_task(self.conn, get_task(task), **kwargs)
        self.assertEqual("ok", result.status, result.error)
        return result

    def _items(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM review_items WHERE category = 'duplicate' "
                "ORDER BY id"
            )
        ]

    def _excluded(self, activity_id):
        return self.conn.execute(
            "SELECT excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()["excluded_at"]

    # -- detection -------------------------------------------------------

    def test_detection_opens_one_item_linked_to_the_sheet(self):
        self._activity("sheet", source="sheet")
        self._activity("device", source="fit")

        result = self._run(DETECT)

        self.assertEqual(1, result.counts["pairs"])
        self.assertEqual(1, result.counts["opened"])
        item = self._items()[0]
        self.assertEqual("sheet", item["activity_id"])
        context = json.loads(item["context_json"])
        self.assertEqual(["device", "sheet"], context["activities"])

    def test_detection_is_idempotent(self):
        self._activity("sheet", source="sheet")
        self._activity("device", source="fit")
        self._run(DETECT)

        second = self._run(DETECT)

        self.assertEqual(0, second.counts["opened"])
        self.assertEqual(1, second.counts["unchanged"])
        self.assertEqual(1, len(self._items()))

    def test_excluding_the_linked_copy_resolves_the_item(self):
        self._activity("sheet", source="sheet")
        self._activity("device", source="fit")
        self._run(DETECT)

        self.writer.exclude_activity("sheet")
        self.conn.commit()
        result = self._run(DETECT)

        self.assertEqual(0, result.counts["pairs"])
        self.assertEqual("resolved", self._items()[0]["status"])

    def test_two_device_rows_link_the_one_with_fewer_sources(self):
        self._activity("one", source="fit")
        self._activity("two", source="fit")
        # Give "two" a second source without changing the pair.
        self._activity("two", source="intervals")

        self._run(DETECT)

        self.assertEqual("one", self._items()[0]["activity_id"])

    def test_different_sports_are_not_duplicates(self):
        self._activity("run", source="fit")
        self._activity("ride", source="fit", sport="ride")

        result = self._run(DETECT)

        self.assertEqual(0, result.counts["pairs"])

    def test_two_same_day_sessions_hours_apart_are_not_duplicates(self):
        self._activity(
            "morning",
            source="fit",
            start="2026-10-01T06:00:00Z",
        )
        self._activity(
            "evening",
            source="intervals",
            start="2026-10-01T16:00:00Z",
        )

        result = self._run(DETECT)

        self.assertEqual(0, result.counts["pairs"])
        self.assertEqual([], self._items())

    def test_a_sheet_row_without_a_start_still_matches(self):
        self._activity("sheet", source="sheet", start=None)
        self._activity("device", source="fit")

        result = self._run(DETECT)

        self.assertEqual(1, result.counts["pairs"])
        self.assertEqual("sheet", self._items()[0]["activity_id"])

    # -- sheet cleanup ---------------------------------------------------

    def test_dry_run_copies_nothing_and_excludes_nothing(self):
        self._activity("sheet", source="sheet", description="with Vicky")
        self._activity("device", source="fit")

        result = self._run(CLEAN, dry_run=True)

        self.assertEqual(1, result.counts["pairs"])
        self.assertIsNone(self._excluded("sheet"))
        self.assertEqual(
            "", self._description("device")
        )

    def test_cleanup_copies_the_text_and_excludes_the_sheet(self):
        self._activity("sheet", source="sheet", description="with Vicky")
        self._activity("device", source="fit")

        result = self._run(CLEAN)

        self.assertEqual(1, result.counts["excluded"])
        self.assertEqual(1, result.counts["description_filled"])
        self.assertIsNotNone(self._excluded("sheet"))
        self.assertEqual("with Vicky", self._description("device"))
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM edit_log "
                "WHERE source = 'sheet-duplicate'"
            ).fetchone()[0],
        )

    def test_device_text_is_not_overwritten(self):
        self._activity("sheet", source="sheet", description="sheet text")
        self._activity("device", source="fit", description="device text")

        result = self._run(CLEAN)

        self.assertEqual(1, result.counts["description_kept"])
        self.assertEqual("device text", self._description("device"))
        self.assertIsNotNone(self._excluded("sheet"))

    def test_a_sheet_row_without_text_is_still_excluded(self):
        self._activity("sheet", source="sheet")
        self._activity("device", source="fit")

        result = self._run(CLEAN)

        self.assertEqual(1, result.counts["no_text"])
        self.assertIsNotNone(self._excluded("sheet"))

    def test_two_device_candidates_are_ambiguous(self):
        self._activity("sheet", source="sheet", description="text")
        self._activity("one", source="fit")
        self._activity("two", source="intervals")

        result = self._run(CLEAN)

        self.assertEqual(1, result.counts["ambiguous"])
        self.assertIsNone(self._excluded("sheet"))

    def test_non_sheet_pairs_are_left_for_review(self):
        self._activity("one", source="fit", description="one")
        self._activity("two", source="intervals", description="two")

        result = self._run(CLEAN)

        self.assertEqual(0, result.counts["pairs"])
        self.assertIsNone(self._excluded("one"))
        self.assertIsNone(self._excluded("two"))

    def test_second_cleanup_is_skipped_as_applied(self):
        self._activity("sheet", source="sheet")
        self._activity("device", source="fit")
        self._run(CLEAN)

        second = run_task(self.conn, get_task(CLEAN))

        self.assertEqual("skipped", second.status)
        self.assertIsNotNone(self._excluded("sheet"))

    def test_scope_limits_the_sheet_rows(self):
        self._activity("sheet1", source="sheet")
        self._activity("device1", source="fit")
        self._activity("sheet2", source="sheet", day="2026-10-02",
                       start="2026-10-02T08:00:00Z")
        self._activity("device2", source="fit", day="2026-10-02",
                       start="2026-10-02T08:00:00Z")

        self._run(CLEAN, scope=Scope(entity_id="sheet1"))

        self.assertIsNotNone(self._excluded("sheet1"))
        self.assertIsNone(self._excluded("sheet2"))

    def _description(self, activity_id):
        return self.conn.execute(
            "SELECT description FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()["description"]


if __name__ == "__main__":
    unittest.main()
