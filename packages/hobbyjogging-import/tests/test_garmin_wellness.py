import unittest
from datetime import date

from hobbyjogging_core import connect, migrate

from hobbyjogging_import.garmin_wellness import (
    GarminWellnessImporter,
    format_wellness_summary,
)


class FakeGarminWellnessClient:

    hrv_fails = False
    no_activities = False

    def __init__(self):
        self.calls = []

    def list_activities(self, start, end):
        if type(self).no_activities:
            return []
        return [{"ownerDisplayName": "user-1"}]

    def get_json(self, path, params=None):
        self.calls.append((path, params))
        if path.startswith("/usersummary-service"):
            day = params["calendarDate"]
            return {
                "calendarDate": day,
                "restingHeartRate": 48,
                "sleepingSeconds": 28620,
                "totalSteps": 20049,
                "floorsAscended": 39.04,
                "averageSpo2": 96.0,
            }
        if path.startswith("/hrv-service"):
            if type(self).hrv_fails:
                raise RuntimeError("HRV is not exposed")
            return {"hrvSummary": {"lastNightAvg": 59, "weeklyAvg": 48}}
        if path.startswith("/weight-service"):
            return {
                "dailyWeightSummaries": [
                    {
                        "summaryDate": "2026-11-20",
                        "latestWeight": {
                            "calendarDate": "2026-11-20",
                            "weight": 65099.0,
                        },
                    }
                ]
            }
        raise AssertionError(path)


class GarminWellnessTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.client = FakeGarminWellnessClient()
        self.importer = GarminWellnessImporter(
            self.conn,
            client=self.client,
        )
        FakeGarminWellnessClient.hrv_fails = False
        FakeGarminWellnessClient.no_activities = False

    def _rows(self):
        return {
            row["local_date"]: dict(row)
            for row in self.conn.execute(
                "SELECT * FROM wellness_days ORDER BY local_date"
            )
        }

    def test_fills_the_days_from_the_daily_summary_and_hrv(self):
        summary = self.importer.import_range(
            date(2026, 11, 20),
            date(2026, 11, 21),
        )

        self.assertEqual(2, summary.days)
        self.assertEqual(2, summary.written)
        rows = self._rows()
        self.assertEqual(
            {
                "hrv": 59.0,
                "resting_hr": 48.0,
                "sleep_s": 28620.0,
                "steps": 20049,
                "floors_climbed": 39,
                "spo2": 96.0,
                "weight_kg": 65.099,
            },
            {
                key: rows["2026-11-20"][key]
                for key in (
                    "hrv",
                    "resting_hr",
                    "sleep_s",
                    "steps",
                    "floors_climbed",
                    "spo2",
                    "weight_kg",
                )
            },
        )

        records = self.conn.execute(
            "SELECT COUNT(*) FROM source_records "
            "WHERE source = 'garmin' AND record_type = 'wellness'"
        ).fetchone()[0]
        self.assertEqual(2, records)

    def test_existing_values_are_never_overwritten(self):
        self.conn.execute(
            """
            INSERT INTO wellness_days
                (local_date, resting_hr, hrv, sleep_s, steps)
            VALUES ('2026-11-20', 60, 50, 25000, 10000)
            """
        )
        self.conn.commit()

        self.importer.import_range(
            date(2026, 11, 20),
            date(2026, 11, 20),
        )

        row = self._rows()["2026-11-20"]
        self.assertEqual(60, row["resting_hr"])
        self.assertEqual(50, row["hrv"])
        self.assertEqual(25000, row["sleep_s"])
        self.assertEqual(10000, row["steps"])
        # A missing field is still filled.
        self.assertEqual(96.0, row["spo2"])

    def test_a_complete_day_is_unchanged_on_a_rerun(self):
        self.importer.import_range(
            date(2026, 11, 20),
            date(2026, 11, 20),
        )

        summary = self.importer.import_range(
            date(2026, 11, 20),
            date(2026, 11, 20),
        )

        self.assertEqual(1, summary.unchanged)
        self.assertEqual(0, summary.written)

    def test_a_missing_hrv_endpoint_still_writes_the_summary(self):
        FakeGarminWellnessClient.hrv_fails = True

        summary = self.importer.import_range(
            date(2026, 11, 20),
            date(2026, 11, 20),
        )

        self.assertEqual(1, summary.written)
        self.assertEqual(0, summary.hrv_days)
        self.assertTrue(any("hrv" in error for error in summary.errors))
        self.assertEqual(
            48.0,
            self._rows()["2026-11-20"]["resting_hr"],
        )

    def test_no_activity_means_no_user_id(self):
        FakeGarminWellnessClient.no_activities = True

        summary = self.importer.import_range(
            date(2026, 11, 20),
            date(2026, 11, 20),
        )

        self.assertTrue(summary.no_user)
        self.assertEqual({}, self._rows())
        self.assertIn("no activity found", format_wellness_summary(summary))

    def test_location_filters_the_weight_range(self):
        self.importer.import_range(
            date(2026, 11, 20),
            date(2026, 11, 21),
        )

        weights = [
            call
            for call in self.client.calls
            if call[0].startswith("/weight-service")
        ]
        self.assertEqual(1, len(weights))
        self.assertIn("2026-11-20", weights[0][0])
        self.assertIn("2026-11-21", weights[0][0])


if __name__ == "__main__":
    unittest.main()
