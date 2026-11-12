import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "event_race_method_v1"


class EventRaceMethodTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

    def _event(self, event_id="e1", *, category="RACE_A", source="intervals"):
        payload = {
            "id": event_id,
            "start_date_local": "2026-10-01T08:00:00",
            "type": "Run",
            "name": "Town race",
            "category": category,
        }
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="event",
            external_id=event_id,
            checksum=f"c-{event_id}",
            payload_json=json.dumps(payload),
            import_run_id=self.run_id,
        )
        self.writer.upsert_event(
            event_id=event_id,
            local_date="2026-10-01",
            name="Town race",
            type="run",
            source_record_id=record_id,
        )
        self.conn.commit()
        return event_id

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _methods(self, event_id):
        return [
            (row["method"], row["source"], row["is_manual"])
            for row in self.conn.execute(
                "SELECT method, source, is_manual FROM event_workout_methods "
                "WHERE event_id = ? ORDER BY method",
                (event_id,),
            )
        ]

    def test_adds_race_for_a_race_category(self):
        event_id = self._event(category="RACE_A")

        run = self._run()

        self.assertEqual(1, run.counts["added"])
        self.assertEqual([("race", "backfill", 0)], self._methods(event_id))

    def test_workout_category_adds_nothing(self):
        event_id = self._event(category="WORKOUT")

        run = self._run()

        self.assertEqual(1, run.counts["unchanged"])
        self.assertEqual([], self._methods(event_id))

    def test_removes_a_stale_race_row(self):
        event_id = self._event(category="RACE_A")
        self.writer.replace_event_workout_methods(
            event_id,
            ["race"],
            source="intervals",
        )
        self.conn.commit()

        # The payload is now a plain workout.
        self.conn.execute(
            "UPDATE source_records SET payload_json = ? "
            "WHERE record_type = 'event'",
            (json.dumps({"id": event_id, "category": "WORKOUT"}),),
        )
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["removed"])
        self.assertEqual([], self._methods(event_id))

    def test_manual_race_row_survives(self):
        event_id = self._event(category="WORKOUT")
        self.writer.replace_event_workout_methods(
            event_id,
            ["race"],
            source="manual",
            is_manual=True,
        )
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["unchanged"])
        self.assertEqual([("race", "manual", 1)], self._methods(event_id))

    def test_is_recorded_as_applied_and_idempotent(self):
        event_id = self._event(category="RACE_B")

        self._run()
        again = self._run(force=True)

        self.assertEqual(1, again.counts["unchanged"])
        self.assertEqual([("race", "backfill", 0)], self._methods(event_id))

    def test_dry_run_writes_nothing(self):
        event_id = self._event(category="RACE_C")

        run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["added"])
        self.assertEqual([], self._methods(event_id))

    def test_skips_other_sources_and_excluded_events(self):
        self._event("manual-1", category="RACE_A", source="manual")
        excluded = self._event("e2", category="RACE_A")
        self.writer.exclude_event(excluded)
        included = self._event("e3", category="RACE_A")
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["events"])
        self.assertEqual(1, run.counts["added"])
        self.assertEqual([], self._methods("manual-1"))
        self.assertEqual([], self._methods(excluded))
        self.assertEqual([("race", "backfill", 0)], self._methods(included))


if __name__ == "__main__":
    unittest.main()
