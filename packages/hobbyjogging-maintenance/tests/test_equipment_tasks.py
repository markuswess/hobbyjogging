import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "drop_ride_shoe_links_v1"


class DropRideShoeLinksTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.writer.upsert_equipment(
            "shoe",
            type="shoe",
            name="Lunge Fis",
        )
        self.writer.upsert_equipment(
            "bike",
            type="bike",
            name="Mery",
        )
        self._activity("ride1", "ride")
        self._activity("ride2", "mtb_ride")
        self._activity("hike", "hike")
        self._activity("run", "run")
        self.conn.commit()

    def _activity(self, activity_id, sport):
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": "2020-08-07",
                "sport": sport,
                "distance_m": 10000,
                "duration_s": 3600,
            },
            source="fit",
            source_record_id=None,
        )

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _rows(self):
        return {
            row["activity_id"]
            for row in self.conn.execute(
                "SELECT activity_id FROM activity_equipment"
            )
        }

    def test_removes_source_shoes_from_rides_only(self):
        self.writer.link_activity_equipment(
            "ride1", "bike", source="fit"
        )
        self.writer.link_activity_equipment(
            "ride1", "shoe", source="sheet", role="secondary"
        )
        self.writer.link_activity_equipment(
            "ride2", "shoe", source="sheet"
        )
        self.writer.link_activity_equipment(
            "hike", "shoe", source="sheet"
        )
        self.writer.link_activity_equipment(
            "run", "shoe", source="sheet"
        )
        self.conn.commit()

        result = self._run()

        self.assertEqual(2, result.counts["rides"])
        self.assertEqual(2, result.counts["removed"])
        links = {
            (row["activity_id"], row["equipment_id"], row["source"])
            for row in self.conn.execute(
                "SELECT activity_id, equipment_id, source "
                "FROM activity_equipment"
            )
        }
        self.assertEqual(
            {
                ("ride1", "bike", "fit"),
                ("hike", "shoe", "sheet"),
                ("run", "shoe", "sheet"),
            },
            links,
        )

    def test_a_manual_shoe_link_survives(self):
        self.writer.link_activity_equipment(
            "ride2", "shoe", source="sheet"
        )
        self.writer.link_activity_equipment(
            "ride2", "shoe", source="manual", role="secondary", is_manual=True
        )
        self.conn.commit()

        self._run()

        rows = self.conn.execute(
            """
            SELECT equipment_id, source, is_manual
            FROM activity_equipment
            WHERE activity_id = 'ride2'
            """
        ).fetchall()
        self.assertEqual(
            [("shoe", "manual", 1)],
            [tuple(row) for row in rows],
        )

    def test_a_dry_run_removes_nothing(self):
        self.writer.link_activity_equipment(
            "ride2", "shoe", source="sheet"
        )
        self.conn.commit()

        result = self._run(dry_run=True)

        self.assertEqual(1, result.counts["rides"])
        self.assertIn("ride2", self._rows())

    def test_a_forced_rerun_is_a_no_op(self):
        self.writer.link_activity_equipment(
            "ride2", "shoe", source="sheet"
        )
        self.conn.commit()
        self._run()

        again = self._run(force=True)

        self.assertEqual(0, again.counts.get("rides", 0))
        self.assertNotIn("ride2", self._rows())


if __name__ == "__main__":
    unittest.main()
