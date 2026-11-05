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

    def test_source_record_is_not_part_of_item_identity(self):
        second_source_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="second.fit",
            checksum="c2",
            import_run_id=self.run_id,
        )

        first_id, created = self.writer.record_review_item(
            category="quality",
            detail="zero duration",
            fingerprint="fp-1",
            activity_id="a1",
            source_record_id=self.source_record_id,
        )
        second_id, created_again = self.writer.record_review_item(
            category="quality",
            detail="zero duration",
            fingerprint="fp-1",
            activity_id="a1",
            source_record_id=second_source_id,
        )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first_id, second_id)
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM review_items"
            ).fetchone()[0],
        )

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


class ExclusionTests(unittest.TestCase):
    """Durable soft-deletion: exclusion hides data without hard deletes."""

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        self.assertEqual(SCHEMA_VERSION, migrate(self.conn))
        self.writer = TrainingWriter(self.conn)
        self.repository = TrainingRepository(self.conn)

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
        self.item_id, _ = self.writer.record_review_item(
            category="quality",
            detail="zero duration",
            fingerprint="fp-x",
            activity_id="a1",
        )

    def _activity_row(self):
        return self.conn.execute(
            "SELECT excluded_at FROM activities WHERE id = 'a1'"
        ).fetchone()

    def _source_row(self):
        return self.conn.execute(
            "SELECT excluded_at FROM source_records WHERE id = ?",
            (self.source_record_id,),
        ).fetchone()

    def _repository_activities(self):
        import datetime

        return self.repository.activities(
            datetime.date(2026, 10, 1),
            datetime.date(2026, 10, 1),
        )

    def test_exclude_marks_activity_source_record_and_resolves_items(self):
        resolved = self.writer.exclude_activity("a1", resolve_note="triage")
        self.conn.commit()

        self.assertEqual(1, resolved)
        self.assertIsNotNone(self._activity_row()["excluded_at"])
        self.assertIsNotNone(self._source_row()["excluded_at"])

        item = self.writer.review_item(self.item_id)
        self.assertEqual("resolved", item["status"])
        self.assertEqual("triage", item["resolved_note"])

        self.assertEqual([], self._repository_activities())

    def test_exclude_is_idempotent(self):
        self.writer.exclude_activity("a1")
        first_note = self.writer.review_item(self.item_id)["resolved_note"]

        self.writer.exclude_activity("a1", resolve_note="second pass")
        self.conn.commit()

        self.assertEqual(
            first_note,
            self.writer.review_item(self.item_id)["resolved_note"],
        )

    def test_restore_clears_exclusion_but_keeps_items_resolved(self):
        self.writer.exclude_activity("a1", resolve_note="triage")
        self.writer.restore_activity("a1")
        self.conn.commit()

        self.assertIsNone(self._activity_row()["excluded_at"])
        self.assertIsNone(self._source_row()["excluded_at"])

        item = self.writer.review_item(self.item_id)
        self.assertEqual("resolved", item["status"])
        self.assertEqual(1, len(self._repository_activities()))

    def test_exclude_unknown_activity_raises(self):
        with self.assertRaises(ValueError):
            self.writer.exclude_activity("nope")

    def test_upsert_activity_rejects_excluded_activity(self):
        self.writer.exclude_activity("a1")
        self.conn.commit()

        with self.assertRaises(ValueError):
            self.writer.upsert_activity(
                "a1",
                {"duration_s": 999},
                source="fit",
                source_record_id=self.source_record_id,
            )

        row = self.conn.execute(
            "SELECT duration_s FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(3600, row["duration_s"])

    def test_link_activity_source_rejects_excluded_activity(self):
        self.writer.exclude_activity("a1")
        self.conn.commit()

        with self.assertRaises(ValueError):
            self.writer.link_activity_source("a1", self.source_record_id)

    def test_is_excluded_helpers(self):
        self.assertFalse(self.writer.is_activity_excluded("a1"))
        self.writer.exclude_activity("a1")
        self.conn.commit()

        self.assertTrue(self.writer.is_activity_excluded("a1"))
        self.assertTrue(self.writer.is_activity_excluded(None) is False)
        self.assertFalse(self.writer.is_activity_excluded("nope"))
        self.assertTrue(
            self.writer.is_source_record_excluded(
                source="fit",
                record_type="activity",
                external_id="seg.fit",
            )
        )
        self.assertFalse(
            self.writer.is_source_record_excluded(
                source="fit",
                record_type="activity",
                external_id="other.fit",
            )
        )


class ManualFieldTests(unittest.TestCase):
    """Manual field overrides outrank all import sources."""

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        self.assertEqual(SCHEMA_VERSION, migrate(self.conn))
        self.writer = TrainingWriter(self.conn)

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
                "distance_m": 10000,
            },
            source="fit",
            source_record_id=self.source_record_id,
        )
        self.writer.link_activity_source(
            "a1", self.source_record_id, match_method="created"
        )

    def _field_row(self, field_name):
        return self.conn.execute(
            """
            SELECT source, is_manual, value_json
            FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = ?
            """,
            (field_name,),
        ).fetchone()

    def _activity_value(self, column):
        return self.conn.execute(
            f"SELECT {column} FROM activities WHERE id = 'a1'"
        ).fetchone()[0]

    def _reimport(self, duration_s=999):
        self.writer.upsert_activity(
            "a1",
            {"duration_s": duration_s},
            source="fit",
            source_record_id=self.source_record_id,
        )

    def test_set_manual_field_writes_value_and_source(self):
        self.writer.set_manual_field("a1", "duration_s", 2780)
        self.conn.commit()

        self.assertEqual(2780, self._activity_value("duration_s"))
        row = self._field_row("duration_s")
        self.assertEqual("manual", row["source"])
        self.assertEqual(1, row["is_manual"])
        self.assertEqual("2780", str(row["value_json"]).strip('"'))

    def test_manual_value_survives_reimport(self):
        self.writer.set_manual_field("a1", "duration_s", 2780)
        self._reimport(duration_s=999)
        self.conn.commit()

        self.assertEqual(2780, self._activity_value("duration_s"))
        self.assertEqual(
            "manual",
            self._field_row("duration_s")["source"],
        )

    def test_clear_manual_field_hands_field_back_to_imports(self):
        self.writer.set_manual_field("a1", "duration_s", 2780)

        self.assertTrue(self.writer.clear_manual_field("a1", "duration_s"))
        self._reimport(duration_s=999)
        self.conn.commit()

        self.assertEqual(999, self._activity_value("duration_s"))
        row = self._field_row("duration_s")
        self.assertEqual("fit", row["source"])
        self.assertEqual(0, row["is_manual"])

    def test_clear_missing_override_is_a_noop(self):
        self.assertFalse(self.writer.clear_manual_field("a1", "duration_s"))

    def test_invalid_field_rejected(self):
        with self.assertRaises(ValueError):
            self.writer.set_manual_field("a1", "name", "Not allowed")
        with self.assertRaises(ValueError):
            self.writer.clear_manual_field("a1", "name")

    def test_unknown_and_excluded_activities_rejected(self):
        with self.assertRaises(ValueError):
            self.writer.set_manual_field("nope", "duration_s", 100)
        self.writer.exclude_activity("a1")
        with self.assertRaises(ValueError):
            self.writer.set_manual_field("a1", "duration_s", 100)


if __name__ == "__main__":
    unittest.main()
