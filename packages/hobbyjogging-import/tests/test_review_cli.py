import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import TrainingWriter, open_database
from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.review_cli import run_review


class ReviewCliTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "review.db"

        seed = open_database(self.database)
        self.addCleanup(seed.close)
        self.seed_writer = TrainingWriter(seed)
        self.run_id = self.seed_writer.start_import_run("test")
        self.seed_writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "started_at_utc": "2026-10-01T06:00:00Z",
                "duration_s": 3600,
                "elapsed_s": 3700,
                "distance_m": 10000,
                "name": "Morning run",
            },
            source="fit",
            source_record_id=None,
        )
        self.source_record_id = self.seed_writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="seg.fit:1",
            checksum="c1",
            import_run_id=self.run_id,
        )
        seed.commit()
        self._seed_items(seed)

    def _seed_items(self, seed):
        self.quality_id = self.seed_writer.record_review_item(
            category="quality",
            detail="distance is 0 m",
            context={"rule": "zero_distance", "distance_m": 0},
            fingerprint="fp-quality",
            activity_id="a1",
            import_run_id=self.run_id,
        )[0]
        self.ambiguous_id = self.seed_writer.record_review_item(
            category="ambiguous_match",
            detail="ambiguous match: 2 candidate activities",
            context={
                "external_id": "seg.fit:1",
                "candidates": [
                    {"activity_id": "a1", "match_method": "temporal_overlap",
                     "confidence": 0.9},
                    {"activity_id": "a2", "match_method": "temporal_overlap",
                     "confidence": 0.8},
                ],
            },
            fingerprint="fp-ambiguous",
            source_record_id=self.source_record_id,
            import_run_id=self.run_id,
        )[0]
        seed.commit()

    def _run(self, argv):
        parser = build_parser()
        args = parser.parse_args(argv)
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = run_review(args, parser)
        return code, captured.getvalue()

    def test_list_open_items(self):
        code, output = self._run(
            ["review", "--database", str(self.database), "list"]
        )

        self.assertEqual(0, code)
        self.assertIn("ambiguous_match/open", output)
        self.assertIn("quality/open", output)
        self.assertIn("2 open review item(s)", output)

    def test_list_filters_status_and_category(self):
        code, output = self._run(
            [
                "review", "--database", str(self.database),
                "list", "--category", "quality",
            ]
        )

        self.assertEqual(0, code)
        self.assertNotIn("ambiguous_match", output)
        self.assertIn("quality/open", output)

    def test_show_prints_full_detail(self):
        code, output = self._run(
            ["review", "--database", str(self.database), "show",
             str(self.ambiguous_id)]
        )

        self.assertEqual(0, code)
        self.assertIn("ambiguous_match/open", output)
        self.assertIn("2 candidate activities", output)
        self.assertIn("a2", output)
        self.assertIn("0.8", output)
        self.assertIn("external_id", output)

    def test_show_unknown_item_errors(self):
        with self.assertRaises(SystemExit):
            self._run(
                ["review", "--database", str(self.database), "show", "999"]
            )

    def test_resolve_without_activity_marks_resolved(self):
        code, output = self._run(
            ["review", "--database", str(self.database), "resolve",
             str(self.quality_id), "--note", "accept data"]
        )

        self.assertEqual(0, code)
        self.assertIn(f"Resolved #{self.quality_id}", output)

        item = self.seed_writer.review_item(self.quality_id)
        self.assertEqual("resolved", item["status"])
        self.assertIn("accept data", item["resolved_note"])

    def test_resolve_with_activity_relinks_source_record(self):
        code, output = self._run(
            ["review", "--database", str(self.database), "resolve",
             str(self.ambiguous_id), "--activity", "a1", "--note", "first"]
        )

        self.assertEqual(0, code)
        self.assertIn("linked to a1", output)

        item = self.seed_writer.review_item(self.ambiguous_id)
        self.assertEqual("resolved", item["status"])

        links = self.seed_writer.connection.execute(
            """
            SELECT activity_id, match_method
            FROM activity_sources WHERE source_record_id = ?
            """,
            (self.source_record_id,),
        ).fetchall()
        self.assertEqual(1, len(links))
        self.assertEqual("a1", links[0]["activity_id"])
        self.assertEqual("review_resolved", links[0]["match_method"])

    def test_ignore_marks_ignored(self):
        code, output = self._run(
            ["review", "--database", str(self.database), "ignore",
             str(self.quality_id)]
        )

        self.assertEqual(0, code)
        self.assertIn(f"Ignored #{self.quality_id}", output)

        item = self.seed_writer.review_item(self.quality_id)
        self.assertEqual("ignored", item["status"])

    def test_flag_creates_and_is_idempotent(self):
        argv = [
            "review", "--database", str(self.database), "flag", "a1",
            "--category", "quality", "--severity", "error",
            "--note", "stray gps points",
        ]

        code, output = self._run(argv)
        self.assertEqual(0, code)
        self.assertIn("Flagged quality: a1", output)

        items = self.seed_writer.review_items(status="open")
        self.assertEqual(
            3,
            len(items),
            "flag should add one item to the existing two",
        )
        flagged = next(
            item for item in items if item["detail"] == "stray gps points"
        )
        self.assertEqual("error", flagged["severity"])

        # Re-flagging the same content is a no-op.
        code, output = self._run(argv)
        self.assertEqual(0, code)
        self.assertIn("Already flagged", output)
        self.assertEqual(
            3,
            len(self.seed_writer.review_items(status="open")),
        )

    def test_flag_without_database_flag_option(self):
        code, output = self._run(
            ["review", "--database", str(self.database), "flag", "a1"]
        )

        self.assertEqual(0, code)
        self.assertIn("Flagged manual_flag: a1", output)

    def test_scan_records_findings_for_degenerate_activities(self):
        seed = open_database(self.database)
        seed.execute(
            """
            INSERT INTO activities (
                id, local_date, sport, duration_s, elapsed_s, distance_m
            ) VALUES ('junk', '2019-01-30', 'run', 0, 0, 0)
            """
        )
        seed.commit()
        seed.close()

        code, output = self._run(
            ["review", "--database", str(self.database), "scan"]
        )

        self.assertEqual(0, code)
        self.assertIn("finding", output)

        writer = TrainingWriter(open_database(self.database))
        items = writer.review_items(status="open")
        self.assertEqual(
            4,
            len(items),
            "existing two + zero_duration + zero_distance for 'junk'",
        )
        self.assertEqual(
            2,
            len([item for item in items if item["activity_id"] == "junk"]),
        )

        code, output = self._run(
            ["review", "--database", str(self.database), "scan"]
        )
        self.assertEqual(0, code)
        self.assertIn(
            "2 finding(s), 0 new review item(s)", output
        )

    def test_scan_dry_run_records_nothing(self):
        seed = open_database(self.database)
        seed.execute(
            """
            INSERT INTO activities (
                id, local_date, sport, duration_s, elapsed_s, distance_m
            ) VALUES ('junk', '2019-01-30', 'run', 0, 0, 0)
            """
        )
        seed.commit()
        seed.close()

        code, output = self._run(
            ["review", "--database", str(self.database), "scan", "--dry-run"]
        )

        self.assertEqual(0, code)
        self.assertIn("Scan dry run", output)

        writer = TrainingWriter(open_database(self.database))
        items = writer.review_items(status="all")
        self.assertEqual(2, len(items))
        self.assertIn("Scan dry run", output)


if __name__ == "__main__":
    unittest.main()
