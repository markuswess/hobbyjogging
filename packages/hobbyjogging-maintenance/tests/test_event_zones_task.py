import json
import unittest
from datetime import date

from hobbyjogging_core import (
    EventZoneTime,
    TrainingRepository,
    TrainingWriter,
    canonical_sport,
    connect,
    migrate,
)

from hobbyjogging_maintenance.context import Scope
from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task
from hobbyjogging_maintenance.store import is_applied

TASK = "event_zones_v1"


def _pace(duration=600):
    return {"duration": duration, "pace": {"units": "%pace", "value": 70}}


def _hr(duration=600):
    return {"duration": duration, "hr": {"units": "%lthr", "value": 70}}


def _workout(steps, zone_times):
    return {"steps": steps, "zoneTimes": zone_times}


def _nonzero(counts):
    """Drop the zero-filled counters so assertions stay focused."""
    return {name: value for name, value in counts.items() if value}


class EventZoneTaskTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _upsert_record(self, external_id, payload, source="intervals"):
        return self.writer.upsert_source_record(
            source=source,
            record_type="event",
            external_id=external_id,
            checksum=f"c-{external_id}",
            payload_json=(
                payload if isinstance(payload, str) else json.dumps(payload)
            ),
            import_run_id=self.run_id,
        )

    def _seed_event(
        self,
        external_id="1",
        payload=None,
        *,
        source="intervals",
        event_id=None,
    ):
        payload = payload or {}
        metadata = payload if isinstance(payload, dict) else {}
        record_id = self._upsert_record(external_id, payload, source)
        event_id = event_id or f"e-{external_id}"
        self.writer.upsert_event(
            event_id=event_id,
            local_date="2026-10-01",
            name=str(metadata.get("name") or "Workout"),
            type=canonical_sport(metadata.get("type")),
            source_record_id=record_id,
        )
        self.conn.commit()
        return event_id

    def _types(self, event_id):
        row = self.conn.execute(
            "SELECT zone_kind FROM events WHERE id = ?",
            (event_id,),
        ).fetchone()
        zones = self.conn.execute(
            """
            SELECT zone_label, seconds FROM event_zone_times
            WHERE event_id = ?
            ORDER BY COALESCE(zone_index, 99), zone_label
            """,
            (event_id,),
        ).fetchall()
        return row["zone_kind"], [
            (zone["zone_label"], zone["seconds"]) for zone in zones
        ]

    def _workout_payload(self, *, sport="Run", steps=None, zones=None):
        return {
            "id": 1,
            "start_date_local": "2026-10-01T08:00:00",
            "type": sport,
            "name": "Workout",
            "workout_doc": _workout(
                steps or [_pace()],
                zones
                or [
                    {"id": "Z1", "secs": 600},
                    {"id": "Z2", "secs": 0},
                ],
            ),
        }

    def test_writes_kind_and_zones(self):
        event_id = self._seed_event(payload=self._workout_payload())

        run = self._run()

        self.assertEqual("ok", run.status)
        self.assertEqual({"events": 1, "updated": 1}, _nonzero(run.counts))
        kind, zones = self._types(event_id)
        self.assertEqual("pace", kind)
        self.assertEqual([("Z1", 600), ("Z2", 0)], zones)

        event = TrainingRepository(self.conn).events(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )[0]
        self.assertEqual("pace", event.zone_kind)
        self.assertEqual(
            ["Z1", "Z2"],
            [zone.zone_label for zone in event.zone_times],
        )

    def test_is_recorded_as_applied(self):
        self._seed_event(payload=self._workout_payload())

        self._run()

        self.assertTrue(is_applied(self.conn, TASK))
        self.assertEqual(
            "skipped",
            self._run().status,
        )

    def test_forced_rerun_is_idempotent(self):
        event_id = self._seed_event(payload=self._workout_payload())
        self._run()

        again = self._run(force=True)

        self.assertEqual({"events": 1, "unchanged": 1}, _nonzero(again.counts))
        self.assertEqual(("pace", [("Z1", 600), ("Z2", 0)]), self._types(event_id))

    def test_clears_an_event_without_a_workout_document(self):
        event_id = self._seed_event(payload=self._workout_payload())
        self._run()

        self._upsert_record(
            "1",
            {"id": 1, "type": "Run", "name": "Workout"},
        )
        run = self._run(force=True)

        self.assertEqual({"events": 1, "updated": 1, "cleared": 1}, _nonzero(run.counts))
        self.assertEqual(("", []), self._types(event_id))

    def test_skips_other_source_events(self):
        event_id = self._seed_event(
            "m1",
            {"id": "m1", "type": "Run", "name": "Manual"},
            source="manual",
        )
        self.writer.set_event_zone_times(
            event_id,
            "hr",
            [EventZoneTime("Z2", 1200, 2)],
        )
        self.conn.commit()

        run = self._run()

        self.assertEqual({}, _nonzero(run.counts))
        self.assertEqual(["No events in scope."], run.notes)
        self.assertEqual(("hr", [("Z2", 1200)]), self._types(event_id))

    def test_skips_excluded_events(self):
        event_id = self._seed_event(payload=self._workout_payload())
        self.writer.set_event_zone_times(
            event_id,
            "hr",
            [EventZoneTime("Z2", 1200, 2)],
        )
        self.writer.exclude_event(event_id)
        self.conn.commit()

        run = self._run()

        self.assertEqual({"events": 1, "skipped": 1}, _nonzero(run.counts))
        self.assertEqual(("hr", [("Z2", 1200)]), self._types(event_id))
        self.assertTrue(any("skipped" in note for note in run.notes))

    def test_skips_malformed_payloads(self):
        event_id = self._seed_event("bad", "not json")

        run = self._run()

        self.assertEqual({"events": 1, "skipped": 1}, _nonzero(run.counts))
        self.assertEqual(("", []), self._types(event_id))

    def test_dry_run_writes_nothing_and_stays_pending(self):
        event_id = self._seed_event(payload=self._workout_payload())

        run = self._run(dry_run=True)

        self.assertEqual({"events": 1, "updated": 1}, _nonzero(run.counts))
        self.assertEqual(("", []), self._types(event_id))
        self.assertFalse(is_applied(self.conn, TASK))

    def test_scope_limits_by_event(self):
        first = self._seed_event(payload=self._workout_payload())
        second = self._seed_event(
            "2",
            self._workout_payload(),
            event_id="e-2",
        )

        run = self._run(scope=Scope(entity_id=second))

        self.assertEqual({"events": 1, "updated": 1}, _nonzero(run.counts))
        self.assertEqual(("", []), self._types(first))
        self.assertEqual("pace", self._types(second)[0])


if __name__ == "__main__":
    unittest.main()
