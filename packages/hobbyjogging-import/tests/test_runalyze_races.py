import json
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.runalyze import RunalyzeResponse
from hobbyjogging_import.runalyze_races import (
    RunalyzeRaceImporter,
    format_race_summary,
)


class FakeClient:

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return RunalyzeResponse(200, {}, list(self.rows))


class RunalyzeRaceTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

    def _activity(self, activity_id, local_date="2020-05-17"):
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": local_date,
                "started_at_utc": f"{local_date}T08:00:00Z",
                "sport": "run",
                "name": "Race",
                "duration_s": 3600,
                "elapsed_s": 3600,
                "distance_m": 10000,
            },
            source="fit",
            source_record_id=None,
        )

    def _runalyze_link(self, activity_id, external_id):
        source_record_id = self.writer.upsert_source_record(
            source="runalyze",
            record_type="activity",
            external_id=external_id,
            checksum=external_id,
            payload_json="{}",
            import_run_id=self.run_id,
        )
        self.writer.link_activity_source(
            activity_id,
            source_record_id,
            match_method="temporal_distance",
        )

    def _race(self, activity_id=101, **overrides):
        row = {
            "date": "2020-05-17",
            "activity_id": activity_id,
            "official_distance": 21.1,
            "official_time": 4823.0,
            "officially_measured": True,
            "name": "Eisbärlauf 1",
            "place_total": 11,
            "place_gender": 10,
            "place_ageclass": 5,
            "participants_total": 240,
            "participants_gender": 180,
            "participants_ageclass": 30,
            "priority_level": "B",
            "status": "completed",
        }
        row.update(overrides)
        return row

    def _import(self, rows, **kwargs):
        client = FakeClient(rows)
        importer = RunalyzeRaceImporter(self.conn, client)
        return importer.import_races(**kwargs), client

    def _result(self, activity_id):
        return self.conn.execute(
            "SELECT * FROM race_results WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()

    def test_writes_the_official_result_onto_the_linked_activity(self):
        self._activity("a1")
        self._runalyze_link("a1", "101")

        summary, client = self._import([self._race()])

        self.assertEqual(1, summary.written)
        row = self._result("a1")
        self.assertEqual("runalyze", row["source"])
        self.assertEqual("Eisbärlauf 1", row["name"])
        self.assertAlmostEqual(21100.0, row["official_distance_m"])
        self.assertAlmostEqual(4823.0, row["official_time_s"])
        self.assertEqual(1, row["officially_measured"])
        self.assertEqual(11, row["place_total"])
        self.assertEqual(240, row["participants_total"])
        self.assertEqual("B", row["priority_level"])
        self.assertEqual("completed", row["status"])
        self.assertEqual([("raceresult", {"page": 1, "itemsPerPage": 500})],
                         client.calls)

    def test_an_unlinked_race_is_reported_not_guessed(self):
        self._activity("a1")
        self._runalyze_link("a1", "101")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "unmatched.json"
            summary, _ = self._import(
                [self._race(activity_id=999, name="Elsewhere")],
                output=output,
            )
            payload = json.loads(output.read_text("utf-8"))

        self.assertEqual(1, summary.unmatched)
        self.assertEqual(0, summary.written)
        self.assertIsNone(self._result("a1"))
        self.assertEqual(999, payload["unmatched"][0]["runalyze_activity_id"])

    def test_a_manual_result_is_kept(self):
        self._activity("a1")
        self._runalyze_link("a1", "101")
        self.writer.upsert_race_result(
            "a1",
            source="manual",
            name="By hand",
            official_distance_m=21100.0,
        )

        summary, _ = self._import([self._race()])

        self.assertEqual(1, summary.kept_manual)
        self.assertEqual(0, summary.written)
        self.assertEqual("By hand", self._result("a1")["name"])

    def test_reimport_is_idempotent(self):
        self._activity("a1")
        self._runalyze_link("a1", "101")

        first, _ = self._import([self._race()])
        second, _ = self._import([self._race()])

        self.assertEqual(1, first.written)
        self.assertEqual(0, second.written)
        self.assertEqual(1, second.unchanged)

    def test_a_changed_result_is_replaced(self):
        self._activity("a1")
        self._runalyze_link("a1", "101")
        self._import([self._race()])

        summary, _ = self._import(
            [self._race(official_time=4700.0, place_total=9)]
        )

        self.assertEqual(1, summary.written)
        self.assertAlmostEqual(4700.0, self._result("a1")["official_time_s"])
        self.assertEqual(9, self._result("a1")["place_total"])

    def test_dry_run_writes_nothing(self):
        self._activity("a1")
        self._runalyze_link("a1", "101")

        summary, _ = self._import([self._race()], dry_run=True)

        self.assertEqual(1, summary.written)
        self.assertIsNone(self._result("a1"))
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records "
                "WHERE record_type = 'race_result'"
            ).fetchone()[0],
        )

    def test_summary_format(self):
        self._activity("a1")
        self._runalyze_link("a1", "101")

        summary, _ = self._import([self._race()], dry_run=True)
        text = format_race_summary(summary)

        self.assertIn("Runalyze races dry run", text)
        self.assertIn("written: 1", text)


class RunalyzeRaceCliTests(unittest.TestCase):

    def test_parser_accepts_races_options(self):
        args = build_parser().parse_args(
            ["runalyze", "races", "--dry-run", "--limit", "5"]
        )

        self.assertEqual("runalyze", args.command)
        self.assertEqual("races", args.runalyze_action)
        self.assertTrue(args.dry_run)
        self.assertEqual(5, args.limit)


if __name__ == "__main__":
    unittest.main()
