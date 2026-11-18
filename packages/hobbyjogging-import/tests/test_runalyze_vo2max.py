import json
import unittest
from datetime import date

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.runalyze_vo2max import (
    RunalyzeVo2maxImporter,
    format_vo2max_summary,
)


class RunalyzeVo2maxTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

    def _activity(self, activity_id, local_date="2026-01-01", **fields):
        values = {
            "local_date": local_date,
            "started_at_utc": f"{local_date}T06:00:00Z",
            "sport": "run",
            "name": "Run",
            "duration_s": 3600,
            "elapsed_s": 3600,
            "distance_m": 10000,
        }
        values.update(fields)
        self.writer.upsert_activity(
            activity_id,
            values,
            source="fit",
            source_record_id=None,
        )

    def _payload(self, activity_id, **payload):
        source_record_id = self.writer.upsert_source_record(
            source="runalyze",
            record_type="activity",
            external_id=activity_id,
            checksum=activity_id,
            payload_json=json.dumps(payload),
            import_run_id=self.run_id,
        )
        self.writer.link_activity_source(
            activity_id,
            source_record_id,
            match_method="temporal_distance",
        )
        return source_record_id

    def _import(self, **kwargs):
        return RunalyzeVo2maxImporter(self.conn).import_vo2max(**kwargs)

    def _row(self, activity_id):
        return self.conn.execute(
            "SELECT * FROM activities WHERE id = ?",
            (activity_id,),
        ).fetchone()

    def test_writes_the_effective_value_and_leaves_garmin_alone(self):
        self._activity("a1", vo2max_garmin=52.0)
        self._payload("a1", vo2max=49.3, vo2max_by_time=47.0)

        summary = self._import()

        self.assertEqual(1, summary.written)
        row = self._row("a1")
        self.assertAlmostEqual(49.3, row["vo2max_runalyze"])
        self.assertAlmostEqual(52.0, row["vo2max_garmin"])

    def test_payloads_without_a_value_are_ignored(self):
        self._activity("a1")
        self._payload("a1", note="no estimate")

        summary = self._import()

        self.assertEqual(1, summary.payloads)
        self.assertEqual(0, summary.with_value)
        self.assertEqual(0, summary.written)
        self.assertIsNone(self._row("a1")["vo2max_runalyze"])

    def test_reimport_is_idempotent(self):
        self._activity("a1")
        self._payload("a1", vo2max=49.3)

        first = self._import()
        second = self._import()

        self.assertEqual(1, first.written)
        self.assertEqual(0, second.written)
        self.assertEqual(1, second.unchanged)

    def test_an_excluded_activity_is_not_written(self):
        self._activity("a1")
        self._payload("a1", vo2max=49.3)
        self.writer.exclude_activity("a1")

        summary = self._import()

        self.assertEqual(1, summary.skipped_excluded)
        self.assertEqual(0, summary.written)
        self.assertIsNone(self._row("a1")["vo2max_runalyze"])

    def test_dry_run_writes_nothing(self):
        self._activity("a1")
        self._payload("a1", vo2max=49.3)

        summary = self._import(dry_run=True)

        self.assertEqual(1, summary.written)
        self.assertIsNone(self._row("a1")["vo2max_runalyze"])

    def test_date_range_and_limit_scope_the_pass(self):
        self._activity("a1", local_date="2020-05-01")
        self._activity("a2", local_date="2026-05-01")
        self._payload("a1", vo2max=44.0)
        self._payload("a2", vo2max=49.0)

        window = self._import(start=date(2026, 1, 1))
        self.assertEqual(1, window.written)
        self.assertIsNone(self._row("a1")["vo2max_runalyze"])

        capped = self._import(limit=1)
        self.assertEqual(1, capped.payloads)

    def test_summary_format(self):
        self._activity("a1")
        self._payload("a1", vo2max=49.3)

        text = format_vo2max_summary(self._import(dry_run=True))

        self.assertIn("Runalyze VO2max dry run", text)
        self.assertIn("written: 1", text)


class RunalyzeVo2maxCliTests(unittest.TestCase):

    def test_parser_accepts_vo2max_options(self):
        args = build_parser().parse_args(
            ["runalyze", "vo2max", "--dry-run", "--limit", "5"]
        )

        self.assertEqual("runalyze", args.command)
        self.assertEqual("vo2max", args.runalyze_action)
        self.assertTrue(args.dry_run)
        self.assertEqual(5, args.limit)
        self.assertIsNone(args.start)


if __name__ == "__main__":
    unittest.main()
