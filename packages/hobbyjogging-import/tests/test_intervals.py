import json
import unittest
from datetime import date, timedelta

from hobbyjogging_core import TrainingRepository, connect, migrate
from hobbyjogging_import.cli import build_parser, resolve_event_range
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
                "moving_time": 1800,
                "distance": 5000,
                "icu_training_load": 40,
            }
        ]
        self.activity_ranges = []
        self.wellness_ranges = []
        self.event_ranges = []
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
        self.activity_ranges.append((start, end))
        if self.fail:
            raise RuntimeError("API unavailable")
        return self.activity_payloads

    def wellness(self, start, end):
        self.wellness_ranges.append((start, end))
        return self.wellness_payloads

    def events(self, start, end):
        self.event_ranges.append((start, end))
        return self.event_payloads

    def activity(self, activity_id):
        for raw in self.activity_payloads:
            if str(raw.get("id")) == str(activity_id):
                return raw
        raise KeyError(activity_id)

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

    def _import(self, include_intervals=True, plan_end=None):
        return self.importer.import_range(
            date(2026, 10, 1),
            date(2026, 10, 2),
            include_intervals=include_intervals,
            plan_end=plan_end,
        )

    def _seed_fit_activity(self, *, duration_s=3600, avg_hr=140):
        writer = self.importer.writer
        run_id = writer.start_import_run("fit")
        source_id = writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="fit-file",
            checksum="fit-checksum",
            import_run_id=run_id,
        )
        writer.upsert_activity(
            "fit-uuid",
            {
                "local_date": "2026-10-01",
                "started_at_utc": "2026-10-01T06:00:00Z",
                "sport": "run",
                "name": "Run",
                "duration_s": duration_s,
                "elapsed_s": 3900,
                "distance_m": 10000,
                "avg_hr": avg_hr,
            },
            source="fit",
            source_record_id=source_id,
        )
        writer.link_activity_source(
            "fit-uuid",
            source_id,
            match_method="created",
        )
        return "fit-uuid", source_id

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
        self.assertEqual(3600, activity.moving_s)
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
        self.assertEqual(1800, events[0].duration_s)
        self.assertEqual(40, events[0].training_load)

        intervals = self.repository.activity_intervals(activity.id)
        self.assertEqual(1, len(intervals))
        self.assertEqual("WORK", intervals[0].type)
        self.assertEqual(150, intervals[0].avg_hr)

    def test_uses_recording_time_for_duration(self):
        self.client.activity_payloads[0]["icu_recording_time"] = 3650

        self._import()

        activity = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )[0]
        self.assertEqual(3650, activity.duration_s)
        self.assertEqual(3900, activity.elapsed_s)
        self.assertEqual(3600, activity.moving_s)

    def test_falls_back_to_moving_time_for_duration(self):
        self.client.activity_payloads[0]["icu_recording_time"] = None

        self._import()

        activity = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )[0]
        self.assertEqual(3600, activity.duration_s)

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

    def test_events_use_the_plan_horizon(self):
        plan_end = date(2026, 10, 2) + timedelta(days=182)

        summary = self._import(plan_end=plan_end)

        self.assertEqual(
            [(date(2026, 10, 1), date(2026, 10, 2))],
            self.client.activity_ranges,
        )
        self.assertEqual(
            [(date(2026, 10, 1), date(2026, 10, 2))],
            self.client.wellness_ranges,
        )
        self.assertEqual(
            [(date(2026, 10, 1), plan_end)],
            self.client.event_ranges,
        )
        self.assertEqual(plan_end, summary.plan_end)

        run = self.conn.execute(
            "SELECT parameters_json FROM import_runs WHERE id = ?",
            (summary.run_id,),
        ).fetchone()
        self.assertEqual(
            plan_end.isoformat(),
            json.loads(run["parameters_json"])["plan_end"],
        )

    def test_events_default_to_the_import_end(self):
        summary = self._import()

        self.assertEqual(
            [(date(2026, 10, 1), date(2026, 10, 2))],
            self.client.event_ranges,
        )
        self.assertEqual(date(2026, 10, 2), summary.plan_end)

    def test_plan_end_is_clamped_to_the_import_end(self):
        summary = self._import(plan_end=date(2026, 10, 1))

        self.assertEqual(date(2026, 10, 2), summary.plan_end)
        self.assertEqual(
            [(date(2026, 10, 1), date(2026, 10, 2))],
            self.client.event_ranges,
        )

    def test_future_planned_event_is_stored(self):
        self.client.event_payloads.append(
            {
                "id": 43,
                "start_date_local": "2027-03-01T09:00:00",
                "name": "Future workout",
                "type": "run",
            }
        )

        summary = self._import(plan_end=date(2027, 5, 6))

        self.assertEqual(2, summary.events_imported)
        events = self.repository.events(
            date(2027, 3, 1),
            date(2027, 3, 1),
        )
        self.assertEqual(["Future workout"], [event.name for event in events])

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

    def test_import_activity_force_takes_ownership(self):
        self._seed_fit_activity()
        self.client.activity_payloads[0]["moving_time"] = 3700
        self.client.activity_payloads[0]["average_heartrate"] = 145

        summary = self.importer.import_activity("i1", force=True)

        self.assertEqual(1, summary.activities_imported)
        activities = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )
        self.assertEqual(["fit-uuid"], [activity.id for activity in activities])
        self.assertEqual(3700, activities[0].duration_s)
        self.assertEqual(145, activities[0].avg_hr)

        rows = self.conn.execute(
            """
            SELECT field_name, source FROM activity_field_sources
            WHERE activity_id = 'fit-uuid'
              AND field_name IN ('duration_s', 'avg_hr')
            """
        ).fetchall()
        self.assertEqual(
            {"duration_s": "intervals", "avg_hr": "intervals"},
            {row["field_name"]: row["source"] for row in rows},
        )
        self.assertEqual(
            [],
            self.importer.writer.review_items(
                category="field_conflict",
                status="open",
            ),
        )

    def test_import_activity_force_keeps_manual_fields(self):
        self._seed_fit_activity()
        self.importer.writer.set_manual_field(
            "fit-uuid",
            "duration_s",
            3550,
        )
        self.client.activity_payloads[0]["moving_time"] = 3700

        summary = self.importer.import_activity("i1", force=True)

        self.assertEqual(1, summary.activities_imported)
        activity = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )[0]
        self.assertEqual(3550, activity.duration_s)

        row = self.conn.execute(
            """
            SELECT source, is_manual FROM activity_field_sources
            WHERE activity_id = 'fit-uuid' AND field_name = 'duration_s'
            """
        ).fetchone()
        self.assertEqual("manual", row["source"])
        self.assertEqual(1, row["is_manual"])

    def test_treadmill_distance_is_canonical_zero(self):
        self.client.activity_payloads[0]["type"] = "TreadmillRun"
        self.client.activity_payloads[0]["distance"] = 8000

        self._import()

        activity = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )[0]
        self.assertEqual("treadmill_run", activity.type)
        self.assertEqual(0, activity.distance_m)

    def test_soccer_distance_is_canonical_zero(self):
        self.client.activity_payloads[0]["type"] = "Soccer"
        self.client.activity_payloads[0]["distance"] = 529

        self._import()

        activity = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )[0]
        self.assertEqual("soccer", activity.type)
        self.assertEqual(0, activity.distance_m)

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


class EventSyncTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.client = FakeIntervalsClient()
        self.importer = IntervalsImporter(self.conn, client=self.client)
        self.repository = TrainingRepository(self.conn)
        self.start = date(2026, 10, 1)
        self.end = date(2026, 10, 2)

    def _sync(self, **kwargs):
        return self.importer.sync_events(self.start, self.end, **kwargs)

    def _events(self):
        return self.repository.events(self.start, self.end)

    def _event_count(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM events"
        ).fetchone()[0]

    def test_sync_adds_new_event(self):
        summary = self._sync()

        self.assertEqual(1, summary.fetched)
        self.assertEqual(1, summary.new)
        self.assertEqual(0, summary.removed)
        self.assertIsNotNone(summary.run_id)

        events = self._events()
        self.assertEqual(1, len(events))
        self.assertEqual("Town race", events[0].name)
        self.assertEqual(1800, events[0].duration_s)
        self.assertEqual(5000, events[0].distance_m)

    def test_sync_overwrites_changed_fields(self):
        self._sync()
        self.client.event_payloads[0].update(
            {
                "name": "New race",
                "moving_time": 2000,
                "icu_training_load": 55,
                "distance": 6000,
            }
        )

        summary = self._sync()

        self.assertEqual(1, summary.updated)
        event = self._events()[0]
        self.assertEqual("New race", event.name)
        self.assertEqual(2000, event.duration_s)
        self.assertEqual(55, event.training_load)
        self.assertEqual(6000, event.distance_m)

    def test_sync_clears_fields(self):
        self.client.event_payloads[0].update(
            {"distance": 5000, "icu_training_load": 55}
        )
        self._sync()

        self.client.event_payloads[0]["distance"] = None
        self.client.event_payloads[0]["icu_training_load"] = None
        summary = self._sync()

        self.assertEqual(1, summary.updated)
        event = self._events()[0]
        self.assertIsNone(event.distance_m)
        self.assertIsNone(event.training_load)

    def test_sync_removes_disappeared_event(self):
        self._sync()
        self.client.event_payloads.clear()

        summary = self._sync()

        self.assertEqual(1, summary.removed)
        self.assertEqual([], self._events())
        row = self.conn.execute(
            "SELECT excluded_at FROM events"
        ).fetchone()
        self.assertIsNotNone(row["excluded_at"])

    def test_sync_revives_returning_event(self):
        self._sync()
        payload = self.client.event_payloads.pop()
        self._sync()
        self.client.event_payloads.append(payload)

        summary = self._sync()

        self.assertEqual(1, summary.revived)
        self.assertEqual(1, len(self._events()))
        row = self.conn.execute(
            "SELECT excluded_at FROM events"
        ).fetchone()
        self.assertIsNone(row["excluded_at"])

    def test_sync_updates_moved_event_without_duplicating(self):
        self._sync()
        self.client.event_payloads[0]["start_date_local"] = (
            "2026-10-01T09:00:00"
        )

        summary = self._sync()

        self.assertEqual(1, summary.updated)
        events = self._events()
        self.assertEqual(1, len(events))
        self.assertEqual(date(2026, 10, 1), events[0].date)

    def test_sync_replaces_recreated_event(self):
        self._sync()
        self.client.event_payloads[0] = {
            **self.client.event_payloads[0],
            "id": 43,
            "name": "Recreated",
        }

        summary = self._sync()

        self.assertEqual(1, summary.new)
        self.assertEqual(1, summary.removed)
        self.assertEqual(["Recreated"], [event.name for event in self._events()])

    def test_sync_leaves_other_source_events_untouched(self):
        run_id = self.importer.writer.start_import_run("manual")
        source_id = self.importer.writer.upsert_source_record(
            source="manual",
            record_type="event",
            external_id="m1",
            checksum="c-manual",
            import_run_id=run_id,
        )
        self.importer.writer.upsert_event(
            event_id="m1",
            local_date="2026-10-02",
            name="Manual event",
            type="run",
            source_record_id=source_id,
        )
        self.conn.commit()
        self.client.event_payloads.clear()

        summary = self._sync()

        self.assertEqual(0, summary.removed)
        self.assertEqual(
            ["Manual event"],
            [event.name for event in self._events()],
        )

    def test_sync_dry_run_writes_nothing(self):
        summary = self._sync(dry_run=True)

        self.assertEqual(1, summary.new)
        self.assertEqual(0, self._event_count())
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM import_runs"
            ).fetchone()[0],
        )

    def test_sync_is_idempotent(self):
        self._sync()
        summary = self._sync()

        self.assertEqual(0, summary.new)
        self.assertEqual(0, summary.updated)
        self.assertEqual(1, summary.unchanged)
        self.assertEqual(0, summary.removed)
        self.assertEqual(1, self._event_count())

    def test_regular_import_prunes_events(self):
        self.importer.import_range(self.start, self.end, include_intervals=False)
        self.client.event_payloads.clear()

        summary = self.importer.import_range(
            self.start,
            self.end,
            include_intervals=False,
        )

        self.assertEqual(1, summary.events_removed)
        self.assertEqual([], self._events())

    def test_regular_import_stores_moving_time_and_load(self):
        self.client.event_payloads[0].update(
            {"moving_time": 2000, "icu_training_load": 55}
        )

        self.importer.import_range(self.start, self.end, include_intervals=False)

        event = self._events()[0]
        self.assertEqual(2000, event.duration_s)
        self.assertEqual(55, event.training_load)


class IntervalsCliTests(unittest.TestCase):

    def test_default_plan_horizon_is_182_days(self):
        args = build_parser().parse_args(["intervals"])

        self.assertEqual(182, args.plan_days)

    def test_plan_horizon_can_be_disabled(self):
        args = build_parser().parse_args(
            ["intervals", "--plan-days", "0"]
        )

        self.assertEqual(0, args.plan_days)

    def test_events_sync_arguments(self):
        args = build_parser().parse_args(
            [
                "events",
                "sync",
                "--from",
                "2026-01-01",
                "--to",
                "2026-02-01",
                "--plan-days",
                "30",
                "--dry-run",
            ]
        )

        self.assertEqual("events", args.command)
        self.assertEqual("sync", args.events_action)
        self.assertEqual("2026-01-01", args.start.isoformat())
        self.assertEqual("2026-02-01", args.end.isoformat())
        self.assertEqual(30, args.plan_days)
        self.assertTrue(args.dry_run)

    def test_events_sync_defaults(self):
        args = build_parser().parse_args(["events", "sync"])

        self.assertEqual(182, args.plan_days)
        self.assertIsNone(args.start)
        self.assertIsNone(args.end)
        self.assertFalse(args.dry_run)

    def test_event_range_defaults_to_today_and_horizon(self):
        today = date(2026, 11, 6)
        start, end = resolve_event_range(None, None, 182, today=today)

        self.assertEqual(today, start)
        self.assertEqual(today + timedelta(days=182), end)

    def test_event_range_honors_explicit_bounds(self):
        start, end = resolve_event_range(
            date(2026, 1, 1),
            date(2026, 2, 1),
            182,
            today=date(2026, 11, 6),
        )

        self.assertEqual(date(2026, 1, 1), start)
        self.assertEqual(date(2026, 2, 1), end)

    def test_event_range_rejects_reversed_bounds(self):
        with self.assertRaises(ValueError):
            resolve_event_range(
                date(2026, 2, 1),
                date(2026, 1, 1),
                182,
                today=date(2026, 11, 6),
            )


if __name__ == "__main__":
    unittest.main()
