import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "activity_device_v1"


class ActivityDeviceTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test", {})

    def _activity(self, activity_id="a1", *, excluded=False):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) VALUES (?, ?, 'run')",
            (activity_id, "2024-06-01"),
        )
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _source(self, activity_id, source, payload, external="x1"):
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=f"{source}-{external}",
            checksum=f"c-{source}-{external}",
            import_run_id=self.run_id,
            payload_json=json.dumps(payload),
        )
        self.conn.execute(
            "INSERT INTO activity_sources "
            "(activity_id, source_record_id, match_method) VALUES (?, ?, 'test')",
            (activity_id, record_id),
        )
        self.conn.commit()

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _device(self, activity_id="a1"):
        row = self.conn.execute(
            "SELECT device_id FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        return row["device_id"]

    def test_fit_supplies_the_device(self):
        self._activity()
        self._source("a1", "fit", {
            "file": {
                "manufacturer": "garmin",
                "product": "enduro",
                "serial_number": "338625",
            }
        })

        result = self._run()

        self.assertEqual(1, result.counts["written"])
        self.assertEqual("fit:garmin:enduro:338625", self._device())
        self.assertEqual(
            1,
            self.conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0],
        )

    def test_a_connect_upload_is_not_a_device(self):
        self._activity()
        self._source("a1", "fit", {
            "file": {"manufacturer": "garmin", "product": "connect"}
        })

        result = self._run()

        self.assertEqual(1, result.counts["skipped"])
        self.assertIsNone(self._device())

    def test_intervals_fills_a_missing_device(self):
        self._activity()
        self._source("a1", "intervals", {"device_name": "GARMIN ENDURO"})

        self._run()

        self.assertEqual("intervals:garmin-enduro", self._device())

    def test_fit_wins_over_intervals(self):
        self._activity()
        self._source("a1", "intervals", {"device_name": "Garmin Enduro"})
        self._source("a1", "fit", {
            "file": {
                "manufacturer": "garmin",
                "product": "enduro",
                "serial_number": "338625",
            }
        }, external="x2")

        self._run()

        self.assertEqual("fit:garmin:enduro:338625", self._device())

    def test_a_manual_assignment_survives(self):
        self._activity()
        self.writer.upsert_device("manual:old-watch", name="Old watch")
        self.writer.set_manual_field("a1", "device_id", "manual:old-watch")
        self._source("a1", "fit", {
            "file": {
                "manufacturer": "garmin",
                "product": "enduro",
                "serial_number": "338625",
            }
        })

        self._run()

        self.assertEqual("manual:old-watch", self._device())

    def test_a_forced_rerun_is_a_no_op(self):
        self._activity()
        self._source("a1", "fit", {
            "file": {
                "manufacturer": "garmin",
                "product": "enduro",
                "serial_number": "338625",
            }
        })

        self._run()
        result = self._run(force=True)

        self.assertEqual(0, result.counts.get("written", 0))
        self.assertEqual(1, result.counts["unchanged"])


if __name__ == "__main__":
    unittest.main()
