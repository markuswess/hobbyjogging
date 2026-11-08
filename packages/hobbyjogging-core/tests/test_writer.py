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
        self.assertEqual("manual", sources["duration_s"])
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
        self.assertEqual("manual", source["source"])
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


if __name__ == "__main__":
    unittest.main()
