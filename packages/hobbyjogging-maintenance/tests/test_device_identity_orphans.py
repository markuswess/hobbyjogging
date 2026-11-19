import unittest

from hobbyjogging_core import TrainingRepository, TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "device_identity_orphans_v1"


class DeviceIdentityOrphanTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.writer.upsert_device(
            "intervals:garmin-enduro",
            name="Garmin Enduro",
        )
        self.writer.upsert_device(
            "intervals:runalyze",
            name="Runalyze",
        )
        self.writer.upsert_device(
            "fit:garmin:enduro:1",
            manufacturer="garmin",
            product="enduro",
            serial_number="1",
        )
        self.conn.commit()

    def _excluded(self):
        return {
            row["id"]
            for row in self.conn.execute(
                "SELECT id FROM devices WHERE excluded_at IS NOT NULL"
            )
        }

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def test_excludes_unused_provider_rows(self):
        result = self._run()

        self.assertEqual(2, result.counts["excluded"])
        self.assertEqual(
            {"intervals:garmin-enduro", "intervals:runalyze"},
            self._excluded(),
        )
        self.assertEqual(
            ["fit:garmin:enduro:1"],
            [device.id for device in TrainingRepository(self.conn).devices()],
        )

    def test_keeps_a_provider_row_with_an_activity(self):
        record_id = self.writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id="i1",
            checksum="c-i1",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "device_id": "intervals:garmin-enduro",
            },
            source="intervals",
            source_record_id=record_id,
        )
        self.conn.commit()

        result = self._run()

        self.assertEqual(1, result.counts["kept"])
        self.assertNotIn("intervals:garmin-enduro", self._excluded())

    def test_a_dry_run_writes_nothing(self):
        result = self._run(dry_run=True)

        self.assertEqual(2, result.counts["excluded"])
        self.assertEqual(set(), self._excluded())

    def test_a_rerun_is_idempotent(self):
        self._run()

        result = self._run(force=True)

        self.assertEqual(2, result.counts["unchanged"])
        self.assertEqual(0, result.counts["excluded"])


if __name__ == "__main__":
    unittest.main()
