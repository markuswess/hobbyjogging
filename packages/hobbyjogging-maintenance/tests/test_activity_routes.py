import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "activity_routes_v1"


class ActivityRoutesTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

    def _activity(self, activity_id, day, values, *, source="sheet"):
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=activity_id,
            checksum=f"c-{activity_id}",
            import_run_id=self.run_id,
            payload_json=json.dumps({"values": values}),
        )
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": day,
                "sport": "run",
                "distance_m": 8000,
                "duration_s": 2400,
            },
            source=source,
            source_record_id=record_id,
        )
        self.writer.link_activity_source(
            activity_id, record_id, match_method="test"
        )
        self.conn.commit()
        return record_id

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _routes(self, activity_id):
        return [
            row["route_id"]
            for row in self.conn.execute(
                "SELECT route_id FROM activity_routes "
                "WHERE activity_id = ? ORDER BY route_id",
                (activity_id,),
            )
        ]

    def test_a_numbered_row_becomes_a_route(self):
        self._activity(
            "a1",
            "2019-01-23",
            {"Strecke": "Wienerberg 8er", "Streckennummer": 25.0},
        )

        result = self._run()

        self.assertEqual(1, result.counts["linked"])
        self.assertEqual(["sheet:route:25"], self._routes("a1"))
        route = self.conn.execute(
            "SELECT name, external_ref, source FROM routes"
        ).fetchone()
        self.assertEqual("Wienerberg 8er", route["name"])
        self.assertEqual("25", route["external_ref"])
        self.assertEqual("sheet", route["source"])

    def test_a_name_only_row_reuses_the_number_seen_for_it(self):
        self._activity(
            "a1",
            "2019-01-23",
            {"Strecke": "Kaserne", "Streckennummer": 6.0},
        )
        self._activity("a2", "2019-01-24", {"Strecke": "Kaserne"})

        self._run()

        self.assertEqual(["sheet:route:6"], self._routes("a1"))
        self.assertEqual(["sheet:route:6"], self._routes("a2"))

    def test_a_url_is_skipped(self):
        self._activity(
            "a1",
            "2019-01-23",
            {"Strecke": "http://www.gmap-pedometer.com/?r=6722376"},
        )

        result = self._run()

        self.assertEqual(1, result.counts["skipped"])
        self.assertEqual([], self._routes("a1"))

    def test_a_manual_link_survives(self):
        self._activity(
            "a1",
            "2019-01-23",
            {"Strecke": "Wienerberg 8er", "Streckennummer": 25.0},
        )
        self.writer.upsert_route(
            "manual:route:1", name="Mine", source="manual"
        )
        self.writer.replace_activity_routes(
            "a1", ["manual:route:1"], source="manual", is_manual=True
        )

        self._run()

        self.assertEqual(
            ["manual:route:1", "sheet:route:25"], self._routes("a1")
        )

    def test_a_forced_rerun_is_a_no_op(self):
        self._activity(
            "a1",
            "2019-01-23",
            {"Strecke": "Wienerberg 8er", "Streckennummer": 25.0},
        )

        self._run()
        result = self._run(force=True)

        self.assertEqual(0, result.counts["linked"])
        self.assertEqual(1, result.counts["unchanged"])

    def test_a_dry_run_writes_nothing(self):
        self._activity(
            "a1",
            "2019-01-23",
            {"Strecke": "Wienerberg 8er", "Streckennummer": 25.0},
        )

        self._run(dry_run=True)

        self.assertEqual([], self._routes("a1"))
        self.assertEqual(
            0, self.conn.execute("SELECT COUNT(*) FROM routes").fetchone()[0]
        )


if __name__ == "__main__":
    unittest.main()
