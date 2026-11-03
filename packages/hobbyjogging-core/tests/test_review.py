import unittest

from hobbyjogging_core import TrainingRepository, TrainingWriter, connect, migrate
from hobbyjogging_core.db.migrations import SCHEMA_VERSION


class ReviewItemTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        self.assertEqual(SCHEMA_VERSION, migrate(self.conn))
        self.writer = TrainingWriter(self.conn)
        self.repository = TrainingRepository(self.conn)
        self._seed()

    def _seed(self):
        self.run_id = self.writer.start_import_run("test")
        self.source_record_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="seg.fit",
            checksum="c1",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "started_at_utc": "2026-10-01T06:00:00Z",
                "duration_s": 3600,
                "elapsed_s": 3700,
            },
            source="fit",
            source_record_id=self.source_record_id,
        )
        self.writer.link_activity_source(
            "a1", self.source_record_id, match_method="created"
        )

    def test_record_review_item_is_idempotent(self):
        first_id, created = self.writer.record_review_item(
            category="quality",
            detail="zero duration",
            fingerprint="fp-1",
            activity_id="a1",
            source_record_id=self.source_record_id,
            import_run_id=self.run_id,
            context={"rule": "zero_duration"},
        )
        second_id, created_again = self.writer.record_review_item(
            category="quality",
            detail="zero duration",
            fingerprint="fp-1",
            activity_id="a1",
            source_record_id=self.source_record_id,
        )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first_id, second_id)

        count = self.conn.execute(
            "SELECT COUNT(*) FROM review_items"
        ).fetchone()[0]
        self.assertEqual(1, count)

    def test_record_review_item_distinguishes_scopes(self):
        self.writer.record_review_item(
            category="quality",
            detail="activity scoped",
            fingerprint="fp-1",
            activity_id="a1",
        )
        activity_scoped = self.writer.review_items()
        self.assertEqual(1, len(activity_scoped))

        record_only, created = self.writer.record_review_item(
            category="quality",
            detail="record scoped",
            fingerprint="fp-1",
        )
        all_items = self.writer.review_items()
        self.assertEqual(2, len(all_items))
        self.assertIsNone(all_items[-1]["activity_id"])
        self.assertTrue(created)
        self.assertGreater(record_only, activity_scoped[0]["id"])

    def test_resolved_items_are_not_reopened(self):
        item_id, _ = self.writer.record_review_item(
            category="ambiguous_match",
            detail="two candidates",
            fingerprint="fp-a",
            source_record_id=self.source_record_id,
            context={"candidates": ["a", "b"]},
        )
        self.writer.set_review_status(item_id, "resolved", note="picked a")

        again_id, _ = self.writer.record_review_item(
            category="ambiguous_match",
            detail="two candidates",
            fingerprint="fp-a",
            source_record_id=self.source_record_id,
        )

        self.assertEqual(item_id, again_id)

        row = self.conn.execute(
            "SELECT status FROM review_items WHERE id = ?", (item_id,)
        ).fetchone()
        self.assertEqual("resolved", row["status"])

    def test_set_review_status_validates_and_timestamps(self):
        item_id, _ = self.writer.record_review_item(
            category="quality",
            detail="bad data",
            fingerprint="fp-s",
            activity_id="a1",
        )

        with self.assertRaises(ValueError):
            self.writer.set_review_status(item_id, "bogus")

        self.writer.set_review_status(item_id, "ignored", note="leave it")
        row = self.conn.execute(
            "SELECT status, resolved_at, resolved_note "
            "FROM review_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        self.assertEqual("ignored", row["status"])
        self.assertIsNotNone(row["resolved_at"])
        self.assertEqual("leave it", row["resolved_note"])

        self.writer.set_review_status(item_id, "open")
        row = self.conn.execute(
            "SELECT status, resolved_at FROM review_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        self.assertEqual("open", row["status"])
        self.assertIsNone(row["resolved_at"])

    def test_resolve_review_match_relinks_source_record(self):
        ambiguous_record = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="ambiguous.fit",
            checksum="c2",
            import_run_id=self.run_id,
        )
        item_id, _ = self.writer.record_review_item(
            category="ambiguous_match",
            detail="two candidates",
            fingerprint="fp-m",
            source_record_id=ambiguous_record,
            context={"candidates": ["a1", "a2"]},
        )

        self.writer.resolve_review_match(item_id, "a1", note="first was right")

        links = self.conn.execute(
            """
            SELECT activity_id, match_method FROM activity_sources
            WHERE source_record_id = ?
            """,
            (ambiguous_record,),
        ).fetchall()
        self.assertEqual(1, len(links))
        self.assertEqual("a1", links[0]["activity_id"])
        self.assertEqual("review_resolved", links[0]["match_method"])

        row = self.conn.execute(
            "SELECT status FROM review_items WHERE id = ?", (item_id,)
        ).fetchone()
        self.assertEqual("resolved", row["status"])

    def test_resolve_review_match_validations(self):
        missing_record, _ = self.writer.record_review_item(
            category="quality",
            detail="no source record",
            fingerprint="fp-n",
            activity_id="a1",
        )
        with self.assertRaises(ValueError):
            self.writer.resolve_review_match(missing_record, "a1")

        unknown_item = 999
        with self.assertRaises(ValueError):
            self.writer.resolve_review_match(unknown_item, "a1")

        unknown_activity, _ = self.writer.record_review_item(
            category="ambiguous_match",
            detail="orphan",
            fingerprint="fp-o",
            source_record_id=self.source_record_id,
        )
        with self.assertRaises(ValueError):
            self.writer.resolve_review_match(unknown_activity, "nope")

        self.writer.set_review_status(unknown_activity, "open")
        still_open = self.writer.review_items(status="open")
        self.assertEqual(2, len(still_open))

    def test_repository_flags_activities_with_open_review_items(self):
        self.writer.record_review_item(
            category="quality",
            detail="suspect gps",
            fingerprint="fp-r",
            activity_id="a1",
        )

        activities = self.repository.activities(
            __import__("datetime").date(2026, 10, 1),
            __import__("datetime").date(2026, 10, 1),
        )
        self.assertEqual(1, len(activities))
        self.assertTrue(activities[0].needs_review)

        item_id = self.writer.review_items(status="open")[0]["id"]
        self.writer.set_review_status(item_id, "resolved")

        activities = self.repository.activities(
            __import__("datetime").date(2026, 10, 1),
            __import__("datetime").date(2026, 10, 1),
        )
        self.assertFalse(activities[0].needs_review)


if __name__ == "__main__":
    unittest.main()
