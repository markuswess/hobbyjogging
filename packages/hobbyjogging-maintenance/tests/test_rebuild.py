import json
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import TrainingWriter, open_database

from hobbyjogging_maintenance.rebuild import format_rebuild_report, rebuild

PAYLOAD = {
    "start_date": "2026-10-01T06:00:00Z",
    "start_date_local": "2026-10-01T08:00:00",
    "type": "Run",
    "icu_recording_time": 3600,
    "elapsed_time": 3700,
    "distance": 10000,
    "average_heartrate": 150,
    "max_heartrate": 170,
    "icu_training_load": 100,
}


class RebuildTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.db"
        self._build_source()

    def _build_source(self):
        connection = open_database(self.source)
        writer = TrainingWriter(connection)
        run_id = writer.start_import_run("test")
        for index, activity_id in enumerate(("a1", "a2"), start=1):
            payload = dict(PAYLOAD)
            payload["id"] = index
            record_id = writer.upsert_source_record(
                source="intervals",
                record_type="activity",
                external_id=activity_id,
                checksum=f"c-{activity_id}",
                payload_json=json.dumps(payload),
                import_run_id=run_id,
            )
            writer.upsert_activity(
                activity_id,
                {
                    "local_date": "2026-10-01",
                    "sport": "run",
                    "duration_s": 3600,
                    "elapsed_s": 3700,
                    "distance_m": 10000,
                    "avg_hr": 150,
                    "max_hr": 170,
                    "training_load": 100,
                },
                source="intervals",
                source_record_id=record_id,
            )
            writer.link_activity_source(activity_id, record_id)

        writer.set_manual_field("a1", "avg_hr", 160)
        writer.exclude_activity("a2")
        item_id, _ = writer.record_review_item(
            category="field_conflict",
            detail="test conflict",
            fingerprint="fp-1",
            activity_id="a1",
        )
        writer.set_review_status(item_id, "ignored", note="known")
        connection.commit()
        connection.close()

    def test_a_rebuild_reproduces_the_canonical_layer(self):
        target = self.root / "rebuilt.db"

        report = rebuild(self.source, target=target)

        self.assertTrue(report.ok, report.drifts)
        self.assertEqual(0, report.drift)
        self.assertEqual(1, report.activities)
        self.assertTrue(report.exclusions_match)
        self.assertEqual(1, report.overlay.manual_fields)
        self.assertEqual(1, report.overlay.exclusions)
        self.assertEqual(1, report.overlay.review_answers)
        self.assertTrue(target.is_file())

        connection = open_database(target)
        try:
            row = connection.execute(
                "SELECT avg_hr FROM activities WHERE id = 'a1'"
            ).fetchone()
            self.assertEqual(160, row["avg_hr"])
            excluded = connection.execute(
                "SELECT excluded_at FROM activities WHERE id = 'a2'"
            ).fetchone()
            self.assertIsNotNone(excluded["excluded_at"])
        finally:
            connection.close()

    def test_a_tampered_live_value_shows_drift(self):
        connection = open_database(self.source)
        try:
            connection.execute(
                "UPDATE activities SET distance_m = 9999 WHERE id = 'a1'"
            )
            connection.commit()
        finally:
            connection.close()

        report = rebuild(self.source)

        self.assertFalse(report.ok)
        self.assertEqual(1, report.drift)
        self.assertTrue(any("distance_m" in line for line in report.drifts))
        self.assertIn("FAILED", format_rebuild_report(report))

    def test_the_report_counts_the_overlay(self):
        report = rebuild(self.source)

        text = format_rebuild_report(report)

        self.assertIn("Rebuild check", text)
        self.assertIn("activities: 1", text)
        self.assertIn("OK: empty canonical diff", text)
        self.assertIn("temporary", text)


if __name__ == "__main__":
    unittest.main()
