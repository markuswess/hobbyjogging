import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_core.model import Interval


class TrainingWriterTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test", {"days": 1})
        self.source_id = self._source("a1", "checksum-1")

    def _source(self, external_id: str, checksum: str) -> int:
        return self.writer.upsert_source_record(
            source="test",
            record_type="activity",
            external_id=external_id,
            checksum=checksum,
            import_run_id=self.run_id,
            payload_json="{}",
        )

    def test_source_record_upsert_is_idempotent(self):
        again = self._source("a1", "checksum-2")

        self.assertEqual(self.source_id, again)
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )
        row = self.conn.execute(
            "SELECT checksum FROM source_records WHERE id = ?",
            (self.source_id,),
        ).fetchone()
        self.assertEqual("checksum-2", row["checksum"])

    def test_activity_insert_update_and_field_sources(self):
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "Morning run",
                "duration_s": 3600,
                "distance_m": 10000,
                "avg_hr": 140,
            },
            source="test",
            source_record_id=self.source_id,
        )
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "Updated run",
                "duration_s": 3600,
                "distance_m": 10000,
                "avg_hr": 142,
            },
            source="test",
            source_record_id=self.source_id,
        )

        activity = self.conn.execute(
            "SELECT * FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual("Updated run", activity["name"])
        self.assertEqual(142, activity["avg_hr"])
        self.assertEqual(self.source_id, activity["source_record_id"])

        sources = self.conn.execute(
            "SELECT field_name, source FROM activity_field_sources "
            "WHERE activity_id = 'a1' ORDER BY field_name"
        ).fetchall()
        self.assertEqual(
            ["avg_hr", "distance_m", "duration_s", "local_date", "name", "sport"],
            [row["field_name"] for row in sources],
        )

    def test_manual_field_is_not_overwritten(self):
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "Source name",
            },
            source="test",
            source_record_id=self.source_id,
        )
        self.conn.execute(
            "UPDATE activities SET name = 'Manual name' WHERE id = 'a1'"
        )
        self.conn.execute(
            "UPDATE activity_field_sources SET is_manual = 1, source = 'manual' "
            "WHERE activity_id = 'a1' AND field_name = 'name'"
        )

        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "New source name",
            },
            source="test",
            source_record_id=self.source_id,
        )

        activity = self.conn.execute(
            "SELECT name FROM activities WHERE id = 'a1'"
        ).fetchone()
        source = self.conn.execute(
            "SELECT source, is_manual FROM activity_field_sources "
            "WHERE activity_id = 'a1' AND field_name = 'name'"
        ).fetchone()
        self.assertEqual("Manual name", activity["name"])
        self.assertEqual("manual", source["source"])
        self.assertEqual(1, source["is_manual"])

    def test_activity_source_links_have_one_primary(self):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        second_source = self._source("a2", "checksum-2")
        self.writer.link_activity_source("a1", self.source_id)
        self.writer.link_activity_source("a1", second_source)

        rows = self.conn.execute(
            "SELECT source_record_id, is_primary FROM activity_sources "
            "ORDER BY source_record_id"
        ).fetchall()
        self.assertEqual(1, rows[0]["is_primary"])
        self.assertEqual(0, rows[1]["is_primary"])

    def test_zone_times_and_intervals_are_replaced(self):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        self.writer.set_activity_zone_times("a1", "pace", [600, 0, 30])
        self.writer.set_activity_zone_times("a1", "pace", [300])
        self.writer.replace_activity_intervals(
            "a1",
            [
                Interval(group_id="g1", type="WORK", duration_s=60),
                Interval(group_id="g2", type="RECOVERY", duration_s=120),
            ],
            source_record_id=self.source_id,
        )
        self.writer.replace_activity_intervals(
            "a1",
            [Interval(group_id="g3", type="WORK", duration_s=90)],
            source_record_id=self.source_id,
        )

        zones = self.conn.execute(
            "SELECT zone_index, seconds FROM activity_zone_times "
            "WHERE activity_id = 'a1' AND kind = 'pace'"
        ).fetchall()
        intervals = self.conn.execute(
            "SELECT interval_index, group_id FROM activity_intervals "
            "WHERE activity_id = 'a1'"
        ).fetchall()
        self.assertEqual([(1, 300)], [(row["zone_index"], row["seconds"]) for row in zones])
        self.assertEqual([(1, "g3")], [(row["interval_index"], row["group_id"]) for row in intervals])

    def test_wellness_and_event_upserts(self):
        self.writer.upsert_wellness(
            local_date="2026-10-01",
            source_record_id=self.source_id,
            hrv=60,
            resting_hr=50,
            sleep_s=28800,
        )
        self.writer.upsert_wellness(
            local_date="2026-10-01",
            source_record_id=self.source_id,
            hrv=None,
        )

        wellness = self.conn.execute(
            "SELECT hrv, resting_hr, sleep_s FROM wellness_days"
        ).fetchone()
        self.assertEqual(60, wellness["hrv"])
        self.assertEqual(50, wellness["resting_hr"])
        self.assertEqual(28800, wellness["sleep_s"])

        self.writer.upsert_event(
            event_id="e1",
            local_date="2026-10-02",
            name="Race",
            type="race",
            source_record_id=self.source_id,
            distance_m=5000,
        )
        self.writer.upsert_event(
            event_id="e1",
            local_date="2026-10-02",
            name="Town race",
            type="race",
            source_record_id=self.source_id,
        )

        event = self.conn.execute(
            "SELECT name, distance_m FROM events WHERE id = 'e1'"
        ).fetchone()
        self.assertEqual("Town race", event["name"])
        self.assertEqual(5000, event["distance_m"])

    def test_finish_import_run_records_counts(self):
        self.writer.finish_import_run(
            self.run_id,
            "success",
            records_seen=5,
            records_imported=4,
            records_skipped=1,
        )

        run = self.conn.execute(
            "SELECT status, records_seen, records_imported, records_skipped "
            "FROM import_runs WHERE id = ?",
            (self.run_id,),
        ).fetchone()
        self.assertEqual("success", run["status"])
        self.assertEqual(5, run["records_seen"])
        self.assertEqual(4, run["records_imported"])
        self.assertEqual(1, run["records_skipped"])


if __name__ == "__main__":
    unittest.main()
