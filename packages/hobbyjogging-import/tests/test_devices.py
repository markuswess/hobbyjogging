"""Provider device identity: app names, display casing and the FIT claim."""

import unittest
from datetime import date

from hobbyjogging_core import (
    TrainingRepository,
    TrainingWriter,
    connect,
    migrate,
)

from hobbyjogging_import.devices import (
    display_device_name,
    is_app_device_name,
    provider_device_id,
)
from hobbyjogging_import.fit_import import device_id_from
from hobbyjogging_import.intervals import IntervalsImporter
from test_intervals import FakeIntervalsClient


class AppNameTests(unittest.TestCase):

    def test_provider_apps_are_never_devices(self):
        for name in (
            "Runalyze",
            " runalyze ",
            "Garmin Connect",
            "GARMIN  CONNECT",
            "GarminConnect",
            "Strava",
            "Intervals.icu",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_app_device_name(name))
                self.assertIsNone(provider_device_id(name))

    def test_a_watch_name_is_not_an_app(self):
        self.assertFalse(is_app_device_name("Garmin Enduro"))
        self.assertEqual(
            "intervals:garmin-enduro",
            provider_device_id("Garmin Enduro"),
        )

    def test_the_display_name_is_collapsed_and_title_cased(self):
        self.assertEqual(
            "Garmin Enduro",
            display_device_name("  GARMIN   ENDURO "),
        )


class FitSerialTests(unittest.TestCase):

    def test_a_serial_less_upload_is_not_a_device(self):
        self.assertIsNone(device_id_from("garmin", "enduro", ""))
        self.assertIsNone(device_id_from("garmin", "connect", "123"))

    def test_the_serial_is_the_identity(self):
        self.assertEqual(
            "fit:garmin:enduro:3386253273",
            device_id_from("garmin", "enduro", "3386253273"),
        )


class ImporterDeviceTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.client = FakeIntervalsClient()
        self.importer = IntervalsImporter(self.conn, client=self.client)
        self.repository = TrainingRepository(self.conn)
        self.writer = TrainingWriter(self.conn)

    def _seed_fit_device(self, serial, product="enduro"):
        device_id = f"fit:garmin:{product}:{serial}"
        self.writer.upsert_device(
            device_id,
            manufacturer="garmin",
            product=product,
            serial_number=serial,
        )
        return device_id

    def _import_one(self, device_name, *, activity_id="i1", day="01"):
        payload = dict(self.client.activity_payloads[0])
        payload["id"] = activity_id
        payload["start_date"] = f"2026-10-{day}T06:00:00Z"
        payload["start_date_local"] = f"2026-10-{day}T08:00:00"
        payload["device_name"] = device_name
        self.client.activity_payloads = [payload]
        self.client.interval_payloads = {}
        summary = self.importer.import_range(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )
        self.assertEqual(1, summary.activities_imported)
        return self.conn.execute(
            "SELECT id, device_id FROM activities"
        ).fetchone()

    def _devices(self):
        return self.conn.execute(
            "SELECT id, name FROM devices ORDER BY id"
        ).fetchall()

    def test_an_app_name_writes_no_device_and_no_device_id(self):
        activity = self._import_one("Runalyze")

        self.assertEqual([], self._devices())
        self.assertIsNone(activity["device_id"])

    def test_a_real_provider_name_writes_the_fallback_device(self):
        activity = self._import_one("  wahoo   ELEMNT ")

        self.assertEqual(
            [("intervals:wahoo-elemnt", "Wahoo Elemnt")],
            [tuple(row) for row in self._devices()],
        )
        self.assertEqual("intervals:wahoo-elemnt", activity["device_id"])

    def test_the_stored_name_survives_a_different_spelling(self):
        self._import_one("GARMIN ENDURO", activity_id="i1", day="01")
        self._import_one("Garmin  Enduro", activity_id="i2", day="02")

        self.assertEqual(
            [("intervals:garmin-enduro", "Garmin Enduro")],
            [tuple(row) for row in self._devices()],
        )

    def test_a_fit_backed_activity_gets_no_provider_device(self):
        run_id = self.writer.start_import_run("fit")
        source_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="fit-file",
            checksum="fit-checksum",
            import_run_id=run_id,
        )
        self.writer.upsert_activity(
            "fit-uuid",
            {
                "local_date": "2026-10-01",
                "started_at_utc": "2026-10-01T06:00:00Z",
                "sport": "run",
                "name": "Run",
                "duration_s": 3600,
                "elapsed_s": 3900,
                "distance_m": 10000,
                "avg_hr": 140,
            },
            source="fit",
            source_record_id=source_id,
        )
        self.writer.link_activity_source(
            "fit-uuid",
            source_id,
            match_method="created",
        )

        activity = self._import_one("Wahoo ELEMNT")

        self.assertEqual([], self._devices())
        self.assertIsNone(activity["device_id"])

    def test_a_unique_fit_device_of_the_model_is_claimed(self):
        claimed = self._seed_fit_device("3386253273")

        activity = self._import_one("GARMIN ENDURO")

        self.assertEqual(claimed, activity["device_id"])
        self.assertEqual(
            [(claimed, "")],
            [tuple(row) for row in self._devices()],
        )

    def test_both_spellings_of_a_model_claim_the_same_device(self):
        claimed = self._seed_fit_device("3604095470", product="edge_540")

        first = self._import_one("GARMIN EDGE_540", activity_id="i1", day="01")
        second = self._import_one(
            "Garmin Edge 540",
            activity_id="i2",
            day="02",
        )

        self.assertEqual(claimed, first["device_id"])
        self.assertEqual(claimed, second["device_id"])
        self.assertEqual(
            [(claimed, "")],
            [tuple(row) for row in self._devices()],
        )

    def test_two_devices_of_the_model_keep_the_provider_id(self):
        self._seed_fit_device("1")
        self._seed_fit_device("2")

        activity = self._import_one("GARMIN ENDURO")

        self.assertEqual("intervals:garmin-enduro", activity["device_id"])
        names = sorted(row["id"] for row in self._devices())
        self.assertIn("fit:garmin:enduro:1", names)
        self.assertIn("intervals:garmin-enduro", names)


if __name__ == "__main__":
    unittest.main()
