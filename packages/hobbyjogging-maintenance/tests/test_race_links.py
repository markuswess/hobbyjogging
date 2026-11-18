import json
import unittest
from datetime import date

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.context import Scope
from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "race_links_current"


class RaceLinksTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

    def _event(
        self,
        event_id="e1",
        *,
        day="2026-04-12",
        distance=42190.0,
        sport="run",
        name="Linz Marathon",
    ):
        record_id = self.writer.upsert_source_record(
            source="intervals",
            record_type="event",
            external_id=event_id,
            checksum=f"c-{event_id}",
            import_run_id=self.run_id,
            payload_json=json.dumps({"category": "RACE_A"}),
        )
        self.writer.upsert_event(
            event_id=event_id,
            local_date=day,
            name=name,
            type=sport,
            distance_m=distance,
            source_record_id=record_id,
        )
        self.writer.replace_event_workout_methods(
            event_id, ["race"], source="intervals"
        )
        self.conn.commit()
        return record_id

    def _activity(
        self,
        activity_id,
        *,
        day="2026-04-12",
        distance=42450.58,
        sport="run",
        name="Linz Running",
        started_at="2026-04-12T07:30:02Z",
    ):
        record_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id=activity_id,
            checksum=f"c-{activity_id}",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": day,
                "started_at_utc": started_at,
                "sport": sport,
                "name": name,
                "distance_m": distance,
                "duration_s": 9469,
            },
            source="fit",
            source_record_id=record_id,
        )
        self.conn.commit()
        return activity_id

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _result(self, activity_id, *, source="runalyze"):
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="race_result",
            external_id=f"r-{activity_id}",
            checksum=f"rc-{activity_id}",
            import_run_id=self.run_id,
        )
        self.writer.upsert_race_result(
            activity_id,
            source=source,
            source_record_id=record_id,
            name="Official race",
            official_distance_m=10000.0,
            official_time_s=3000.0,
        )
        self.conn.commit()
        return record_id

    def _links(self):
        return [
            (row["event_id"], row["activity_id"], row["is_manual"])
            for row in self.conn.execute(
                "SELECT event_id, activity_id, is_manual "
                "FROM event_activity_links ORDER BY event_id, activity_id"
            )
        ]

    def _methods(self, activity_id):
        return [
            (row["method"], row["source"])
            for row in self.conn.execute(
                "SELECT method, source FROM activity_workout_methods "
                "WHERE activity_id = ? ORDER BY method",
                (activity_id,),
            )
        ]

    def test_links_a_race_within_five_percent(self):
        self._event()
        self._activity("a1")

        result = self._run()

        self.assertEqual(1, result.counts["linked"])
        self.assertEqual([("e1", "a1", 0)], self._links())
        self.assertEqual([("race", "race_link")], self._methods("a1"))

        link = self.conn.execute(
            "SELECT match_method, confidence FROM event_activity_links"
        ).fetchone()
        self.assertEqual("auto", link["match_method"])
        self.assertGreater(link["confidence"], 0.99)

    def test_a_distance_beyond_the_tolerance_does_not_link(self):
        self._event(distance=10000.0)
        self._activity("a1", distance=10600.0)

        result = self._run()

        self.assertEqual(0, result.counts["linked"])
        self.assertEqual([], self._links())

    def test_a_different_sport_does_not_link(self):
        self._event()
        self._activity("a1", sport="ride")

        self._run()

        self.assertEqual([], self._links())

    def test_two_candidates_open_an_ambiguous_race_item(self):
        self._event(distance=10000.0)
        self._activity("a1", distance=10000.0)
        self._activity(
            "a2", distance=10100.0, started_at="2026-04-12T09:00:00Z"
        )

        result = self._run()

        self.assertEqual(1, result.counts["ambiguous"])
        self.assertEqual([], self._links())
        item = self.conn.execute(
            "SELECT category, context_json FROM review_items"
        ).fetchone()
        self.assertEqual("ambiguous_race", item["category"])
        self.assertEqual(
            2, len(json.loads(item["context_json"])["candidates"])
        )

    def test_manual_methods_are_not_touched(self):
        self._event()
        self._activity("a1")
        self.writer.replace_activity_workout_methods(
            "a1", ["long_run"], source="manual", is_manual=True
        )

        self._run()

        self.assertEqual([("long_run", "manual")], self._methods("a1"))

    def test_a_manual_link_is_kept_and_still_gets_the_method(self):
        self._event()
        self._activity("a1")
        self.conn.execute(
            "INSERT INTO event_activity_links "
            "(event_id, activity_id, is_manual) VALUES ('e1', 'a1', 1)"
        )
        self.conn.commit()

        result = self._run()

        self.assertEqual(1, result.counts["skipped"])
        self.assertEqual([("e1", "a1", 1)], self._links())
        self.assertEqual([("race", "race_link")], self._methods("a1"))

    def test_a_forced_rerun_is_a_no_op(self):
        self._event()
        self._activity("a1")

        self._run()
        result = self._run(force=True)

        self.assertEqual(1, result.counts["events"])
        self.assertEqual(1, result.counts["unchanged"])
        self.assertEqual(0, result.counts["methods_added"])
        self.assertEqual([("race", "race_link")], self._methods("a1"))

    def test_a_stale_link_and_method_are_removed(self):
        self._event()
        self._activity("a1")
        self._run()

        self.writer.replace_event_workout_methods("e1", [], source="intervals")
        self.conn.commit()

        result = self._run(force=True)

        self.assertEqual([], self._links())
        self.assertEqual([], self._methods("a1"))

    def test_an_official_result_adds_the_race_method(self):
        self._activity("a1")
        self._result("a1")

        result = self._run()

        self.assertEqual(1, result.counts["results"])
        self.assertEqual(1, result.counts["methods_added"])
        self.assertEqual([("race", "race_link")], self._methods("a1"))

    def test_a_manual_method_beats_an_official_result(self):
        self._activity("a1")
        self._result("a1")
        self.writer.replace_activity_workout_methods(
            "a1", ["long_run"], source="manual", is_manual=True
        )

        self._run()

        self.assertEqual([("long_run", "manual")], self._methods("a1"))

    def test_an_excluded_result_does_not_add_the_method(self):
        self._activity("a1")
        self._result("a1")
        self.conn.execute(
            "UPDATE race_results SET excluded_at = '2026-01-01' "
            "WHERE activity_id = 'a1'"
        )
        self.conn.commit()

        self._run()

        self.assertEqual([], self._methods("a1"))

    def test_a_removed_result_drops_the_derived_method(self):
        self._activity("a1")
        self._result("a1")
        self._run()

        self.conn.execute(
            "UPDATE race_results SET excluded_at = '2026-01-01' "
            "WHERE activity_id = 'a1'"
        )
        self.conn.commit()

        result = self._run(force=True)

        self.assertEqual(1, result.counts["methods_removed"])
        self.assertEqual([], self._methods("a1"))

    def test_an_event_and_a_result_share_one_method(self):
        self._event()
        self._activity("a1")
        self._result("a1")

        self._run()

        self.assertEqual([("race", "race_link")], self._methods("a1"))

    def test_a_dry_run_writes_nothing(self):
        self._event()
        self._activity("a1")

        self._run(dry_run=True)

        self.assertEqual([], self._links())
        self.assertEqual([], self._methods("a1"))

    def test_scope_leaves_other_events_alone(self):
        self._event("e1", day="2026-04-12")
        self._activity("a1", day="2026-04-12")
        self._event(
            "e2", day="2026-05-01", distance=10000.0, name="May race"
        )
        self._activity(
            "a2",
            day="2026-05-01",
            distance=10000.0,
            started_at="2026-05-01T08:00:00Z",
        )
        self._run()

        self.conn.execute(
            "DELETE FROM event_activity_links WHERE event_id = 'e2'"
        )
        self.conn.execute(
            "DELETE FROM activity_workout_methods "
            "WHERE activity_id = 'a2' AND source = 'race_link'"
        )
        self.conn.commit()

        self._run(
            force=True,
            scope=Scope(start=date(2026, 5, 1), end=date(2026, 5, 1)),
        )

        self.assertEqual(
            [("e1", "a1", 0), ("e2", "a2", 0)], self._links()
        )
        self.assertEqual([("race", "race_link")], self._methods("a1"))

if __name__ == "__main__":
    unittest.main()
