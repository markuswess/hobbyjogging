import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from hobbyjogging_core import (
    EventZoneTime,
    TrainingRepository,
    TrainingWriter,
    canonical_sport,
    connect,
    migrate,
    open_database,
)
from hobbyjogging_import.cli import build_parser, run_events
from hobbyjogging_import.event_zones import (
    UNKNOWN,
    backfill_event_zones,
    event_zone_data,
    infer_zone_kind,
    parse_zone_times,
)


def _pace(duration=600):
    return {"duration": duration, "pace": {"units": "%pace", "value": 70}}


def _hr(duration=600):
    return {"duration": duration, "hr": {"units": "%lthr", "value": 70}}


def _power(duration=600):
    return {"duration": duration, "power": {"units": "%ftp", "value": 70}}


def _workout(steps, zone_times):
    return {"steps": steps, "zoneTimes": zone_times}


class ZoneParsingTests(unittest.TestCase):

    def test_keeps_zero_seconds_and_known_labels(self):
        zones = parse_zone_times(
            {
                "zoneTimes": [
                    {"id": "Z1", "secs": 0},
                    {"id": "Z2", "secs": 600},
                    {"id": "Z7", "secs": 30},
                    {"id": "SS", "secs": 900},
                ]
            }
        )

        self.assertEqual(
            ["Z1", "Z2", "Z7", "SS"],
            [zone.zone_label for zone in zones],
        )
        self.assertEqual([0, 600, 30, 900], [zone.seconds for zone in zones])
        self.assertEqual([1, 2, 7, None], [zone.zone_index for zone in zones])

    def test_normalizes_lowercase_and_last_duplicate_wins(self):
        zones = parse_zone_times(
            {
                "zoneTimes": [
                    {"id": "z3", "secs": 60},
                    {"id": "Z3", "secs": 90},
                ]
            }
        )

        self.assertEqual(["Z3"], [zone.zone_label for zone in zones])
        self.assertEqual(90, zones[0].seconds)

    def test_ignores_unknown_labels_and_bad_durations(self):
        zones = parse_zone_times(
            {
                "zoneTimes": [
                    {"id": "Z8", "secs": 10},
                    {"id": "Z4", "secs": None},
                    {"id": "Z5", "secs": -1},
                    {"nope": 1},
                    "not a row",
                ]
            }
        )

        self.assertEqual([], zones)

    def test_missing_or_malformed_document_is_empty(self):
        self.assertEqual([], parse_zone_times(None))
        self.assertEqual([], parse_zone_times({}))
        self.assertEqual([], parse_zone_times({"zoneTimes": {}}))


class ZoneKindTests(unittest.TestCase):

    def test_dominant_step_target_wins(self):
        self.assertEqual(
            "pace",
            infer_zone_kind(_workout([_pace()], []), "run"),
        )
        self.assertEqual(
            "hr",
            infer_zone_kind(_workout([_hr()], []), "run"),
        )
        self.assertEqual(
            "power",
            infer_zone_kind(_workout([_power()], []), "ride"),
        )

    def test_dominant_target_uses_planned_seconds(self):
        document = _workout(
            [_hr(900), _pace(300)],
            [],
        )

        self.assertEqual("hr", infer_zone_kind(document, "run"))

    def test_nested_repeats_are_weighted(self):
        document = _workout(
            [
                {
                    "reps": 3,
                    "steps": [_hr(100), _pace(300)],
                }
            ],
            [],
        )

        self.assertEqual("pace", infer_zone_kind(document, "run"))

    def test_ties_follow_the_sport(self):
        run = _workout([{**_pace(), **_hr()}], [])
        ride = _workout([{**_power(), **_hr()}], [])

        self.assertEqual("pace", infer_zone_kind(run, "run"))
        self.assertEqual("power", infer_zone_kind(ride, "ride"))

    def test_without_targets_the_sport_decides(self):
        for sport in ("run", "trail_run", "treadmill_run"):
            with self.subTest(sport=sport):
                self.assertEqual(
                    "pace",
                    infer_zone_kind(_workout([], []), sport),
                )

        for sport in ("ride", "gravel_ride", "virtual_ride"):
            with self.subTest(sport=sport):
                self.assertEqual(
                    "power",
                    infer_zone_kind(_workout([], []), sport),
                )

        self.assertEqual(UNKNOWN, infer_zone_kind(_workout([], []), "soccer"))
        self.assertEqual(UNKNOWN, infer_zone_kind(_workout([], []), ""))

    def test_event_without_a_workout_document_clears_everything(self):
        kind, zones = event_zone_data({"id": 1}, "run")

        self.assertEqual("", kind)
        self.assertEqual([], zones)

    def test_event_data_combines_kind_and_zones(self):
        raw = {
            "workout_doc": {
                "steps": [_hr()],
                "zoneTimes": [{"id": "Z2", "secs": 600}],
            }
        }

        kind, zones = event_zone_data(raw, "run")

        self.assertEqual("hr", kind)
        self.assertEqual(["Z2"], [zone.zone_label for zone in zones])


class BackfillTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

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

    def test_backfill_writes_kind_and_zones(self):
        event_id = self._seed_event(payload=self._workout_payload())

        summary = backfill_event_zones(self.conn)

        self.assertEqual(1, summary.events)
        self.assertEqual(1, summary.updated)
        self.assertEqual(0, summary.unchanged)
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

    def test_backfill_is_idempotent(self):
        self._seed_event(payload=self._workout_payload())

        first = backfill_event_zones(self.conn)
        second = backfill_event_zones(self.conn)

        self.assertEqual(1, first.updated)
        self.assertEqual(0, second.updated)
        self.assertEqual(1, second.unchanged)

    def test_backfill_clears_an_event_without_a_workout_document(self):
        event_id = self._seed_event(payload=self._workout_payload())
        backfill_event_zones(self.conn)

        self._upsert_record(
            "1",
            {"id": 1, "type": "Run", "name": "Workout"},
        )
        summary = backfill_event_zones(self.conn)

        self.assertEqual(1, summary.updated)
        self.assertEqual(1, summary.cleared)
        self.assertEqual(("", []), self._types(event_id))

    def test_backfill_skips_other_source_events(self):
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

        summary = backfill_event_zones(self.conn)

        self.assertEqual(0, summary.events)
        self.assertEqual(("hr", [("Z2", 1200)]), self._types(event_id))

    def test_backfill_skips_excluded_events(self):
        event_id = self._seed_event(payload=self._workout_payload())
        self.writer.set_event_zone_times(
            event_id,
            "hr",
            [EventZoneTime("Z2", 1200, 2)],
        )
        self.writer.exclude_event(event_id)
        self.conn.commit()

        summary = backfill_event_zones(self.conn)

        self.assertEqual(1, summary.events)
        self.assertEqual(1, summary.skipped)
        self.assertEqual(0, summary.updated)
        self.assertEqual(("hr", [("Z2", 1200)]), self._types(event_id))

    def test_backfill_skips_malformed_payloads(self):
        event_id = self._seed_event("bad", "not json")

        summary = backfill_event_zones(self.conn)

        self.assertEqual(1, summary.skipped)
        self.assertEqual(("", []), self._types(event_id))

    def test_backfill_dry_run_writes_nothing(self):
        event_id = self._seed_event(payload=self._workout_payload())

        summary = backfill_event_zones(self.conn, dry_run=True)

        self.assertEqual(1, summary.updated)
        self.assertEqual(("", []), self._types(event_id))


class BackfillCliTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "zones.db"

        connection = open_database(self.database)
        self.addCleanup(connection.close)
        writer = TrainingWriter(connection)
        run_id = writer.start_import_run("test")
        record_id = writer.upsert_source_record(
            source="intervals",
            record_type="event",
            external_id="1",
            checksum="c1",
            payload_json=json.dumps(
                {
                    "id": 1,
                    "start_date_local": "2026-10-01T08:00:00",
                    "type": "Run",
                    "name": "Workout",
                    "workout_doc": _workout(
                        [_pace()],
                        [{"id": "Z1", "secs": 600}],
                    ),
                }
            ),
            import_run_id=run_id,
        )
        writer.upsert_event(
            event_id="e1",
            local_date="2026-10-01",
            name="Workout",
            type="run",
            source_record_id=record_id,
        )
        connection.commit()

    def test_parser_accepts_backfill_zones(self):
        args = build_parser().parse_args(
            ["events", "backfill-zones", "--dry-run"]
        )

        self.assertEqual("events", args.command)
        self.assertEqual("backfill-zones", args.events_action)
        self.assertTrue(args.dry_run)
        self.assertIsNone(args.database)

    def test_command_backfills_the_database(self):
        args = build_parser().parse_args(
            [
                "events",
                "backfill-zones",
                "--database",
                str(self.database),
            ]
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_events(args, build_parser())

        self.assertEqual(0, code)
        self.assertIn("1 events, 1 updated", output.getvalue())

        connection = open_database(self.database)
        self.addCleanup(connection.close)
        event = TrainingRepository(connection).events(
            date(2026, 10, 1),
            date(2026, 10, 2),
        )[0]
        self.assertEqual("pace", event.zone_kind)
        self.assertEqual(
            ["Z1"],
            [zone.zone_label for zone in event.zone_times],
        )


if __name__ == "__main__":
    unittest.main()
