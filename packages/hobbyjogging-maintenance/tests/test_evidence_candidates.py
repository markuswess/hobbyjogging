import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_core.model import Lap

from hobbyjogging_maintenance.context import Scope
from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

ILLNESS = "illness_candidates_current"
TRAIL = "trail_candidates_current"


class EvidenceCandidateTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

    def _activity(
        self,
        activity_id,
        day,
        *,
        sport="run",
        tags=None,
        distance=10000.0,
        elevation=None,
        sub_sport=None,
    ):
        values = {
            "local_date": day,
            "sport": sport,
            "distance_m": distance,
        }
        if elevation is not None:
            values["elevation_gain_m"] = elevation
        if sub_sport is not None:
            values["sub_sport"] = sub_sport
        self.writer.upsert_activity(
            activity_id,
            values,
            source="test",
            source_record_id=None,
        )
        if tags:
            self.writer.replace_activity_tags(
                activity_id, tags, source="runalyze"
            )
        self.conn.commit()

    def _period(self, start, end=None, kind="illness"):
        self.writer.upsert_training_period(
            f"p-{start}",
            kind=kind,
            start_date=start,
            end_date=end,
        )
        self.conn.commit()

    def _items(self, category):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM review_items WHERE category = ? ORDER BY id",
                (category,),
            )
        ]

    def _run(self, task, **kwargs):
        run = run_task(self.conn, get_task(task), **kwargs)
        self.assertEqual("ok", run.status, run.error)
        return run

    # -- illness ---------------------------------------------------------

    def test_illness_outside_a_period_opens_a_candidate(self):
        self._activity("a1", "2026-03-11", tags=["verkühlt"])

        run = self._run(ILLNESS)

        self.assertEqual(1, run.counts["candidates"])
        self.assertEqual(1, run.counts["opened"])
        item = self._items("period_candidate")[0]
        self.assertEqual("open", item["status"])
        self.assertIn("2026-03-11", item["detail"])
        self.assertIn("verkühlt", item["detail"])
        self.assertEqual(
            "illness_candidate",
            json.loads(item["context_json"])["rule"],
        )

    def test_illness_inside_a_period_has_no_candidate(self):
        self._period("2026-04-01", "2026-04-05")
        self._activity("a1", "2026-04-03", tags=["grippe"])

        run = self._run(ILLNESS)

        self.assertEqual(0, run.counts["candidates"])
        self.assertEqual([], self._items("period_candidate"))

    def test_recovered_tag_closes_the_candidate_range(self):
        self._activity("a1", "2026-03-11", tags=["verkühlt"])
        self._activity("a1b", "2026-03-13", tags=["wieder gesund"])

        self._run(ILLNESS)

        item = self._items("period_candidate")[0]
        self.assertIn("2026-03-11..2026-03-13", item["detail"])

    def test_overlapping_recovery_ranges_merge(self):
        self._activity("a1", "2026-03-01", tags=["verkühlt"])
        self._activity("a2", "2026-03-05", tags=["verkühlt"])
        self._activity("a3", "2026-03-09", tags=["wieder gesund"])

        self._run(ILLNESS)

        items = self._items("period_candidate")
        self.assertEqual(1, len(items))
        self.assertIn("2026-03-01..2026-03-09", items[0]["detail"])

    def test_schlapp_is_not_illness_evidence(self):
        self._activity("a1", "2026-03-11", tags=["schlapp"])

        run = self._run(ILLNESS)

        self.assertEqual(0, run.counts["candidates"])

    def test_second_run_is_unchanged(self):
        self._activity("a1", "2026-03-11", tags=["verkühlt"])
        self._run(ILLNESS)

        second = self._run(ILLNESS, force=True)

        self.assertEqual(0, second.counts["opened"])
        self.assertEqual(1, second.counts["unchanged"])

    def test_adding_a_period_resolves_the_candidate(self):
        self._activity("a1", "2026-03-11", tags=["verkühlt"])
        self._run(ILLNESS)
        self._period("2026-03-10", "2026-03-12")

        run = self._run(ILLNESS, force=True)

        self.assertEqual(1, run.counts["resolved"])
        self.assertEqual("resolved", self._items("period_candidate")[0]["status"])

    def test_scope_limits_to_one_activity(self):
        self._activity("a1", "2026-03-11", tags=["verkühlt"])
        self._activity("a2", "2026-03-20", tags=["krank"])

        self._run(ILLNESS, scope=Scope(entity_id="a1"))

        items = self._items("period_candidate")
        self.assertEqual(1, len(items))
        self.assertEqual("a1", items[0]["activity_id"])

    # -- trail -----------------------------------------------------------

    def test_elevation_opens_a_trail_candidate(self):
        self._activity("a1", "2026-05-01", elevation=500.0)

        run = self._run(TRAIL)

        self.assertEqual(1, run.counts["opened"])
        item = self._items("consistency")[0]
        self.assertIn("50 m/km", item["detail"])
        self.assertIn("trail_run", item["context_json"])

    def test_lap_elevation_is_used_when_the_session_has_none(self):
        self._activity("a1", "2026-05-01")
        self.writer.replace_activity_laps(
            "a1",
            [
                Lap(index=1, elevation_gain_m=300.0),
                Lap(index=2, elevation_gain_m=200.0),
            ],
        )
        self.conn.commit()

        run = self._run(TRAIL)

        self.assertEqual(1, run.counts["opened"])

    def test_a_trail_run_is_skipped(self):
        self._activity(
            "a1",
            "2026-05-01",
            sport="trail_run",
            elevation=500.0,
        )

        run = self._run(TRAIL)

        self.assertEqual(0, run.counts["candidates"])

    def test_sub_sport_and_trail_tag_are_evidence(self):
        self._activity(
            "a1",
            "2026-05-01",
            sub_sport="trail",
        )
        self._activity("a2", "2026-05-02", tags=["Trail"])

        run = self._run(TRAIL)

        self.assertEqual(2, run.counts["candidates"])

    def test_route_name_alone_is_not_enough(self):
        self._activity("a1", "2026-05-01", elevation=0.0)
        self.writer.upsert_route(
            "r1",
            name="Küniglberg trail",
            source="test",
        )
        self.writer.replace_activity_routes("a1", ["r1"], source="test")
        self.conn.commit()

        run = self._run(TRAIL)

        self.assertEqual(0, run.counts["candidates"])

    def test_second_run_is_unchanged(self):
        self._activity("a1", "2026-05-01", elevation=500.0)
        self._run(TRAIL)

        second = self._run(TRAIL, force=True)

        self.assertEqual(0, second.counts["opened"])
        self.assertEqual(1, second.counts["unchanged"])

    def test_changing_the_sport_resolves_the_candidate(self):
        self._activity("a1", "2026-05-01", elevation=500.0)
        self._run(TRAIL)
        self.writer.set_manual_field("a1", "sport", "trail_run")
        self.conn.commit()

        run = self._run(TRAIL, force=True)

        self.assertEqual(1, run.counts["resolved"])
        self.assertEqual("resolved", self._items("consistency")[0]["status"])


if __name__ == "__main__":
    unittest.main()
