import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.intervals import _activity_values

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "recompute_canonical"

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


class RecomputeCanonicalTests(unittest.TestCase):

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

    def _activity(self, activity_id, payload, *, record_id=None):
        self.writer.upsert_activity(
            activity_id,
            _activity_values(payload),
            source="intervals",
            source_record_id=record_id or self.record_id,
        )
        self.conn.commit()
        return activity_id

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _field(self, field="distance_m", activity_id="a1"):
        return self.conn.execute(
            f"SELECT {field} FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()[0]

    def _snapshot(self, field="distance_m"):
        row = self.conn.execute(
            """
            SELECT value_json FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = ?
            """,
            (field,),
        ).fetchone()
        return row["value_json"]

    def _tamper(self, value=9999.0):
        self.conn.execute(
            "UPDATE activities SET distance_m = ? WHERE id = 'a1'",
            (value,),
        )
        self.conn.commit()

    def test_a_clean_activity_is_unchanged(self):
        result = self._run()

        self.assertEqual(0, result.counts["written"])
        self.assertGreater(result.counts["unchanged"], 5)

    def test_a_tampered_value_is_restored_and_the_snapshot_refreshed(self):
        self._tamper()

        result = self._run()

        self.assertEqual(1, result.counts["written"])
        self.assertEqual(10000.0, self._field())
        self.assertEqual("10000.0", self._snapshot())

    def test_a_manual_value_is_restored_without_touching_the_snapshot(self):
        self.writer.set_manual_field("a1", "distance_m", 8000.0)
        self._tamper()

        result = self._run()

        self.assertEqual(1, result.counts["written"])
        self.assertEqual(8000.0, self._field())
        self.assertEqual("10000.0", self._snapshot())

    def test_an_owner_patch_uses_the_chosen_source(self):
        self.writer.set_manual_owner("a1", "distance_m", "intervals")
        self._tamper()

        self._run()

        self.assertEqual(10000.0, self._field())

    def test_a_dangling_field_is_left_alone(self):
        self.conn.execute(
            "UPDATE activity_field_sources SET source_record_id = NULL "
            "WHERE activity_id = 'a1' AND field_name = 'distance_m'"
        )
        self.conn.execute(
            "DELETE FROM activity_sources WHERE activity_id = 'a1'"
        )
        self._tamper()

        result = self._run()

        self.assertGreaterEqual(result.counts["dangling"], 1)
        self.assertEqual(9999.0, self._field())

    def test_a_dry_run_writes_nothing(self):
        self._tamper()

        result = self._run(dry_run=True)

        self.assertEqual(1, result.counts["written"])
        self.assertEqual(9999.0, self._field())

    def test_the_distance_policy_is_reapplied(self):
        payload = dict(PAYLOAD, type="TreadmillRun", distance=5000.0)
        record_id = self._record("intervals", "i2", payload)
        self._activity("a2", payload, record_id=record_id)
        self.conn.execute(
            "UPDATE activities SET distance_m = 5000 WHERE id = 'a2'"
        )
        self.conn.commit()

        self._run()

        self.assertEqual(0.0, self._field(activity_id="a2"))


if __name__ == "__main__":
    unittest.main()
