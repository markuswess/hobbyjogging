import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task
from hobbyjogging_import.tag_lexicon import place_names_for

TASK = "routes_from_place_tags_v1"


class PlaceRouteTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _activity(self, *, tags=(), excluded=False):
        self.counter += 1
        activity_id = f"p{self.counter}"
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "Run",
                "duration_s": 3600,
            },
            source="fit",
            source_record_id=None,
        )
        if tags:
            self.writer.replace_activity_tags(
                activity_id, list(tags), source="runalyze"
            )
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _links(self, activity_id):
        return [
            (row["route_id"], row["source"], row["is_manual"])
            for row in self.conn.execute(
                """
                SELECT route_id, source, is_manual
                FROM activity_routes WHERE activity_id = ?
                ORDER BY route_id
                """,
                (activity_id,),
            )
        ]

    def test_place_names_normalize_aliases(self):
        self.assertEqual(
            ["Donaukanal"],
            place_names_for(["kanal", "donaukanal"]),
        )
        self.assertEqual(
            ["Wienerberg"],
            place_names_for(["Wienerberg", "Wienerbergteich"]),
        )

    def test_a_place_tag_creates_and_links_a_route(self):
        activity_id = self._activity(tags=["kanal"])

        result = self._run()

        self.assertEqual(1, result.counts["tagged"])
        self.assertEqual(1, result.counts["routes_created"])
        self.assertEqual(1, result.counts["linked"])
        self.assertEqual(
            [("runalyze:tag:donaukanal", "tag", 0)],
            self._links(activity_id),
        )
        route = self.conn.execute(
            "SELECT name, source FROM routes WHERE id = ?",
            ("runalyze:tag:donaukanal",),
        ).fetchone()
        self.assertEqual(("Donaukanal", "tag"), tuple(route))

    def test_two_aliases_share_one_route(self):
        first = self._activity(tags=["kanal"])
        second = self._activity(tags=["donaukanal"])

        self._run()

        self.assertEqual(
            ["runalyze:tag:donaukanal"],
            [row[0] for row in self._links(first)],
        )
        self.assertEqual(
            ["runalyze:tag:donaukanal"],
            [row[0] for row in self._links(second)],
        )
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM routes WHERE name = 'Donaukanal'"
            ).fetchone()[0],
        )

    def test_a_manual_route_wins(self):
        activity_id = self._activity(tags=["Prater"])
        self.writer.upsert_route(
            "manual:route:prater",
            name="My Prater loop",
            source="manual",
        )
        self.writer.replace_activity_routes(
            activity_id,
            ["manual:route:prater"],
            source="manual",
            is_manual=True,
        )
        self.conn.commit()

        result = self._run()

        self.assertEqual(1, result.counts["already"])
        self.assertEqual(
            [("manual:route:prater", "manual", 1)],
            self._links(activity_id),
        )

    def test_a_sheet_route_wins(self):
        activity_id = self._activity(tags=["Prater"])
        self.writer.upsert_route(
            "sheet:route:prater",
            name="Historical Prater",
            source="sheet",
        )
        self.writer.replace_activity_routes(
            activity_id,
            ["sheet:route:prater"],
            source="sheet",
        )
        self.conn.commit()

        self._run()

        self.assertEqual(
            [("sheet:route:prater", "sheet", 0)],
            self._links(activity_id),
        )

    def test_an_excluded_activity_is_skipped(self):
        self._activity(tags=["Prater"], excluded=True)

        result = self._run()

        self.assertEqual(0, result.counts.get("tagged", 0))

    def test_a_second_run_is_a_no_op(self):
        activity_id = self._activity(tags=["Prater"])
        self._run()

        again = self._run(force=True)

        self.assertEqual(0, again.counts.get("linked", 0))
        self.assertEqual(1, again.counts["already"])
        self.assertEqual(
            [("runalyze:tag:prater", "tag", 0)],
            self._links(activity_id),
        )


if __name__ == "__main__":
    unittest.main()
