import tempfile
import unittest
from datetime import date
from pathlib import Path

from hobbyjogging_core import SCHEMA_VERSION, connect, migrate
from hobbyjogging_report.sources.database import DatabaseSource


class DatabaseSourceTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self._seed()
        self.source = DatabaseSource(connection=self.conn)

    def _seed(self):
        self.conn.execute(
            "INSERT INTO activities "
            "(id, local_date, sport, name, duration_s, distance_m) "
            "VALUES ('a1', '2026-10-01', 'run', 'Morning run', 3600, 10000)"
        )
        self.conn.execute(
            "INSERT INTO equipment (id, type, name) "
            "VALUES ('shoe-1', 'shoe', 'Pegasus 40')"
        )
        self.conn.execute(
            "INSERT INTO activity_equipment (activity_id, equipment_id) "
            "VALUES ('a1', 'shoe-1')"
        )
        self.conn.execute(
            "INSERT INTO activity_intervals "
            "(activity_id, interval_index, type, duration_s) "
            "VALUES ('a1', 1, 'WORK', 60)"
        )
        self.conn.execute(
            "INSERT INTO wellness_days (local_date, hrv) "
            "VALUES ('2026-10-01', 60)"
        )
        self.conn.execute(
            "INSERT INTO events (id, local_date, name) "
            "VALUES ('e1', '2026-10-02', 'Town race')"
        )

    def test_activities_delegate_to_repository(self):
        activities = self.source.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )

        self.assertEqual(1, len(activities))
        self.assertEqual("a1", activities[0].id)
        self.assertEqual("shoe-1", activities[0].equipment[0].id)

    def test_other_queries_delegate_to_repository(self):
        wellness = self.source.wellness(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )
        events = self.source.events(
            date(2026, 10, 2),
            date(2026, 10, 2),
        )
        intervals = self.source.activity_intervals("a1")
        equipment = self.source.equipment()

        self.assertEqual(60, wellness[0].hrv)
        self.assertEqual("Town race", events[0].name)
        self.assertEqual("WORK", intervals[0].type)
        self.assertEqual("Pegasus 40", equipment[0].name)

    def test_earliest_activity_date(self):
        self.assertEqual(
            date(2026, 10, 1),
            self.source.earliest_activity_date(),
        )

    def test_earliest_activity_date_is_none_without_activities(self):
        self.conn.execute("DELETE FROM activities")

        self.assertIsNone(self.source.earliest_activity_date())

    def test_close_does_not_close_external_connection(self):
        self.source.close()

        self.assertEqual(
            1,
            self.conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0],
        )

    def test_path_opens_and_migrates_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "training.db"
            source = DatabaseSource(path=path)
            self.addCleanup(source.close)

            self.assertTrue(path.exists())
            self.assertEqual(
                SCHEMA_VERSION,
                source.connection.execute("PRAGMA user_version").fetchone()[0],
            )


if __name__ == "__main__":
    unittest.main()
