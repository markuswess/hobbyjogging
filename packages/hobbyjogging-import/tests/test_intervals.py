import unittest
from datetime import date

from hobbyjogging_core import TrainingRepository, connect, migrate
from hobbyjogging_import.intervals import IntervalsImporter


class FakeIntervalsClient:

    def __init__(self):
        self.activity_payloads = [
            {
                "id": "i1",
                "start_date": "2026-10-01T06:00:00Z",
                "start_date_local": "2026-10-01T08:00:00",
                "type": "run",
                "name": "Morning run",
                "description": "Easy",
                "moving_time": 3600,
                "elapsed_time": 3900,
                "distance": 10000,
                "average_heartrate": 140,
                "icu_training_load": 50,
                "icu_rpe": 4,
                "feel": 2,
                "icu_intensity": 80,
                "pace_zone_times": [600, 300],
                "icu_hr_zone_times": [1800, 1800],
            }
        ]
        self.wellness_payloads = [
            {
                "id": "2026-10-01",
                "hrv": 60,
                "restingHR": 50,
                "sleepSecs": 28800,
            }
        ]
        self.event_payloads = [
            {
                "id": 42,
                "start_date_local": "2026-10-02T09:00:00",
                "name": "Town race",
                "type": "race",
                "duration": 1800,
                "distance": 5000,
            }
        ]
        self.interval_payloads = {
            "i1": [
                {
                    "group_id": "g1",
                    "type": "WORK",
                    "start_time": "00:05:00",
                    "moving_time": 60,
                    "distance": 200,
                    "average_heartrate": 150,
                    "max_heartrate": 160,
                }
            ]
        }
        self.fail = False

    def activities(self, start, end):
        if self.fail:
            raise RuntimeError("API unavailable")
        return self.activity_payloads

    def wellness(self, start, end):
        return self.wellness_payloads

    def events(self, start, end):
        return self.event_payloads

    def activity_intervals(self, activity_id):
        return self.interval_payloads.get(activity_id, [])


class IntervalsImporterTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.client = FakeIntervalsClient()
        self.importer = IntervalsImporter(self.conn, client=self.client)
        self.repository = TrainingRepository(self.conn)

    def _import(self, include_intervals=True):
        return self.importer.import_range(
            date(2026, 10, 1),
            date(2026, 10, 2),
            include_intervals=include_intervals,
        )

    def test_imports_activities_wellness_events_and_intervals(self):
        summary = self._import()

        self.assertEqual(1, summary.activities_imported)
        self.assertEqual(1, summary.wellness_imported)
        self.assertEqual(1, summary.events_imported)
        self.assertEqual(1, summary.intervals_imported)

        activities = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )
        self.assertEqual(1, len(activities))
        activity = activities[0]
        self.assertEqual("run", activity.type)
        self.assertEqual("Morning run", activity.name)
        self.assertEqual(3600, activity.duration_s)
        self.assertEqual(3900, activity.elapsed_s)
        self.assertEqual(10000, activity.distance_m)
        self.assertEqual(140, activity.avg_hr)
        self.assertEqual(50, activity.training_load)
        self.assertEqual(4, activity.rpe)
        self.assertEqual(2, activity.feel)
        self.assertEqual(0.8, activity.intensity)
        self.assertEqual([600, 300], activity.pace_zone_times)
        self.assertEqual([1800, 1800], activity.hr_zone_times)

        timing = self.conn.execute(
            "SELECT started_at_utc, tz_offset_min FROM activities"
        ).fetchone()
        self.assertEqual("2026-10-01T06:00:00Z", timing["started_at_utc"])
        self.assertEqual(120, timing["tz_offset_min"])

        wellness = self.repository.wellness(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )
        self.assertEqual(60, wellness[0].hrv)
        self.assertEqual(50, wellness[0].resting_hr)

        events = self.repository.events(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )
        self.assertEqual("Town race", events[0].name)

        intervals = self.repository.activity_intervals(activity.id)
        self.assertEqual(1, len(intervals))
        self.assertEqual("WORK", intervals[0].type)
        self.assertEqual(150, intervals[0].avg_hr)

    def test_import_records_raw_data_and_import_run(self):
        summary = self._import()

        sources = self.conn.execute(
            "SELECT source, record_type, external_id FROM source_records "
            "ORDER BY record_type"
        ).fetchall()
        self.assertEqual(
            [
                ("intervals", "activity", "i1"),
                ("intervals", "event", "42"),
                ("intervals", "intervals", "i1"),
                ("intervals", "wellness", "2026-10-01"),
            ],
            [
                (row["source"], row["record_type"], row["external_id"])
                for row in sources
            ],
        )

        run = self.conn.execute(
            "SELECT status, records_seen, records_imported "
            "FROM import_runs WHERE id = ?",
            (summary.run_id,),
        ).fetchone()
        self.assertEqual("success", run["status"])
        self.assertEqual(3, run["records_seen"])
        self.assertEqual(3, run["records_imported"])

        link = self.conn.execute(
            "SELECT is_primary FROM activity_sources"
        ).fetchone()
        self.assertEqual(1, link["is_primary"])

    def test_reimport_is_idempotent_and_preserves_manual_fields(self):
        first = self._import()
        activity = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )[0]

        self.conn.execute(
            "UPDATE activities SET name = 'Manual name' WHERE id = ?",
            (activity.id,),
        )
        self.conn.execute(
            "UPDATE activity_field_sources SET source = 'manual', is_manual = 1 "
            "WHERE activity_id = ? AND field_name = 'name'",
            (activity.id,),
        )

        self.client.activity_payloads[0]["name"] = "Changed name"
        second = self._import()

        activities = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )
        self.assertEqual(1, len(activities))
        self.assertEqual(activity.id, activities[0].id)
        self.assertEqual("Manual name", activities[0].name)

        self.assertEqual(
            4,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )
        self.assertEqual(
            2,
            self.conn.execute(
                "SELECT COUNT(*) FROM import_runs"
            ).fetchone()[0],
        )
        self.assertNotEqual(first.run_id, second.run_id)

    def test_can_skip_interval_downloads(self):
        summary = self._import(include_intervals=False)

        self.assertEqual(0, summary.intervals_imported)
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM activity_intervals"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records "
                "WHERE record_type = 'intervals'"
            ).fetchone()[0],
        )

    def test_failed_import_is_recorded(self):
        self.client.fail = True

        with self.assertRaises(RuntimeError):
            self._import()

        run = self.conn.execute(
            "SELECT status, error FROM import_runs"
        ).fetchone()
        self.assertEqual("failed", run["status"])
        self.assertIn("API unavailable", run["error"])


if __name__ == "__main__":
    unittest.main()
