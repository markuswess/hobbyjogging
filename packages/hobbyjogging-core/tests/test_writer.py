import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_core.model import EventZoneTime, Interval, Lap


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

    def test_blank_text_is_a_gap_a_later_source_can_fill(self):
        intervals_source = self.writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id="i1",
            checksum="c-i",
            import_run_id=self.run_id,
        )
        fit_source = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="f1",
            checksum="c-f",
            import_run_id=self.run_id,
        )

        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "",
                "description": "   ",
            },
            source="intervals",
            source_record_id=intervals_source,
        )

        conflicts = self.writer.upsert_activity(
            "a1",
            {"name": "Liesingbachrunde", "description": "Locker"},
            source="fit",
            source_record_id=fit_source,
        )

        self.assertEqual([], conflicts)
        row = self.conn.execute(
            "SELECT name, description FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(("Liesingbachrunde", "Locker"), tuple(row))

        owners = self.conn.execute(
            """
            SELECT field_name, source FROM activity_field_sources
            WHERE activity_id = 'a1'
              AND field_name IN ('name', 'description')
            """
        ).fetchall()
        self.assertEqual(
            {"name": "fit", "description": "fit"},
            {row["field_name"]: row["source"] for row in owners},
        )

        # An empty incoming text never clears a filled value.
        self.writer.upsert_activity(
            "a1",
            {"description": ""},
            source="intervals",
            source_record_id=intervals_source,
        )
        self.assertEqual(
            "Locker",
            self.conn.execute(
                "SELECT description FROM activities WHERE id = 'a1'"
            ).fetchone()[0],
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
                "avg_hr": 147,
                "training_load": 99,
            },
            source="fit",
            source_record_id=fit_source,
        )

        # The 100 s duration difference fits inside the 100 s pause gap, so
        # it is recording semantics rather than a competing measurement.
        self.assertEqual(3, len(conflicts))
        self.assertEqual(
            {(c.field_name, c.current_source, c.incoming_source)
             for c in conflicts},
            {
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
            {"duration_s": 3800},
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

        # 5% of 3600 s = 180 s, so a 30 s drift agrees; 1% of 10000 m = 100 m,
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

    def test_duration_tolerance_is_five_percent(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run", "duration_s": 3600},
            source="intervals",
            source_record_id=self.source_id,
        )

        # FIT and Intervals recording time can differ by up to ~5%; the cause
        # classifier calls that a small difference, so it is not a conflict.
        agree = self.writer.upsert_activity(
            "a1",
            {"duration_s": 3780},
            source="fit",
            source_record_id=fit_source,
        )
        self.assertEqual([], agree)

        # Beyond 5% it is a different recording, not accounting noise.
        conflict = self.writer.upsert_activity(
            "a1",
            {"duration_s": 3800},
            source="fit",
            source_record_id=fit_source,
        )
        self.assertEqual(["duration_s"], [c.field_name for c in conflict])

    def test_avg_hr_tolerance_is_five_bpm(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run", "avg_hr": 140},
            source="intervals",
            source_record_id=self.source_id,
        )

        # Device averages and stream averages drift by a few bpm; that is not
        # worth a review item.
        conflicts = self.writer.upsert_activity(
            "a1",
            {"avg_hr": 145},
            source="fit",
            source_record_id=fit_source,
        )
        self.assertEqual([], conflicts)

        # A wider gap is still a real disagreement.
        conflicts = self.writer.upsert_activity(
            "a1",
            {"avg_hr": 146},
            source="fit",
            source_record_id=fit_source,
        )
        self.assertEqual(["avg_hr"], [c.field_name for c in conflicts])
        self.assertEqual(
            140,
            self.conn.execute(
                "SELECT avg_hr FROM activities WHERE id = 'a1'"
            ).fetchone()[0],
        )

    def test_absolute_floor_protects_short_values(self):
        fit_source = self._source("fit-a1", "checksum-f")
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "duration_s": 30,
                "distance_m": 500,
            },
            source="intervals",
            source_record_id=self.source_id,
        )

        # 5% of 30 s is 1.5 s — under the 2 s floor these differ.
        conflicts = self.writer.upsert_activity(
            "a1",
            {"duration_s": 32.5, "distance_m": 505},
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
        self.assertIsNone(event["distance_m"])

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


class Vo2maxAndTagTests(unittest.TestCase):
    """Independent VO2max owners and per-source tag replacement."""

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

        self.intervals_id = self._source("intervals", "i1", "c-i")
        self.fit_id = self._source("fit", "f1", "c-f")
        self.runalyze_id = self._source("runalyze", "r1", "c-r")

        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run"},
            source="intervals",
            source_record_id=self.intervals_id,
        )

    def _source(self, source, external_id, checksum):
        return self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=external_id,
            checksum=checksum,
            import_run_id=self.run_id,
        )

    def _values(self):
        return self.conn.execute(
            "SELECT vo2max_garmin, vo2max_runalyze FROM activities "
            "WHERE id = 'a1'"
        ).fetchone()

    def _upsert(self, values, source, record_id):
        return self.writer.upsert_activity(
            "a1",
            values,
            source=source,
            source_record_id=record_id,
        )

    def test_vo2max_fields_have_independent_owners(self):
        conflicts = self._upsert(
            {"vo2max_garmin": 52.0},
            "fit",
            self.fit_id,
        )
        conflicts += self._upsert(
            {"vo2max_runalyze": 50.0},
            "runalyze",
            self.runalyze_id,
        )

        self.assertEqual([], conflicts)
        values = self._values()
        self.assertEqual(52.0, values["vo2max_garmin"])
        self.assertEqual(50.0, values["vo2max_runalyze"])

    def test_runalyze_fills_garmin_only_when_empty_and_fit_replaces_it(self):
        self._upsert(
            {"vo2max_garmin": 49.0, "vo2max_runalyze": 49.0},
            "runalyze",
            self.runalyze_id,
        )
        values = self._values()
        self.assertEqual(49.0, values["vo2max_garmin"])
        self.assertEqual(49.0, values["vo2max_runalyze"])

        self._upsert({"vo2max_garmin": 52.0}, "fit", self.fit_id)
        values = self._values()
        self.assertEqual(52.0, values["vo2max_garmin"])
        self.assertEqual(49.0, values["vo2max_runalyze"])

        # A later Runalyze import refreshes its own estimate but must not
        # overwrite the Garmin value it only filled as a fallback.
        self._upsert(
            {"vo2max_garmin": 50.0, "vo2max_runalyze": 50.0},
            "runalyze",
            self.runalyze_id,
        )
        values = self._values()
        self.assertEqual(52.0, values["vo2max_garmin"])
        self.assertEqual(50.0, values["vo2max_runalyze"])

    def test_manual_vo2max_wins(self):
        self.writer.set_manual_field("a1", "vo2max_garmin", 55.0)

        conflicts = self._upsert(
            {"vo2max_garmin": 52.0},
            "fit",
            self.fit_id,
        )

        self.assertEqual([], conflicts)
        self.assertEqual(55.0, self._values()["vo2max_garmin"])

    def test_replace_tags_per_source_keeps_manual_tags(self):
        self.assertEqual(
            2,
            self.writer.replace_activity_tags(
                "a1",
                ["race", "morning"],
                source="runalyze",
                source_record_id=self.runalyze_id,
            ),
        )
        self.writer.replace_activity_tags(
            "a1",
            ["key session"],
            source="manual",
            is_manual=True,
        )

        self.assertEqual(
            1,
            self.writer.replace_activity_tags(
                "a1",
                ["race"],
                source="runalyze",
                source_record_id=self.runalyze_id,
            ),
        )

        rows = self.conn.execute(
            """
            SELECT tag, source, is_manual FROM activity_tags
            WHERE activity_id = 'a1' ORDER BY tag
            """
        ).fetchall()
        self.assertEqual(
            [("key session", "manual", 1), ("race", "runalyze", 0)],
            [(row["tag"], row["source"], row["is_manual"]) for row in rows],
        )

    def test_replace_tags_deduplicates_and_strips(self):
        written = self.writer.replace_activity_tags(
            "a1",
            [" race ", "race", "", "  "],
            source="runalyze",
            source_record_id=self.runalyze_id,
        )

        self.assertEqual(1, written)

    def test_replace_tags_rejects_unknown_or_excluded_activity(self):
        with self.assertRaises(ValueError):
            self.writer.replace_activity_tags("nope", ["x"], source="runalyze")

        self.writer.exclude_activity("a1")
        with self.assertRaises(ValueError):
            self.writer.replace_activity_tags("a1", ["x"], source="runalyze")

    def test_moving_time_is_intervals_authoritative(self):
        self._upsert({"moving_s": 1100}, "fit", self.fit_id)

        conflicts = self._upsert(
            {"moving_s": 1055},
            "intervals",
            self.intervals_id,
        )

        self.assertEqual([], conflicts)
        self.assertEqual(
            1055,
            self.conn.execute(
                "SELECT moving_s FROM activities WHERE id = 'a1'"
            ).fetchone()[0],
        )

        # A later FIT value neither overrides Intervals nor opens a conflict.
        conflicts = self._upsert({"moving_s": 1200}, "fit", self.fit_id)
        self.assertEqual([], conflicts)
        self.assertEqual(
            1055,
            self.conn.execute(
                "SELECT moving_s FROM activities WHERE id = 'a1'"
            ).fetchone()[0],
        )

        # Manual still wins over the authoritative source.
        self.writer.set_manual_field("a1", "moving_s", 1055)
        self._upsert({"moving_s": 999}, "intervals", self.intervals_id)
        self.assertEqual(
            1055,
            self.conn.execute(
                "SELECT moving_s FROM activities WHERE id = 'a1'"
            ).fetchone()[0],
        )

    def test_event_training_load_is_upserted(self):
        self.writer.upsert_event(
            event_id="e1",
            local_date="2026-04-01",
            name="5x6 LT1",
            type="run",
            source_record_id=self.intervals_id,
            duration_s=3450,
            distance_m=12984,
            training_load=62,
        )
        row = self.conn.execute(
            "SELECT duration_s, distance_m, training_load FROM events "
            "WHERE id = 'e1'"
        ).fetchone()
        self.assertEqual(3450, row["duration_s"])
        self.assertEqual(12984, row["distance_m"])
        self.assertEqual(62, row["training_load"])

        # A later event refresh without a load clears it: Intervals is
        # authoritative, so stale values must not survive.
        self.writer.upsert_event(
            event_id="e1",
            local_date="2026-04-01",
            name="5x6 LT1",
            type="run",
            source_record_id=self.intervals_id,
            duration_s=3450,
        )
        self.assertIsNone(
            self.conn.execute(
                "SELECT training_load FROM events WHERE id = 'e1'"
            ).fetchone()[0],
        )

    def test_set_event_zone_times_replaces_and_clears(self):
        self.writer.upsert_event(
            event_id="e1",
            local_date="2026-04-01",
            name="5x6 LT1",
            type="run",
            source_record_id=self.intervals_id,
        )

        written = self.writer.set_event_zone_times(
            "e1",
            "pace",
            [
                EventZoneTime("Z1", 1650, 1),
                EventZoneTime("Z3", 1500, 3),
                EventZoneTime("Z4", 300, 4),
            ],
        )
        self.assertEqual(3, written)
        self.assertEqual(
            "pace",
            self.conn.execute(
                "SELECT zone_kind FROM events WHERE id = 'e1'"
            ).fetchone()[0],
        )
        self.assertEqual(
            3,
            self.conn.execute(
                "SELECT COUNT(*) FROM event_zone_times"
            ).fetchone()[0],
        )

        # Replacing with a different set removes the old rows.
        self.writer.set_event_zone_times(
            "e1",
            "hr",
            [EventZoneTime("Z2", 1800, 2)],
        )
        rows = self.conn.execute(
            "SELECT zone_label, seconds FROM event_zone_times"
        ).fetchall()
        self.assertEqual([("Z2", 1800)], [tuple(row) for row in rows])

        # An empty set clears the distribution and the kind.
        self.assertEqual(
            0,
            self.writer.set_event_zone_times("e1", "", []),
        )
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM event_zone_times"
            ).fetchone()[0],
        )
        self.assertEqual(
            "",
            self.conn.execute(
                "SELECT zone_kind FROM events WHERE id = 'e1'"
            ).fetchone()[0],
        )

    def test_set_event_zone_times_rejects_unknown_event(self):
        with self.assertRaises(ValueError):
            self.writer.set_event_zone_times("nope", "pace", [])

    def test_activity_workout_sets_replace_per_source_and_manual_wins(self):
        self.assertEqual(
            2,
            self.writer.replace_activity_workout_methods(
                "a1",
                ["intervals", "strides"],
                source="sheet",
                source_record_id=self.intervals_id,
            ),
        )
        self.writer.replace_activity_workout_methods(
            "a1",
            ["continuous"],
            source="classifier",
        )
        self.writer.replace_activity_workout_targets(
            "a1",
            ["vo2max"],
            source="sheet",
            source_record_id=self.intervals_id,
        )

        def methods():
            return [
                row[0]
                for row in self.conn.execute(
                    "SELECT method FROM activity_workout_methods "
                    "WHERE activity_id = 'a1' ORDER BY method"
                )
            ]

        def targets():
            return [
                row[0]
                for row in self.conn.execute(
                    "SELECT target FROM activity_workout_targets "
                    "WHERE activity_id = 'a1' ORDER BY target"
                )
            ]

        self.assertEqual(["continuous", "intervals", "strides"], methods())
        self.assertEqual(["vo2max"], targets())

        # A manual value is added and never replaced by a source.
        self.writer.replace_activity_workout_methods(
            "a1",
            ["progression"],
            source="manual",
            is_manual=True,
        )
        self.writer.replace_activity_workout_methods(
            "a1",
            ["intervals", "progression"],
            source="sheet",
            source_record_id=self.intervals_id,
        )
        # The sheet's old values are replaced, the classifier's continuous
        # value and the manual progression value remain.
        self.assertEqual(
            ["continuous", "intervals", "progression"],
            methods(),
        )

        row = self.conn.execute(
            "SELECT is_manual FROM activity_workout_methods "
            "WHERE activity_id = 'a1' AND method = 'progression'"
        ).fetchone()
        self.assertEqual(1, row["is_manual"])

    def test_set_manual_activity_workout_methods_clears_every_source(self):
        self.writer.replace_activity_workout_methods(
            "a1",
            ["intervals", "strides"],
            source="backfill",
        )

        written = self.writer.set_manual_activity_workout_methods(
            "a1",
            ["continuous"],
        )

        self.assertEqual(1, written)
        rows = self.conn.execute(
            "SELECT method, source, is_manual FROM activity_workout_methods "
            "WHERE activity_id = 'a1'"
        ).fetchall()
        self.assertEqual(
            [("continuous", "manual", 1)],
            [(row["method"], row["source"], row["is_manual"]) for row in rows],
        )

    def test_set_manual_activity_workout_methods_normalizes_retired_tempo(self):
        self.writer.set_manual_activity_workout_methods("a1", ["tempo"])

        methods = [
            row[0]
            for row in self.conn.execute(
                "SELECT method FROM activity_workout_methods "
                "WHERE activity_id = 'a1'"
            )
        ]
        self.assertEqual(["continuous"], methods)

    def test_set_manual_activity_workout_methods_rejects_unknown_entity(self):
        with self.assertRaises(ValueError):
            self.writer.set_manual_activity_workout_methods(
                "missing", ["continuous"]
            )

    def test_event_workout_sets(self):
        self.writer.upsert_event(
            event_id="e1",
            local_date="2026-04-01",
            name="5x6 LT1",
            type="run",
            source_record_id=self.intervals_id,
        )
        self.writer.replace_event_workout_methods(
            "e1",
            ["intervals", "strides"],
            source="manual",
            is_manual=True,
        )
        self.writer.replace_event_workout_targets(
            "e1",
            ["vo2max"],
            source="manual",
            is_manual=True,
        )
        self.assertEqual(
            ["intervals", "strides"],
            [
                row[0]
                for row in self.conn.execute(
                    "SELECT method FROM event_workout_methods "
                    "WHERE event_id = 'e1' ORDER BY method"
                )
            ],
        )
        self.assertEqual(
            ["vo2max"],
            [
                row[0]
                for row in self.conn.execute(
                    "SELECT target FROM event_workout_targets "
                    "WHERE event_id = 'e1' ORDER BY target"
                )
            ],
        )

    def test_workout_sets_reject_unknown_or_excluded_entity(self):
        with self.assertRaises(ValueError):
            self.writer.replace_activity_workout_methods(
                "nope", ["intervals"], source="manual"
            )
        self.writer.exclude_activity("a1")
        with self.assertRaises(ValueError):
            self.writer.replace_activity_workout_methods(
                "a1", ["intervals"], source="manual"
            )

    def test_event_exclusion_and_revival(self):
        self.writer.upsert_event(
            event_id="e1",
            local_date="2026-04-01",
            name="5x6 LT1",
            type="run",
            source_record_id=self.intervals_id,
            duration_s=3450,
        )

        self.assertTrue(self.writer.exclude_event("e1"))
        self.assertFalse(self.writer.exclude_event("e1"))
        self.assertIsNotNone(
            self.conn.execute(
                "SELECT excluded_at FROM events WHERE id = 'e1'"
            ).fetchone()[0],
        )

        # Upserting a fetched event revives it and replaces its fields.
        self.writer.upsert_event(
            event_id="e1",
            local_date="2026-04-02",
            name="5x6 LT1 (moved)",
            type="run",
            source_record_id=self.intervals_id,
        )
        row = self.conn.execute(
            "SELECT local_date, name, duration_s, excluded_at FROM events "
            "WHERE id = 'e1'"
        ).fetchone()
        self.assertEqual("2026-04-02", row["local_date"])
        self.assertEqual("5x6 LT1 (moved)", row["name"])
        self.assertIsNone(row["duration_s"])
        self.assertIsNone(row["excluded_at"])

        self.assertFalse(self.writer.restore_event("e1"))


class ForcedActivityUpsertTests(unittest.TestCase):
    """A human-trusted source can take ownership of non-manual fields."""

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.fit_id = self._source("fit", "f1", "c-f")
        self.intervals_id = self._source("intervals", "i1", "c-i")

        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "duration_s": 3600,
                "avg_hr": 140,
            },
            source="fit",
            source_record_id=self.fit_id,
        )

    def _source(self, source, external_id, checksum):
        return self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=external_id,
            checksum=checksum,
            import_run_id=self.run_id,
        )

    def _field_sources(self):
        rows = self.conn.execute(
            """
            SELECT field_name, source FROM activity_field_sources
            WHERE activity_id = 'a1'
            """
        ).fetchall()
        return {
            row["field_name"]: row["source"]
            for row in rows
        }

    def test_force_overwrites_another_source_owner(self):
        conflicts = self.writer.upsert_activity(
            "a1",
            {"duration_s": 3700, "avg_hr": 145},
            source="intervals",
            source_record_id=self.intervals_id,
            force=True,
        )

        self.assertEqual([], conflicts)
        row = self.conn.execute(
            "SELECT duration_s, avg_hr FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(3700, row["duration_s"])
        self.assertEqual(145, row["avg_hr"])

        sources = self._field_sources()
        self.assertEqual("intervals", sources["duration_s"])
        self.assertEqual("intervals", sources["avg_hr"])

    def test_force_keeps_manual_fields(self):
        self.writer.set_manual_field("a1", "duration_s", 3600)

        conflicts = self.writer.upsert_activity(
            "a1",
            {"duration_s": 3700, "avg_hr": 145},
            source="intervals",
            source_record_id=self.intervals_id,
            force=True,
        )

        self.assertEqual([], conflicts)
        row = self.conn.execute(
            "SELECT duration_s, avg_hr FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(3600, row["duration_s"])
        self.assertEqual(145, row["avg_hr"])

        sources = self._field_sources()
        self.assertEqual("fit", sources["duration_s"])
        self.assertEqual("intervals", sources["avg_hr"])


class DurationSemanticsTests(unittest.TestCase):
    """A stop between two recordings is not a duration conflict."""

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.fit_id = self._source("fit", "f1", "c-f")
        self.intervals_id = self._source("intervals", "i1", "c-i")

        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "duration_s": 3600,
                "elapsed_s": 3900,
            },
            source="fit",
            source_record_id=self.fit_id,
        )

    def _source(self, source, external_id, checksum):
        return self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=external_id,
            checksum=checksum,
            import_run_id=self.run_id,
        )

    def _values(self):
        return self.conn.execute(
            "SELECT duration_s, elapsed_s FROM activities WHERE id = 'a1'"
        ).fetchone()

    def _source_of(self, field_name):
        return self.conn.execute(
            """
            SELECT source FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = ?
            """,
            (field_name,),
        ).fetchone()["source"]

    def test_pause_gap_absorbs_duration_difference(self):
        conflicts = self.writer.upsert_activity(
            "a1",
            {"duration_s": 3500, "elapsed_s": 3900},
            source="intervals",
            source_record_id=self.intervals_id,
        )

        self.assertEqual([], conflicts)
        self.assertEqual(3600, self._values()["duration_s"])
        self.assertEqual("fit", self._source_of("duration_s"))

    def test_difference_beyond_pause_gap_conflicts(self):
        conflicts = self.writer.upsert_activity(
            "a1",
            {"duration_s": 3000, "elapsed_s": 3300},
            source="intervals",
            source_record_id=self.intervals_id,
        )

        self.assertIn(
            "duration_s",
            {conflict.field_name for conflict in conflicts},
        )
        self.assertNotIn(
            "elapsed_s",
            {conflict.field_name for conflict in conflicts},
        )
        self.assertEqual(3600, self._values()["duration_s"])
        self.assertEqual(3300, self._values()["elapsed_s"])
        self.assertEqual("intervals", self._source_of("elapsed_s"))

    def test_intervals_elapsed_overrides_fit_silently(self):
        conflicts = self.writer.upsert_activity(
            "a1",
            {"elapsed_s": 3300},
            source="intervals",
            source_record_id=self.intervals_id,
        )

        self.assertEqual([], conflicts)
        self.assertEqual(3300, self._values()["elapsed_s"])
        self.assertEqual("intervals", self._source_of("elapsed_s"))

    def test_fit_elapsed_does_not_override_intervals(self):
        self.writer.upsert_activity(
            "a1",
            {"elapsed_s": 3300},
            source="intervals",
            source_record_id=self.intervals_id,
        )

        conflicts = self.writer.upsert_activity(
            "a1",
            {"elapsed_s": 3900},
            source="fit",
            source_record_id=self.fit_id,
        )

        self.assertEqual([], conflicts)
        self.assertEqual(3300, self._values()["elapsed_s"])
        self.assertEqual("intervals", self._source_of("elapsed_s"))

    def test_same_source_refresh_still_writes(self):
        conflicts = self.writer.upsert_activity(
            "a1",
            {"duration_s": 3500, "elapsed_s": 3900},
            source="fit",
            source_record_id=self.fit_id,
        )

        self.assertEqual([], conflicts)
        self.assertEqual(3500, self._values()["duration_s"])
        self.assertEqual("fit", self._source_of("duration_s"))


class DistancePolicyTests(unittest.TestCase):
    """Distance is canonical zero for sports where it is not meaningful."""

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.fit_id = self._source("fit", "f1", "c-f")
        self.intervals_id = self._source("intervals", "i1", "c-i")

    def _source(self, source, external_id, checksum):
        return self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=external_id,
            checksum=checksum,
            import_run_id=self.run_id,
        )

    def _insert(self, sport, distance_m):
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": sport,
                "distance_m": distance_m,
                "duration_s": 1800,
            },
            source="intervals",
            source_record_id=self.intervals_id,
        )
        return self.conn.execute(
            "SELECT distance_m FROM activities WHERE id = 'a1'"
        ).fetchone()["distance_m"]

    def test_no_distance_sports_are_zeroed(self):
        for sport in (
            "treadmill_run",
            "virtual_run",
            "soccer",
            "racket",
            "training",
            "other",
            "workout",
        ):
            with self.subTest(sport=sport):
                self.conn.execute("DELETE FROM activities")
                self.conn.execute("DELETE FROM activity_field_sources")
                self.assertEqual(0, self._insert(sport, 8000))

    def test_distance_sports_keep_the_value(self):
        self.assertEqual(10000, self._insert("run", 10000))

    def test_manual_distance_wins(self):
        self._insert("treadmill_run", 8000)
        self.writer.set_manual_field("a1", "distance_m", 5000)

        self.writer.upsert_activity(
            "a1",
            {
                "sport": "treadmill_run",
                "distance_m": 9000,
            },
            source="intervals",
            source_record_id=self.intervals_id,
        )

        row = self.conn.execute(
            "SELECT distance_m FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(5000, row["distance_m"])
        source = self.conn.execute(
            """
            SELECT source, is_manual FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = 'distance_m'
            """
        ).fetchone()
        self.assertEqual("intervals", source["source"])
        self.assertEqual(1, source["is_manual"])

    def test_sport_update_to_no_distance_sport_zeroes_existing_distance(self):
        self._insert("other", 529)

        self.writer.upsert_activity(
            "a1",
            {
                "sport": "soccer",
                "distance_m": 529,
            },
            source="intervals",
            source_record_id=self.intervals_id,
        )

        row = self.conn.execute(
            "SELECT distance_m, sport FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(0, row["distance_m"])
        self.assertEqual("soccer", row["sport"])


class EquipmentTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.sheet_source = self._source("sheet", "1", "c-sheet")
        self.fit_source = self._source("fit", "f1", "c-fit")

        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run"},
            source="fit",
            source_record_id=self.fit_source,
        )

    def _source(self, source, external_id, checksum):
        return self.writer.upsert_source_record(
            source=source,
            record_type="equipment",
            external_id=external_id,
            checksum=checksum,
            import_run_id=self.run_id,
        )

    def _equipment(self, equipment_id="sheet:equipment:1"):
        self.writer.upsert_equipment(
            equipment_id,
            type="shoe",
            name="Asics GT-2000 1",
            brand="Asics",
            model="GT-2000 1",
            acquired_on="2008-01-01",
            retired_on="2018-04-09",
            notes="size 42.5",
            source_record_id=self.sheet_source,
        )

    def _links(self):
        return self.conn.execute(
            """
            SELECT equipment_id, role, source, is_manual
            FROM activity_equipment WHERE activity_id = 'a1'
            """
        ).fetchall()

    def test_equipment_upsert_is_idempotent(self):
        self._equipment()
        created = self.writer.upsert_equipment(
            "sheet:equipment:1",
            type="shoe",
            name="Asics GT-2000 1",
            brand="Asics",
            model="GT-2000 1",
            acquired_on="2008-01-01",
            retired_on="2018-04-09",
            notes="size 42.5",
            source_record_id=self.sheet_source,
        )

        self.assertFalse(created)
        rows = self.writer.connection.execute(
            "SELECT * FROM equipment"
        ).fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual("Asics", rows[0]["brand"])
        self.assertEqual("2008-01-01", rows[0]["acquired_on"])

        linked = self.conn.execute(
            """
            SELECT equipment_id FROM equipment_source_links
            WHERE source_record_id = ?
            """,
            (self.sheet_source,),
        ).fetchall()
        self.assertEqual(["sheet:equipment:1"], [r[0] for r in linked])

    def test_link_equipment_source_does_not_change_the_row(self):
        self._equipment()
        self.writer.upsert_equipment(
            "runalyze:equipment:1",
            type="shoe",
            name="Runalyze shoe",
        )
        gear_source = self._source("runalyze", "g1", "c-gear")

        self.assertTrue(
            self.writer.link_equipment_source(
                "sheet:equipment:1",
                gear_source,
            )
        )
        self.assertFalse(
            self.writer.link_equipment_source(
                "sheet:equipment:1",
                gear_source,
            )
        )

        row = self.conn.execute(
            "SELECT name, brand, model FROM equipment "
            "WHERE id = 'sheet:equipment:1'"
        ).fetchone()
        self.assertEqual("Asics GT-2000 1", row["name"])
        self.assertEqual("Asics", row["brand"])
        self.assertEqual("GT-2000 1", row["model"])

        self.assertTrue(
            self.writer.link_equipment_source(
                "runalyze:equipment:1",
                gear_source,
            )
        )
        linked = self.conn.execute(
            "SELECT equipment_id FROM equipment_source_links "
            "WHERE source_record_id = ?",
            (gear_source,),
        ).fetchone()
        self.assertEqual("runalyze:equipment:1", linked["equipment_id"])

    def test_link_equipment_is_idempotent_and_manual_wins(self):
        self._equipment()

        self.assertTrue(
            self.writer.link_activity_equipment(
                "a1",
                "sheet:equipment:1",
                source="sheet",
                source_record_id=self.sheet_source,
            )
        )
        self.assertFalse(
            self.writer.link_activity_equipment(
                "a1",
                "sheet:equipment:1",
                source="sheet",
                source_record_id=self.sheet_source,
            )
        )

        self.writer.link_activity_equipment(
            "a1",
            "sheet:equipment:1",
            source="manual",
            is_manual=True,
        )
        self.writer.upsert_equipment("sheet:equipment:2", type="shoe", name="Other")
        self.assertFalse(
            self.writer.link_activity_equipment(
                "a1",
                "sheet:equipment:2",
                source="sheet",
            )
        )

        self.assertEqual(
            [("sheet:equipment:1", "primary", "manual", 1)],
            [tuple(row) for row in self._links()],
        )

    def test_first_source_keeps_the_link(self):
        self._equipment()
        self.writer.upsert_equipment("sheet:equipment:2", type="shoe", name="Other")

        self.writer.link_activity_equipment(
            "a1", "sheet:equipment:1", source="sheet"
        )
        self.assertFalse(
            self.writer.link_activity_equipment(
                "a1", "sheet:equipment:2", source="fit"
            )
        )

        self.assertEqual(
            [("sheet:equipment:1", "primary", "sheet", 0)],
            [tuple(row) for row in self._links()],
        )

    def test_same_source_can_repoint_the_link(self):
        self._equipment()
        self.writer.upsert_equipment("sheet:equipment:2", type="shoe", name="Other")

        self.writer.link_activity_equipment(
            "a1", "sheet:equipment:1", source="sheet"
        )
        self.assertTrue(
            self.writer.link_activity_equipment(
                "a1", "sheet:equipment:2", source="sheet"
            )
        )

        self.assertEqual(
            [("sheet:equipment:2", "primary", "sheet", 0)],
            [tuple(row) for row in self._links()],
        )

    def test_link_rejects_unknown_rows(self):
        with self.assertRaises(ValueError):
            self.writer.link_activity_equipment(
                "a1", "missing", source="sheet"
            )
        self._equipment()
        with self.assertRaises(ValueError):
            self.writer.link_activity_equipment(
                "missing", "sheet:equipment:1", source="sheet"
            )
        with self.assertRaises(ValueError):
            self.writer.upsert_equipment("", type="shoe", name="x")




class RaceResultTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-04-12', 'run')"
        )
        self.conn.commit()

    def _row(self):
        return self.conn.execute(
            "SELECT official_distance_m, official_time_s, place_total, "
            "status, source FROM race_results WHERE activity_id = 'a1'"
        ).fetchone()

    def test_inserts_and_replaces(self):
        self.writer.upsert_race_result(
            "a1",
            source="manual",
            official_time_s=9600.0,
            status="completed",
        )
        self.writer.upsert_race_result(
            "a1",
            source="manual",
            official_distance_m=42195.0,
            official_time_s=9469.0,
        )

        row = self._row()
        self.assertAlmostEqual(42195.0, row["official_distance_m"])
        self.assertAlmostEqual(9469.0, row["official_time_s"])

    def test_a_manual_row_is_not_overwritten_by_a_source(self):
        self.writer.upsert_race_result(
            "a1",
            source="manual",
            official_time_s=9469.0,
        )

        written = self.writer.upsert_race_result(
            "a1",
            source="runalyze",
            official_time_s=9500.0,
        )

        self.assertFalse(written)
        self.assertAlmostEqual(9469.0, self._row()["official_time_s"])
        self.assertEqual("manual", self._row()["source"])

    def test_an_empty_payload_writes_nothing(self):
        self.assertFalse(
            self.writer.upsert_race_result("a1", source="manual")
        )
        self.assertIsNone(self._row())


class FitScanManifestTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)

    def test_records_and_reads_the_manifest(self):
        self.writer.record_fit_scan_file(
            path="/fit/a.fit",
            size_bytes=1024,
            mtime_ns=111,
            kind="activity",
        )
        self.writer.record_fit_scan_file(
            path="/fit/b.fit",
            size_bytes=2048,
            mtime_ns=222,
            kind="other",
        )

        self.assertEqual(
            {
                "/fit/a.fit": (1024, 111, "activity"),
                "/fit/b.fit": (2048, 222, "other"),
            },
            self.writer.fit_scan_manifest(),
        )

    def test_re_recording_updates_size_and_mtime(self):
        self.writer.record_fit_scan_file(
            path="/fit/a.fit",
            size_bytes=1024,
            mtime_ns=111,
            kind="other",
        )
        self.writer.record_fit_scan_file(
            path="/fit/a.fit",
            size_bytes=4096,
            mtime_ns=999,
            kind="activity",
        )

        self.assertEqual(
            {"/fit/a.fit": (4096, 999, "activity")},
            self.writer.fit_scan_manifest(),
        )

    def test_forget_drops_missing_files(self):
        for name in ("a", "b", "c"):
            self.writer.record_fit_scan_file(
                path=f"/fit/{name}.fit",
                size_bytes=1,
                mtime_ns=1,
                kind="other",
            )

        removed = self.writer.forget_fit_scan_files(["/fit/b.fit"])

        self.assertEqual(1, removed)
        self.assertEqual(
            ["/fit/a.fit", "/fit/c.fit"],
            sorted(self.writer.fit_scan_manifest()),
        )
        self.assertEqual(0, self.writer.forget_fit_scan_files([]))

    def test_rejects_an_empty_path(self):
        with self.assertRaises(ValueError):
            self.writer.record_fit_scan_file(
                path="",
                size_bytes=1,
                mtime_ns=1,
                kind="other",
            )


class ActivitySocialTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.writer.upsert_activity(
            "a1",
            {"local_date": "2026-10-01", "sport": "run"},
            source="intervals",
            source_record_id=None,
        )

    def test_upsert_creates_and_refreshes_one_source_row(self):
        created = self.writer.upsert_activity_social(
            "a1",
            source="strava",
            title="Bakery run",
            description="Race you to the bakery",
            external_id="123",
            url="https://www.strava.com/activities/123",
        )
        self.assertTrue(created)

        refreshed = self.writer.upsert_activity_social(
            "a1",
            source="strava",
            title="Bakery run 2",
            description="",
            external_id="123",
            url="https://www.strava.com/activities/123",
        )
        self.assertFalse(refreshed)

        rows = self.conn.execute(
            "SELECT source, title, description FROM activity_social "
            "WHERE activity_id = 'a1'"
        ).fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual("strava", rows[0]["source"])
        self.assertEqual("Bakery run 2", rows[0]["title"])
        self.assertEqual("", rows[0]["description"])

    def test_sources_have_independent_rows(self):
        self.writer.upsert_activity_social(
            "a1", source="strava", title="Strava title"
        )
        self.writer.upsert_activity_social(
            "a1", source="runalyze", title="Runalyze title"
        )

        rows = self.conn.execute(
            "SELECT source, title FROM activity_social "
            "WHERE activity_id = 'a1' ORDER BY source"
        ).fetchall()
        self.assertEqual(
            [("runalyze", "Runalyze title"), ("strava", "Strava title")],
            [(row["source"], row["title"]) for row in rows],
        )

    def test_a_manual_row_is_never_overwritten_by_an_import(self):
        self.writer.upsert_activity_social(
            "a1",
            source="manual",
            title="My title",
            is_manual=True,
        )

        changed = self.writer.upsert_activity_social(
            "a1",
            source="manual",
            title="Import title",
        )
        self.assertFalse(changed)
        row = self.conn.execute(
            "SELECT title FROM activity_social "
            "WHERE activity_id = 'a1' AND source = 'manual'"
        ).fetchone()
        self.assertEqual("My title", row["title"])

    def test_unknown_activity_is_rejected(self):
        with self.assertRaises(ValueError):
            self.writer.upsert_activity_social("nope", source="strava")

    def test_excluded_activity_is_rejected(self):
        self.writer.exclude_activity("a1")
        with self.assertRaises(ValueError):
            self.writer.upsert_activity_social("a1", source="strava")


class ManualFieldTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.fit_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="f1",
            checksum="c-f1",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "distance_m": 10000.0,
                "duration_s": 3600.0,
            },
            source="fit",
            source_record_id=self.fit_id,
        )
        self.conn.commit()

    def _field(self, field="distance_m"):
        return self.conn.execute(
            f"SELECT {field} FROM activities WHERE id = 'a1'"
        ).fetchone()[0]

    def _pointer(self, field="distance_m"):
        return self.conn.execute(
            """
            SELECT source, is_manual FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = ?
            """,
            (field,),
        ).fetchone()

    def _input(self, field="distance_m"):
        return self.conn.execute(
            """
            SELECT value_json, owner_source FROM activity_manual_fields
            WHERE activity_id = 'a1' AND field_name = ?
            """,
            (field,),
        ).fetchone()

    def test_set_records_the_input_and_keeps_the_source_pointer(self):
        self.writer.set_manual_field("a1", "distance_m", 8000.0)

        self.assertEqual(8000.0, self._field())
        row = self._input()
        self.assertEqual("8000.0", row["value_json"])
        self.assertIsNone(row["owner_source"])

        pointer = self._pointer()
        self.assertEqual("fit", pointer["source"])
        self.assertEqual(1, pointer["is_manual"])

    def test_clear_restores_the_source_snapshot(self):
        self.writer.set_manual_field("a1", "distance_m", 8000.0)

        self.writer.clear_manual_field("a1", "distance_m")

        self.assertEqual(10000.0, self._field())
        self.assertIsNone(self._input())
        pointer = self._pointer()
        self.assertEqual("fit", pointer["source"])
        self.assertEqual(0, pointer["is_manual"])

    def test_clear_without_a_source_uses_the_column_default(self):
        self.conn.execute(
            "DELETE FROM activity_field_sources "
            "WHERE activity_id = 'a1' AND field_name = 'distance_m'"
        )
        self.writer.set_manual_field("a1", "distance_m", 8000.0)

        self.writer.clear_manual_field("a1", "distance_m")

        self.assertEqual(0.0, self._field())
        self.assertIsNone(self._pointer())

    def test_a_manual_value_survives_a_reimport(self):
        self.writer.set_manual_field("a1", "distance_m", 8000.0)

        self.writer.upsert_activity(
            "a1",
            {"distance_m": 12000.0},
            source="intervals",
            source_record_id=self.fit_id,
        )

        self.assertEqual(8000.0, self._field())

    def test_an_owner_patch_blocks_another_source(self):
        self.writer.set_manual_owner("a1", "distance_m", "fit")

        self.writer.upsert_activity(
            "a1",
            {"distance_m": 12000.0},
            source="intervals",
            source_record_id=self.fit_id,
        )

        self.assertEqual(10000.0, self._field())
        self.assertEqual("fit", self._pointer()["source"])

    def test_clearing_an_owner_patch_keeps_the_value(self):
        self.writer.set_manual_owner("a1", "distance_m", "fit")

        self.assertTrue(self.writer.clear_manual_field("a1", "distance_m"))

        self.assertEqual(10000.0, self._field())
        self.assertIsNone(self._input())


if __name__ == "__main__":
    unittest.main()
