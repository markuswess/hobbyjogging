import json
import unittest
from datetime import date

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.intervals import _activity_values

from hobbyjogging_maintenance.context import Scope
from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "device_identity_v1"
VERIFY = "verify_canonical"
RECOMPUTE = "recompute_canonical"

ENDURO = "fit:garmin:enduro:3386253273"


class DeviceIdentityTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0
        self._fit_device(ENDURO, serial="3386253273")
        self._provider_device("intervals:garmin-enduro", "Garmin Enduro")
        self._provider_device("intervals:runalyze", "Runalyze")

    def _fit_device(self, device_id, *, product="enduro", serial="1"):
        self.writer.upsert_device(
            device_id,
            manufacturer="garmin",
            product=product,
            serial_number=serial,
        )
        self.conn.commit()

    def _provider_device(self, device_id, name):
        self.writer.upsert_device(device_id, name=name)
        self.conn.commit()

    def _activity(
        self,
        device_name,
        device_id,
        *,
        activity_id=None,
        local_date="2024-08-04",
        name="Ramsau am Dachstein Surfing",
    ):
        self.counter += 1
        activity_id = activity_id or f"a{self.counter}"
        payload = {
            "start_date": f"{local_date}T06:00:00Z",
            "start_date_local": f"{local_date}T08:00:00",
            "type": "Run",
            "name": name,
            "icu_recording_time": 3600,
            "elapsed_time": 3700,
            "distance": 10000.0,
            "device_name": device_name,
        }
        record_id = self.writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id=activity_id,
            checksum=f"c-{activity_id}",
            payload_json=json.dumps(payload),
            import_run_id=self.run_id,
        )
        values = _activity_values(payload)
        values["device_id"] = device_id
        self.writer.upsert_activity(
            activity_id,
            values,
            source="intervals",
            source_record_id=record_id,
        )
        self.writer.link_activity_source(activity_id, record_id)
        self.conn.commit()
        return activity_id

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _device(self, activity_id):
        row = self.conn.execute(
            "SELECT device_id FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        return row["device_id"]

    def _snapshot(self, activity_id):
        row = self.conn.execute(
            """
            SELECT value_json FROM activity_field_sources
            WHERE activity_id = ? AND field_name = 'device_id'
            """,
            (activity_id,),
        ).fetchone()
        return row["value_json"]

    def test_claims_the_unique_fit_device(self):
        activity_id = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")

        run = self._run()

        self.assertEqual(1, run.counts["reassigned"])
        self.assertEqual(ENDURO, self._device(activity_id))
        self.assertEqual(json.dumps(ENDURO), self._snapshot(activity_id))
        self.assertTrue(any("->" in note for note in run.notes))

    def test_app_name_clears_the_fallback(self):
        activity_id = self._activity(
            "Runalyze",
            "intervals:runalyze",
            local_date="2025-07-08",
            name="Höchst Other",
        )

        run = self._run()

        self.assertEqual(1, run.counts["cleared"])
        self.assertIsNone(self._device(activity_id))
        self.assertEqual("null", self._snapshot(activity_id))

    def test_an_already_null_app_name_is_not_selected(self):
        activity_id = self._activity(
            "Garmin Connect",
            None,
            local_date="2019-01-30",
            name="wdf",
        )

        run = self._run()

        self.assertEqual({}, run.counts)
        self.assertIsNone(self._device(activity_id))
        self.assertIn("No activities", run.notes[0])

    def test_two_devices_of_the_same_model_stay_provider(self):
        self._fit_device(
            "fit:garmin:enduro:111",
            serial="111",
        )
        activity_id = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")

        run = self._run()

        self.assertEqual(1, run.counts["unchanged"])
        self.assertEqual("intervals:garmin-enduro", self._device(activity_id))

    def test_manual_assignment_is_not_touched(self):
        activity_id = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")
        self.writer.set_manual_field(
            activity_id,
            "device_id",
            "intervals:garmin-enduro",
        )
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["manual"])
        self.assertEqual("intervals:garmin-enduro", self._device(activity_id))

    def test_fit_backed_activity_is_not_claimed(self):
        activity_id = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")
        fit_record = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="fit-1",
            checksum="fit-1",
            import_run_id=self.run_id,
        )
        self.writer.link_activity_source(activity_id, fit_record)
        self.conn.commit()

        run = self._run()

        self.assertEqual({}, run.counts)
        self.assertEqual("intervals:garmin-enduro", self._device(activity_id))

    def test_dry_run_writes_nothing(self):
        activity_id = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")

        run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["reassigned"])
        self.assertEqual("intervals:garmin-enduro", self._device(activity_id))

    def test_rerun_is_a_no_op(self):
        activity_id = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")
        self._run()

        again = self._run(force=True)

        self.assertEqual({}, again.counts)
        self.assertEqual(ENDURO, self._device(activity_id))

    def test_scope_limits_to_one_activity(self):
        first = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")
        second = self._activity(
            "GARMIN ENDURO",
            "intervals:garmin-enduro",
            local_date="2025-09-04",
            name="Vienna Cycling",
        )

        self._run(scope=Scope(entity_id=second))

        self.assertEqual("intervals:garmin-enduro", self._device(first))
        self.assertEqual(ENDURO, self._device(second))

    def test_scope_limits_by_date(self):
        first = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")
        second = self._activity(
            "GARMIN ENDURO",
            "intervals:garmin-enduro",
            local_date="2025-09-04",
            name="Vienna Cycling",
        )

        self._run(scope=Scope(start=date(2025, 9, 4)))

        self.assertEqual("intervals:garmin-enduro", self._device(first))
        self.assertEqual(ENDURO, self._device(second))

    def test_scope_limits_by_count(self):
        first = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")
        second = self._activity(
            "GARMIN ENDURO",
            "intervals:garmin-enduro",
            local_date="2025-09-04",
            name="Vienna Cycling",
        )

        self._run(scope=Scope(limit=1))

        self.assertEqual(ENDURO, self._device(first))
        self.assertEqual("intervals:garmin-enduro", self._device(second))

    def test_excluded_activity_is_untouched(self):
        activity_id = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")
        self.writer.exclude_activity(activity_id)
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["skipped"])
        self.assertEqual("intervals:garmin-enduro", self._device(activity_id))

    def test_unknown_entity_fails(self):
        run = self._run(scope=Scope(entity_id="missing"))

        self.assertEqual("failed", run.status)
        self.assertIn("unknown or excluded activity", run.error)

    def test_verify_canonical_accepts_the_claim(self):
        activity_id = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")
        self._run()

        verified = run_task(self.conn, get_task(VERIFY))

        self.assertEqual("ok", verified.status)
        self.assertFalse(
            any(
                "device_id" in line
                for line in verified.notes
            )
        )
        self.assertEqual(ENDURO, self._device(activity_id))

    def test_recompute_canonical_keeps_the_claim(self):
        activity_id = self._activity("GARMIN ENDURO", "intervals:garmin-enduro")
        self._run()

        run_task(self.conn, get_task(RECOMPUTE))

        self.assertEqual(ENDURO, self._device(activity_id))


if __name__ == "__main__":
    unittest.main()
