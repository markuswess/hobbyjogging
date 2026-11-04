import json
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

    def test_excluded_intervals_activity_is_skipped_on_reimport(self):
        self._import()
        activity_id = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )[0].id

        self.importer.writer.exclude_activity(activity_id)
        self.conn.commit()

        summary = self._import()

        self.assertEqual(1, summary.activities_seen)
        self.assertEqual(0, summary.activities_imported)
        self.assertEqual(1, summary.activities_skipped)

        row = self.conn.execute(
            "SELECT duration_s, excluded_at FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()
        self.assertEqual(3600, row["duration_s"])
        self.assertIsNotNone(row["excluded_at"])

        count = self.conn.execute(
            "SELECT COUNT(*) FROM source_records "
            "WHERE source = 'intervals' AND record_type = 'intervals'"
        ).fetchone()[0]
        self.assertEqual(1, count)

    def test_first_intervals_import_is_created_link(self):
        summary = self._import()

        link = self.conn.execute(
            "SELECT match_method, is_primary, confidence "
            "FROM activity_sources"
        ).fetchone()
        self.assertEqual("created", link["match_method"])
        self.assertEqual(1, link["is_primary"])
        self.assertEqual(1, summary.activities_imported)

    def test_intervals_match_existing_fit_activity(self):
        writer = self.importer.writer
        fit_run_id = writer.start_import_run("fit")
        fit_source = writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="fit-file",
            checksum="fit-checksum",
            import_run_id=fit_run_id,
        )
        writer.upsert_activity(
            "fit-uuid",
            {
                "local_date": "2026-10-01",
                "started_at_utc": "2026-10-01T06:00:00Z",
                "sport": "run",
                "name": "Run",
                "duration_s": 3600,
                "elapsed_s": 3700,
                "distance_m": 10100,
                "avg_hr": 141,
            },
            source="fit",
            source_record_id=fit_source,
        )
        writer.link_activity_source(
            "fit-uuid",
            fit_source,
            match_method="created",
        )

        self.client.activity_payloads[0]["start_date"] = (
            "2026-10-01T06:00:00Z"
        )
        self.client.activity_payloads[0]["elapsed_time"] = 3900
        summary = self._import()

        self.assertEqual(1, summary.activities_imported)
        self.assertEqual([], summary.ambiguous_matches)

        activities = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )
        self.assertEqual(["fit-uuid"], [activity.id for activity in activities])
        # The FIT owner keeps its values; only the elapsed-time disagreement
        # becomes a review item.
        self.assertEqual("Run", activities[0].name)
        self.assertEqual(3600, activities[0].duration_s)
        self.assertEqual(3700, activities[0].elapsed_s)
        self.assertEqual(10100, activities[0].distance_m)
        self.assertEqual(141, activities[0].avg_hr)

        conflicts = writer.review_items(
            category="field_conflict",
            status="open",
        )
        self.assertEqual(1, len(conflicts))
        context = json.loads(conflicts[0]["context_json"])
        self.assertEqual("elapsed_s", context["field"])
        self.assertEqual("fit", context["current"]["source"])
        self.assertEqual("intervals", context["incoming"]["source"])
        self.assertEqual(3700, context["current"]["value"])
        self.assertEqual(3900, context["incoming"]["value"])

        links = self.conn.execute(
            """
            SELECT sr.source, s.match_method, s.is_primary
            FROM activity_sources s
            JOIN source_records sr ON sr.id = s.source_record_id
            ORDER BY sr.source
            """
        ).fetchall()
        self.assertEqual(2, len(links))
        self.assertEqual("fit", links[0]["source"])
        self.assertEqual(1, links[0]["is_primary"])
        self.assertEqual("intervals", links[1]["source"])
        self.assertEqual(0, links[1]["is_primary"])
        self.assertEqual("temporal_overlap", links[1]["match_method"])

    def test_ambiguous_intervals_match_is_reported(self):
        for activity_id in ("overlap-1", "overlap-2"):
            self.conn.execute(
                """
                INSERT INTO activities (
                    id, local_date, started_at_utc, sport, elapsed_s, duration_s
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    "2026-10-01",
                    "2026-10-01T06:05:00Z",
                    "run",
                    3600,
                    3500,
                ),
            )
        self.client.activity_payloads[0]["start_date"] = (
            "2026-10-01T06:00:00Z"
        )
        self.client.activity_payloads[0]["duration"] = 3600
        self.client.activity_payloads[0]["elapsed_time"] = 3700

        summary = self._import()

        self.assertEqual(0, summary.activities_imported)
        self.assertEqual(1, summary.activities_skipped)
        self.assertEqual(1, len(summary.ambiguous_matches))
        external_id, matches = summary.ambiguous_matches[0]
        self.assertEqual("i1", external_id)
        self.assertEqual(2, len(matches))

        self.assertEqual(1, summary.review_recorded)
        items = self.importer.writer.review_items(status="all")
        self.assertEqual(1, len(items))
        self.assertEqual("ambiguous_match", items[0]["category"])
        self.assertIsNone(items[0]["activity_id"])

        summary = self._import()

        self.assertEqual(0, summary.review_recorded)
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM review_items"
            ).fetchone()[0],
        )

    def test_quality_issue_from_intervals_is_recorded(self):
        self.client.activity_payloads[0]["distance"] = 0

        summary = self._import()

        self.assertEqual(1, summary.review_recorded)
        items = self.importer.writer.review_items(status="all")
        self.assertEqual(1, len(items))
        self.assertEqual("quality", items[0]["category"])
        context = json.loads(items[0]["context_json"])
        self.assertEqual("zero_distance", context["rule"])

        activities = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )
        self.assertEqual(1, len(activities))
        self.assertTrue(activities[0].needs_review)

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
