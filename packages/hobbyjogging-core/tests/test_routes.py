import unittest
from datetime import date

from hobbyjogging_core import TrainingRepository, TrainingWriter, connect, migrate


class RouteAndLinkTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.repository = TrainingRepository(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.conn.executemany(
            "INSERT INTO activities (id, local_date, sport) VALUES (?, ?, ?)",
            [
                ("a1", "2026-10-01", "run"),
                ("a2", "2026-10-02", "run"),
            ],
        )

    def _route(self, route_id="sheet:route:16", *, source="sheet", name="Loop"):
        self.writer.upsert_route(
            route_id,
            name=name,
            source=source,
            external_ref=route_id.rsplit(":", 1)[-1],
            distance_m=8000,
        )

    def test_an_activity_carries_its_routes(self):
        self._route()
        self.writer.replace_activity_routes(
            "a1",
            ["sheet:route:16"],
            source="sheet",
        )

        activity = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )[0]

        self.assertEqual(["sheet:route:16"], [route.id for route in activity.routes])
        self.assertEqual("Loop", activity.routes[0].name)

    def test_routes_are_listed(self):
        self._route()
        self._route("sheet:route:17", name="Other")

        self.assertEqual(
            ["sheet:route:16", "sheet:route:17"],
            [route.id for route in self.repository.routes()],
        )

    def test_reimport_replaces_only_its_own_links(self):
        self._route()
        self.writer.replace_activity_routes(
            "a1", ["sheet:route:16"], source="sheet"
        )
        self.writer.replace_activity_routes(
            "a1", ["sheet:route:16"], source="manual", is_manual=True
        )

        self.writer.replace_activity_routes("a1", [], source="sheet")

        routes = self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )[0].routes
        self.assertEqual(["sheet:route:16"], [route.id for route in routes])

    def test_a_manual_route_is_not_overwritten_by_a_source(self):
        self._route(source="manual", name="My loop")

        self.writer.upsert_route(
            "sheet:route:16",
            name="Sheet loop",
            source="sheet",
            external_ref="16",
        )

        self.assertEqual("My loop", self.repository.routes()[0].name)

    def test_an_unknown_route_is_rejected(self):
        with self.assertRaises(ValueError):
            self.writer.replace_activity_routes(
                "a1", ["sheet:route:99"], source="sheet"
            )

    def _event(self):
        record_id = self.writer.upsert_source_record(
            source="intervals",
            record_type="event",
            external_id="e1",
            checksum="c1",
            import_run_id=self.run_id,
        )
        self.writer.upsert_event(
            event_id="e1",
            local_date="2026-10-01",
            name="Town race",
            type="run",
            source_record_id=record_id,
        )
        return record_id

    def test_event_links_are_stored_and_listed(self):
        self._event()

        self.writer.replace_event_activity_links(
            "e1", ["a1"], confidence=0.98
        )

        links = self.repository.event_activity_links()
        self.assertEqual(1, len(links))
        self.assertEqual("e1", links[0].event_id)
        self.assertEqual("a1", links[0].activity_id)
        self.assertAlmostEqual(0.98, links[0].confidence)
        self.assertFalse(links[0].is_manual)

    def test_replacing_auto_links_keeps_manual_ones(self):
        self._event()
        self.writer.replace_event_activity_links("e1", ["a1"])
        self.conn.execute(
            "INSERT INTO event_activity_links (event_id, activity_id, "
            "is_manual) VALUES ('e1', 'a2', 1)"
        )

        self.writer.replace_event_activity_links("e1", [])

        links = self.repository.event_activity_links()
        self.assertEqual(["a2"], [link.activity_id for link in links])
        self.assertTrue(links[0].is_manual)


if __name__ == "__main__":
    unittest.main()
