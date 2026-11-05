import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_core.model import Interval, Lap


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
                "elapsed_s": 3700,
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
                "elapsed_s": 3700,
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
        self.assertEqual(3700, activity["elapsed_s"])
        self.assertEqual(142, activity["avg_hr"])
        self.assertEqual(self.source_id, activity["source_record_id"])

        sources = self.conn.execute(
            "SELECT field_name, source FROM activity_field_sources "
            "WHERE activity_id = 'a1' ORDER BY field_name"
        ).fetchall()
        self.assertEqual(
            [
                "avg_hr",
                "distance_m",
                "duration_s",
                "elapsed_s",
                "local_date",
                "name",
                "sport",
            ],
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

    def test_cross_source_fields_have_no_automatic_priority(self):
        """First owner keeps a field unless a human decides otherwise."""
        intervals_source = self._source("intervals-a1", "checksum-i")
        fit_source = self._source("fit-a1", "checksum-f")

        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "Intervals name",
                "duration_s": 3600,
                "elapsed_s": 3700,
                "distance_m": 10000,
                "avg_hr": 140,
                "training_load": 50,
            },
            source="intervals",
            source_record_id=intervals_source,
        )

        # FIT agrees except for a few fields: agreement changes nothing,
        # disagreement conflicts without writing or changing ownership.
        conflicts = self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "FIT name",
                "duration_s": 3700,
                "elapsed_s": 3700,
                "distance_m": 10500,
                "avg_hr": 145,
                "training_load": 99,
            },
            source="fit",
            source_record_id=fit_source,
        )

        self.assertEqual(4, len(conflicts))
        self.assertEqual(
            {(c.field_name, c.current_source, c.incoming_source)
             for c in conflicts},
            {
                ("duration_s", "intervals", "fit"),
                ("distance_m", "intervals", "fit"),
                ("avg_hr", "intervals", "fit"),
                ("training_load", "intervals", "fit"),
            },
        )

        activity = self.conn.execute(
            "SELECT sport, name, duration_s, elapsed_s, distance_m, "
            "avg_hr, training_load FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual("run", activity["sport"])
        self.assertEqual("Intervals name", activity["name"])
        self.assertEqual(3600, activity["duration_s"])
        self.assertEqual(3700, activity["elapsed_s"])
        self.assertEqual(10000, activity["distance_m"])
        self.assertEqual(140, activity["avg_hr"])
        self.assertEqual(50, activity["training_load"])

        owner = self.conn.execute(
            """
            SELECT source FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = 'duration_s'
            """
        ).fetchone()
        self.assertEqual("intervals", owner["source"])

        # A conflicting source reimporting does not resolve or duplicate
        # anything: the same disagreement yields no further writes.
        again = self.writer.upsert_activity(
            "a1",
            {"duration_s": 3650},
            source="fit",
            source_record_id=fit_source,
        )
        self.assertEqual(1, len(again))

    def test_same_source_refresh_its_own_fields(self):
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run", "duration_s": 3600},
            source="fit",
            source_record_id=self.source_id,
        )
        self.writer.upsert_activity(
            "a1",
            {"duration_s": 3610},
            source="fit",
            source_record_id=self.source_id,
        )

        self.assertEqual(
            3610,
            self.conn.execute(
                "SELECT duration_s FROM activities WHERE id = 'a1'"
            ).fetchone()[0],
        )

    def test_agreement_within_tolerance_is_not_a_conflict(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "duration_s": 3600,
                "elapsed_s": 3700,
                "distance_m": 10000,
            },
            source="intervals",
            source_record_id=self.source_id,
        )

        # 1% of 3600 s = 36 s, so a 30 s drift agrees; 1% of 10000 m = 100 m,
        # so 10100 m agrees too.
        conflicts = self.writer.upsert_activity(
            "a1",
            {"duration_s": 3630, "elapsed_s": 3671, "distance_m": 10100},
            source="fit",
            source_record_id=fit_source,
        )

        self.assertEqual([], conflicts)
        row = self.conn.execute(
            "SELECT duration_s, elapsed_s, distance_m"
            " FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(
            (3600, 3700, 10000),
            (row["duration_s"], row["elapsed_s"], row["distance_m"]),
        )

    def test_absolute_floor_protects_short_values(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "duration_s": 120,
                "distance_m": 500,
            },
            source="intervals",
            source_record_id=self.source_id,
        )

        # 1% of 120 s is 1.2 s — under the 2 s floor these differ.
        conflicts = self.writer.upsert_activity(
            "a1",
            {"duration_s": 122.5, "distance_m": 505},
            source="fit",
            source_record_id=fit_source,
        )

        self.assertEqual(1, len(conflicts))
        self.assertEqual("duration_s", conflicts[0].field_name)

    def test_start_time_tolerance(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "started_at_utc": "2026-10-01T06:00:00Z",
            },
            source="intervals",
            source_record_id=self.source_id,
        )

        agree = self.writer.upsert_activity(
            "a1",
            {"started_at_utc": "2026-10-01T06:00:10Z"},
            source="fit",
            source_record_id=fit_source,
        )
        self.assertEqual([], agree)

        conflict = self.writer.upsert_activity(
            "a1",
            {"started_at_utc": "2026-10-01T06:01:00Z"},
            source="fit",
            source_record_id=fit_source,
        )
        self.assertEqual(1, len(conflict))
        self.assertEqual("started_at_utc", conflict[0].field_name)

    def test_conflict_does_not_touch_owner_when_source_fills_gap(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run", "duration_s": 3600},
            source="intervals",
            source_record_id=self.source_id,
        )

        # FIT brings a value for a field the owner never wrote: no conflict
        # exists (nothing to disagree with), the gap gets filled.
        conflicts = self.writer.upsert_activity(
            "a1",
            {"distance_m": 10000},
            source="fit",
            source_record_id=fit_source,
        )

        self.assertEqual([], conflicts)
        row = self.conn.execute(
            "SELECT distance_m FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(10000, row["distance_m"])
        owner = self.conn.execute(
            "SELECT source FROM activity_field_sources"
            " WHERE activity_id = 'a1' AND field_name = 'distance_m'"
        ).fetchone()
        self.assertEqual("fit", owner["source"])

    def test_manual_field_outranks_cross_source_agreement_and_disagreement(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run", "duration_s": 3600},
            source="intervals",
            source_record_id=self.source_id,
        )
        self.writer.set_manual_field("a1", "duration_s", 2780)

        conflicts = self.writer.upsert_activity(
            "a1",
            {"duration_s": 9999},
            source="fit",
            source_record_id=fit_source,
        )

        self.assertEqual([], conflicts)
        self.assertEqual(
            2780,
            self.conn.execute(
                "SELECT duration_s FROM activities WHERE id = 'a1'"
            ).fetchone()[0],
        )

    def test_specific_sport_fills_unknown_placeholder(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "other"},
            source="intervals",
            source_record_id=self.source_id,
        )

        conflicts = self.writer.upsert_activity(
            "a1",
            {"sport": "alpine_skiing"},
            source="fit",
            source_record_id=fit_source,
        )

        self.assertEqual([], conflicts)
        row = self.conn.execute(
            "SELECT sport FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual("alpine_skiing", row["sport"])
        owner = self.conn.execute(
            """
            SELECT source FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = 'sport'
            """
        ).fetchone()
        self.assertEqual("fit", owner["source"])

    def test_unknown_sport_does_not_conflict_with_specific(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "soccer"},
            source="intervals",
            source_record_id=self.source_id,
        )

        conflicts = self.writer.upsert_activity(
            "a1",
            {"sport": "generic"},
            source="fit",
            source_record_id=fit_source,
        )

        self.assertEqual([], conflicts)
        row = self.conn.execute(
            "SELECT sport FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual("soccer", row["sport"])

    def test_different_specific_sports_conflict(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "trail_run"},
            source="intervals",
            source_record_id=self.source_id,
        )

        conflicts = self.writer.upsert_activity(
            "a1",
            {"sport": "run"},
            source="fit",
            source_record_id=fit_source,
        )

        self.assertEqual(1, len(conflicts))
        self.assertEqual("sport", conflicts[0].field_name)

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

    def test_activity_laps_are_replaced(self):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        self.writer.replace_activity_laps(
            "a1",
            [
                Lap(
                    index=1,
                    start_time_utc="2026-10-01T06:00:00Z",
                    duration_s=60,
                    distance_m=200,
                    avg_hr=150,
                    max_hr=160,
                    elevation_gain_m=1,
                ),
                Lap(
                    index=2,
                    start_time_utc="2026-10-01T06:01:00Z",
                    duration_s=120,
                    distance_m=300,
                ),
            ],
            source_record_id=self.source_id,
        )
        self.writer.replace_activity_laps(
            "a1",
            [Lap(index=1, duration_s=90)],
            source_record_id=self.source_id,
        )

        laps = self.conn.execute(
            "SELECT lap_index, duration_s FROM activity_laps "
            "WHERE activity_id = 'a1'"
        ).fetchall()
        self.assertEqual([(1, 90)], [(row["lap_index"], row["duration_s"]) for row in laps])

    def test_activity_laps_merge_by_source(self):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        second_source = self._source("fit-2", "checksum-2")

        self.writer.merge_activity_laps(
            "a1",
            [
                Lap(
                    index=1,
                    start_time_utc="2026-10-01T06:00:00Z",
                    duration_s=60,
                ),
                Lap(
                    index=2,
                    start_time_utc="2026-10-01T06:10:00Z",
                    duration_s=60,
                ),
            ],
            source_record_id=self.source_id,
        )
        self.writer.merge_activity_laps(
            "a1",
            [
                Lap(
                    index=1,
                    start_time_utc="2026-10-01T06:05:00Z",
                    duration_s=60,
                )
            ],
            source_record_id=second_source,
        )

        laps = self.conn.execute(
            "SELECT lap_index, start_time_utc, source_record_id "
            "FROM activity_laps WHERE activity_id = 'a1' ORDER BY lap_index"
        ).fetchall()
        self.assertEqual(
            [
                (1, "2026-10-01T06:00:00Z", self.source_id),
                (2, "2026-10-01T06:05:00Z", second_source),
                (3, "2026-10-01T06:10:00Z", self.source_id),
            ],
            [
                (row["lap_index"], row["start_time_utc"], row["source_record_id"])
                for row in laps
            ],
        )

        self.writer.merge_activity_laps(
            "a1",
            [
                Lap(
                    index=1,
                    start_time_utc="2026-10-01T06:02:00Z",
                    duration_s=90,
                )
            ],
            source_record_id=self.source_id,
        )

        laps = self.conn.execute(
            "SELECT lap_index, start_time_utc, source_record_id "
            "FROM activity_laps WHERE activity_id = 'a1' ORDER BY lap_index"
        ).fetchall()
        self.assertEqual(
            [
                (1, "2026-10-01T06:02:00Z", self.source_id),
                (2, "2026-10-01T06:05:00Z", second_source),
            ],
            [
                (row["lap_index"], row["start_time_utc"], row["source_record_id"])
                for row in laps
            ],
        )

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
