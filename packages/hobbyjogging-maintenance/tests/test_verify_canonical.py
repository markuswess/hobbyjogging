import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.intervals import _activity_values

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "verify_canonical"

PAYLOAD = {
    "start_date": "2026-10-01T06:00:00Z",
    "start_date_local": "2026-10-01T08:00:00",
    "type": "Run",
    "name": "Morning run",
    "description": "Easy",
    "icu_recording_time": 3600,
    "elapsed_time": 3700,
    "distance": 10000.0,
    "average_heartrate": 140,
    "max_heartrate": 160,
    "total_elevation_gain": 50.0,
    "icu_training_load": 50,
}


class VerifyCanonicalTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.record_id = self._record("intervals", "i1", PAYLOAD)
        self._activity("a1", PAYLOAD)

    def _record(self, source, external_id, payload):
        return self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=external_id,
            checksum=f"c-{external_id}",
            payload_json=json.dumps(payload),
            import_run_id=self.run_id,
        )

    def _activity(self, activity_id, payload, *, source="intervals"):
        record_id = self.record_id
        self.writer.upsert_activity(
            activity_id,
            _activity_values(payload),
            source=source,
            source_record_id=record_id,
        )
        self.conn.commit()
        return activity_id

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def test_a_clean_activity_has_no_drift(self):
        result = self._run()

        self.assertEqual(0, result.counts["drift"])
        self.assertGreater(result.counts["ok"], 5)

    def test_a_tampered_value_is_drift(self):
        self.conn.execute(
            "UPDATE activities SET distance_m = 9999 WHERE id = 'a1'"
        )
        self.conn.commit()

        result = self._run()

        self.assertEqual(1, result.counts["drift"])
        self.assertTrue(
            any("distance_m" in line for line in result.notes)
        )

    def test_a_manual_value_is_compared(self):
        self.writer.set_manual_field("a1", "distance_m", 8000.0)

        result = self._run()

        self.assertEqual(0, result.counts["drift"])

    def test_an_owner_patch_uses_the_chosen_source(self):
        self.writer.set_manual_owner("a1", "distance_m", "intervals")

        result = self._run()

        self.assertEqual(0, result.counts["drift"])

    def test_a_missing_record_is_dangling(self):
        self.conn.execute(
            "UPDATE activity_field_sources SET source_record_id = NULL "
            "WHERE activity_id = 'a1' AND field_name = 'distance_m'"
        )
        self.conn.execute(
            "DELETE FROM activity_sources WHERE activity_id = 'a1'"
        )
        self.conn.commit()

        result = self._run()

        self.assertGreaterEqual(result.counts["dangling"], 1)

    def test_an_unmapped_source_is_reported(self):
        strava_id = self._record("strava", "s1", {})
        self.conn.execute(
            "UPDATE activity_field_sources "
            "SET source = 'strava', source_record_id = ? "
            "WHERE activity_id = 'a1' AND field_name = 'distance_m'",
            (strava_id,),
        )
        self.conn.commit()

        result = self._run()

        self.assertGreaterEqual(result.counts["unmapped"], 1)

    def test_the_distance_policy_is_applied(self):
        payload = dict(PAYLOAD, type="TreadmillRun", distance=5000.0)
        record_id = self._record("intervals", "i2", payload)
        self.writer.upsert_activity(
            "a2",
            _activity_values(payload),
            source="intervals",
            source_record_id=record_id,
        )
        self.conn.commit()

        result = self._run()

        self.assertEqual(0, result.counts["drift"])


if __name__ == "__main__":
    unittest.main()
