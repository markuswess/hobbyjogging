import sqlite3
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import SCHEMA_VERSION, connect, migrate, open_database
from hobbyjogging_core.db.schema import INITIAL_SCHEMA_SQL


EXPECTED_TABLES = {
    "activities",
    "activity_equipment",
    "activity_field_sources",
    "activity_intervals",
    "activity_laps",
    "activity_sources",
    "activity_tags",
    "activity_zone_times",
    "equipment",
    "equipment_source_links",
    "events",
    "import_runs",
    "source_records",
    "wellness_days",
    "zone_configs",
}


class SchemaMigrationTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)

    def test_migrate_creates_schema_and_sets_version(self):
        version = migrate(self.conn)

        self.assertEqual(SCHEMA_VERSION, version)
        self.assertEqual(
            SCHEMA_VERSION,
            self.conn.execute("PRAGMA user_version").fetchone()[0],
        )

        tables = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertTrue(EXPECTED_TABLES.issubset(tables))

        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(activities)")
        }
        self.assertIn("elapsed_s", columns)
        self.assertIn("excluded_at", columns)
        self.assertIn("vo2max_garmin", columns)
        self.assertIn("vo2max_runalyze", columns)

        record_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(source_records)")
        }
        self.assertIn("excluded_at", record_columns)

        tag_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(activity_tags)")
        }
        self.assertEqual(
            {
                "activity_id",
                "tag",
                "source",
                "source_record_id",
                "is_manual",
                "created_at",
            },
            tag_columns,
        )

    def test_migrates_v1_activity_rows_to_elapsed_time(self):
        self.conn.executescript(INITIAL_SCHEMA_SQL)
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        self.conn.execute("PRAGMA user_version = 1")
        self.conn.commit()

        version = migrate(self.conn)
        row = self.conn.execute(
            "SELECT elapsed_s FROM activities WHERE id = 'a1'"
        ).fetchone()

        self.assertEqual(SCHEMA_VERSION, version)
        self.assertEqual(0, row["elapsed_s"])

    def test_migrates_v4_database_to_v5(self):
        from hobbyjogging_core.db.migrations import MIGRATIONS

        self.conn.executescript(INITIAL_SCHEMA_SQL)
        for version in (2, 3, 4):
            self.conn.executescript(MIGRATIONS[version])
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        self.conn.execute("PRAGMA user_version = 4")
        self.conn.commit()

        version = migrate(self.conn)

        self.assertEqual(SCHEMA_VERSION, version)
        row = self.conn.execute(
            "SELECT vo2max_garmin, vo2max_runalyze FROM activities "
            "WHERE id = 'a1'"
        ).fetchone()
        self.assertIsNone(row["vo2max_garmin"])
        self.assertIsNone(row["vo2max_runalyze"])
        self.conn.execute(
            "INSERT INTO activity_tags (activity_id, tag, source) "
            "VALUES ('a1', 'race', 'manual')"
        )
        self.assertEqual(
            1,
            self.conn.execute("SELECT COUNT(*) FROM activity_tags").fetchone()[0],
        )

    def test_migrate_is_idempotent(self):
        migrate(self.conn)
        version = migrate(self.conn)

        self.assertEqual(SCHEMA_VERSION, version)

    def test_foreign_keys_are_enabled(self):
        self.assertEqual(
            1,
            self.conn.execute("PRAGMA foreign_keys").fetchone()[0],
        )

    def test_equipment_usage_view_aggregates_primary_links(self):
        migrate(self.conn)
        self.conn.execute(
            "INSERT INTO equipment (id, type, name, target_distance_m) "
            "VALUES ('shoe-1', 'shoe', 'Pegasus 40', 800000)"
        )
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport, distance_m, duration_s) "
            "VALUES ('a1', '2026-10-01', 'run', 10000, 3600)"
        )
        self.conn.execute(
            "INSERT INTO activity_equipment (activity_id, equipment_id) "
            "VALUES ('a1', 'shoe-1')"
        )

        usage = self.conn.execute(
            "SELECT * FROM equipment_usage WHERE equipment_id = 'shoe-1'"
        ).fetchone()

        self.assertEqual(1, usage["activity_count"])
        self.assertEqual(10000, usage["distance_m"])
        self.assertEqual(3600, usage["duration_s"])
        self.assertEqual("2026-10-01", usage["first_used_on"])
        self.assertEqual("2026-10-01", usage["last_used_on"])

    def test_source_records_are_unique_per_source_type_and_external_id(self):
        migrate(self.conn)
        values = ("intervals", "activity", "i123", "checksum")

        self.conn.execute(
            "INSERT INTO source_records (source, record_type, external_id, checksum) "
            "VALUES (?, ?, ?, ?)",
            values,
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO source_records "
                "(source, record_type, external_id, checksum) "
                "VALUES (?, ?, ?, ?)",
                values,
            )

    def test_cascades_activity_children(self):
        migrate(self.conn)
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        self.conn.execute(
            "INSERT INTO activity_laps (activity_id, lap_index) VALUES ('a1', 1)"
        )
        self.conn.execute("DELETE FROM activities WHERE id = 'a1'")

        count = self.conn.execute(
            "SELECT COUNT(*) FROM activity_laps"
        ).fetchone()[0]
        self.assertEqual(0, count)

    def test_activity_equipment_allows_only_one_primary_item(self):
        migrate(self.conn)
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        self.conn.execute(
            "INSERT INTO equipment (id, type, name) VALUES "
            "('shoe-1', 'shoe', 'Pegasus 40'), "
            "('shoe-2', 'shoe', 'Boston 12')"
        )
        self.conn.execute(
            "INSERT INTO activity_equipment (activity_id, equipment_id) "
            "VALUES ('a1', 'shoe-1')"
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO activity_equipment (activity_id, equipment_id) "
                "VALUES ('a1', 'shoe-2')"
            )

    def test_manual_field_source_can_have_no_source_record(self):
        migrate(self.conn)
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) "
            "VALUES ('a1', '2026-10-01', 'run')"
        )
        self.conn.execute(
            "INSERT INTO activity_field_sources "
            "(activity_id, field_name, source, is_manual) "
            "VALUES ('a1', 'training_load', 'manual', 1)"
        )

        count = self.conn.execute(
            "SELECT COUNT(*) FROM activity_field_sources"
        ).fetchone()[0]
        self.assertEqual(1, count)

    def test_migrate_rejects_newer_schema(self):
        self.conn.execute("PRAGMA user_version = 999")
        self.conn.commit()

        with self.assertRaises(RuntimeError):
            migrate(self.conn)

    def test_open_database_creates_parent_directory_and_migrates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "training.db"
            conn = open_database(path)
            self.addCleanup(conn.close)

            self.assertTrue(path.exists())
            self.assertEqual(
                SCHEMA_VERSION,
                conn.execute("PRAGMA user_version").fetchone()[0],
            )


if __name__ == "__main__":
    unittest.main()
