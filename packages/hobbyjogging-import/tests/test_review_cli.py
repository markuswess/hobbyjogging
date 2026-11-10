import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
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

    def test_exclude_and_restore_activity(self):
        self.seed_writer.link_activity_source(
            "a1", self.source_record_id, match_method="created"
        )
        seed_conn = self.seed_writer.connection
        seed_conn.commit()

        code, output = self._run(
            [
                "review", "--database", str(self.database),
                "exclude", "a1", "--note", "bad data",
            ]
        )

        self.assertEqual(0, code)
        self.assertIn("Excluded a1", output)
        self.assertIn("Review items resolved: 1", output)
        seed_conn.commit()
        self.assertEqual(
            "resolved",
            self.seed_writer.review_item(self.quality_id)["status"],
        )
        self.assertEqual(
            "bad data",
            self.seed_writer.review_item(self.quality_id)["resolved_note"],
        )

        code, output = self._run(
            ["review", "--database", str(self.database), "list",
             "--status", "all"]
        )

        self.assertIn("[excluded]", output)
        self.assertNotIn("open review item(s)", output)

        code, output = self._run(
            ["review", "--database", str(self.database), "restore", "a1"]
        )

        self.assertEqual(0, code)
        self.assertIn("Restored a1", output)

        rows = seed_conn.execute(
            "SELECT excluded_at FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertIsNone(rows["excluded_at"])
        self.assertIsNone(
            seed_conn.execute(
                "SELECT excluded_at FROM source_records WHERE id = ?",
                (self.source_record_id,),
            ).fetchone()["excluded_at"],
        )

    def test_edit_sets_manual_value_resolves_item_and_reports_quality(self):
        conn = self.seed_writer.connection
        # Recreate the zero-distance situation the seed item describes.
        conn.execute("UPDATE activities SET distance_m = 0 WHERE id = 'a1'")
        conn.commit()

        code, output = self._run(
            [
                "review", "--database", str(self.database),
                "edit", "a1",
                "--distance", "10.0km",
                "--item", str(self.quality_id),
            ]
        )

        self.assertEqual(0, code)
        self.assertIn("set distance_m: 0.00 km → 10.00 km (manual)", output)
        self.assertIn(f"Resolved #{self.quality_id}", output)
        self.assertIn("quality: ok", output)

        row = conn.execute(
            "SELECT distance_m FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(10000, row["distance_m"])

        source = conn.execute(
            """
            SELECT source, is_manual FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = 'distance_m'
            """
        ).fetchone()
        self.assertEqual("manual", source["source"])
        self.assertEqual(1, source["is_manual"])

        item = self.seed_writer.review_item(self.quality_id)
        self.assertEqual("resolved", item["status"])
        self.assertEqual(
            0,
            len(
                self.seed_writer.review_items(
                    status="open", category="quality"
                )
            ),
        )

    def test_edit_survives_reimport(self):
        conn = self.seed_writer.connection
        conn.execute("UPDATE activities SET distance_m = 0 WHERE id = 'a1'")
        conn.commit()
        self._run(
            [
                "review", "--database", str(self.database),
                "edit", "a1", "--distance", "10.2km",
            ]
        )

        # A reimport tries to write the original wrong distance again.
        self.seed_writer.upsert_activity(
            "a1",
            {"distance_m": 0},
            source="fit",
            source_record_id=self.source_record_id,
        )
        conn.commit()

        row = conn.execute(
            "SELECT distance_m FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual(10200, row["distance_m"])

    def test_edit_still_flagged_prints_remaining_findings(self):
        conn = self.seed_writer.connection
        conn.execute("UPDATE activities SET distance_m = 0 WHERE id = 'a1'")
        conn.execute("UPDATE activities SET duration_s = 0 WHERE id = 'a1'")
        conn.commit()

        code, output = self._run(
            [
                "review", "--database", str(self.database),
                "edit", "a1", "--duration", "60:00", "--note", "fixed time",
            ]
        )

        self.assertEqual(0, code)
        self.assertIn("set duration_s", output)
        self.assertIn("still flagged", output)
        self.assertIn("zero_distance", output)
        self.assertEqual(
            1,
            len(
                self.seed_writer.review_items(
                    status="open", category="quality"
                )
            ),
        )

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

    def test_show_prints_activity_links(self):
        intervals_record = self.seed_writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id="i104800507",
            checksum="c2",
            import_run_id=self.run_id,
        )
        self.seed_writer.link_activity_source(
            "a1",
            intervals_record,
            match_method="external_id",
        )
        started = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)
        self.seed_writer.upsert_source_record(
            source="garmin",
            record_type="activity-file",
            external_id="24926143497",
            checksum="c3",
            payload_json=json.dumps(
                {"beginTimestamp": int(started.timestamp() * 1000)}
            ),
            raw_path="/tmp/garmin/24926143497.fit",
            import_run_id=self.run_id,
        )
        self.seed_writer.connection.commit()

        code, output = self._run(
            ["review", "--database", str(self.database), "show",
             str(self.quality_id)]
        )

        self.assertEqual(0, code)
        self.assertIn(
            "Intervals: https://intervals.icu/activities/i104800507",
            output,
        )
        self.assertIn(
            "Garmin: https://connect.garmin.com/app/activity/24926143497",
            output,
        )

    def test_prune_resolves_conflicts_within_tolerance(self):
        conflict_id, _ = self.seed_writer.record_review_item(
            category="field_conflict",
            detail="duration differs",
            context={
                "rule": "field_conflict",
                "field": "duration_s",
                "current": {"source": "fit", "value": 3600},
                "incoming": {"source": "intervals", "value": 3610},
            },
            fingerprint="fp-prune",
            activity_id="a1",
        )
        self.seed_writer.connection.commit()

        code, output = self._run(
            ["review", "--database", str(self.database), "prune"]
        )

        self.assertEqual(0, code)
        self.assertIn("Prune: 1 resolved", output)
        self.assertEqual(
            "resolved",
            self.seed_writer.review_item(conflict_id)["status"],
        )

    def test_prune_dry_run_does_not_write(self):
        conflict_id, _ = self.seed_writer.record_review_item(
            category="field_conflict",
            detail="duration differs",
            context={
                "rule": "field_conflict",
                "field": "duration_s",
                "current": {"source": "fit", "value": 3600},
                "incoming": {"source": "intervals", "value": 3610},
            },
            fingerprint="fp-prune-dry",
            activity_id="a1",
        )
        self.seed_writer.connection.commit()

        code, output = self._run(
            ["review", "--database", str(self.database), "prune", "--dry-run"]
        )

        self.assertEqual(0, code)
        self.assertIn("Prune dry run: 1 resolved", output)
        self.assertEqual(
            "open",
            self.seed_writer.review_item(conflict_id)["status"],
        )

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

    def test_scan_prune_resolves_stale_quality_items(self):
        code, output = self._run(
            ["review", "--database", str(self.database), "scan", "--prune"]
        )

        self.assertEqual(0, code)
        self.assertIn("prune: 1 pruned", output)

        writer = TrainingWriter(open_database(self.database))
        self.addCleanup(writer.connection.close)
        open_items = writer.review_items(status="open")
        self.assertEqual(
            ["ambiguous_match"],
            [item["category"] for item in open_items],
        )

        code, output = self._run(
            ["review", "--database", str(self.database), "scan", "--prune"]
        )
        self.assertEqual(0, code)
        self.assertIn("prune: 0 pruned", output)

    def test_scan_prune_dry_run_writes_nothing(self):
        code, output = self._run(
            [
                "review", "--database", str(self.database),
                "scan", "--prune", "--dry-run",
            ]
        )

        self.assertEqual(0, code)
        self.assertIn("prune: 1 would resolve", output)

        writer = TrainingWriter(open_database(self.database))
        self.addCleanup(writer.connection.close)
        item = writer.review_item(self.quality_id)
        self.assertEqual("open", item["status"])

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


    # -- conflict causes ----------------------------------------------------

    def _seed_cause_conflict(
        self,
        fingerprint,
        cause,
        *,
        field_name="elapsed_s",
        current=3600,
        incoming=3700,
    ):
        item_id, _ = self.seed_writer.record_review_item(
            category="field_conflict",
            detail=f"{field_name} differs",
            context={
                "rule": "field_conflict",
                "field": field_name,
                "current": {"source": "fit", "value": current},
                "incoming": {"source": "intervals", "value": incoming},
                **({"cause": cause} if cause else {}),
            },
            fingerprint=fingerprint,
            activity_id="a1",
        )
        self.seed_writer.connection.commit()
        return item_id

    def test_list_filters_by_cause(self):
        self._seed_cause_conflict("fp-elapsed", "elapsed_definition")
        self._seed_cause_conflict(
            "fp-unknown",
            "unknown",
            field_name="avg_hr",
            current=140,
            incoming=150,
        )

        code, output = self._run(
            ["review", "--database", str(self.database), "list",
             "--cause", "elapsed_definition"]
        )
        self.assertEqual(0, code)
        self.assertIn("[elapsed_definition]", output)
        self.assertNotIn("[unknown]", output)

        code, output = self._run(
            ["review", "--database", str(self.database), "list",
             "--cause", "unknown"]
        )
        self.assertEqual(0, code)
        self.assertIn("[unknown]", output)
        self.assertNotIn("[elapsed_definition]", output)

    def test_causes_summarizes_the_backlog(self):
        self._seed_cause_conflict("fp-1", "elapsed_definition")
        self._seed_cause_conflict("fp-2", "elapsed_definition")
        self._seed_cause_conflict("fp-3", None)

        code, output = self._run(
            ["review", "--database", str(self.database), "causes"]
        )

        self.assertEqual(0, code)
        self.assertIn("elapsed_definition", output)
        self.assertIn("unclassified", output)
        self.assertIn("run `review classify`", output)
        self.assertIn("3 open field conflict(s)", output)

    def test_classify_backfills_existing_conflicts(self):
        item_id = self._seed_cause_conflict("fp-old", None)
        self.assertNotIn(
            "cause",
            json.loads(self.seed_writer.review_item(item_id)["context_json"]),
        )

        code, output = self._run(
            ["review", "--database", str(self.database), "classify",
             "--dry-run"]
        )
        self.assertEqual(0, code)
        self.assertIn("1 updated", output)
        self.assertNotIn(
            "cause",
            json.loads(self.seed_writer.review_item(item_id)["context_json"]),
        )

        code, output = self._run(
            ["review", "--database", str(self.database), "classify"]
        )
        self.assertEqual(0, code)
        item = self.seed_writer.review_item(item_id)
        self.assertEqual(
            "elapsed_definition",
            json.loads(item["context_json"])["cause"],
        )
        self.assertEqual("info", item["severity"])

    def test_resolve_by_cause_bulk_and_dry_run(self):
        elapsed_id = self._seed_cause_conflict("fp-1", "elapsed_definition")
        unknown_id = self._seed_cause_conflict(
            "fp-2",
            "unknown",
            field_name="avg_hr",
            current=140,
            incoming=150,
        )

        code, output = self._run(
            ["review", "--database", str(self.database), "resolve",
             "--cause", "elapsed_definition", "--dry-run"]
        )
        self.assertEqual(0, code)
        self.assertIn("1 item(s) would be resolved", output)
        self.assertEqual(
            "open",
            self.seed_writer.review_item(elapsed_id)["status"],
        )

        code, output = self._run(
            ["review", "--database", str(self.database), "resolve",
             "--cause", "elapsed_definition"]
        )
        self.assertEqual(0, code)
        self.assertIn("Resolved 1 field conflict", output)
        self.assertEqual(
            "resolved",
            self.seed_writer.review_item(elapsed_id)["status"],
        )
        self.assertEqual(
            "open",
            self.seed_writer.review_item(unknown_id)["status"],
        )

    def test_resolve_rejects_non_advisory_cause(self):
        with self.assertRaises(SystemExit):
            self._run(
                ["review", "--database", str(self.database), "resolve",
                 "--cause", "activity_trimmed"]
            )

    def test_resolve_without_id_or_cause_errors(self):
        with self.assertRaises(SystemExit):
            self._run(
                ["review", "--database", str(self.database), "resolve"]
            )


if __name__ == "__main__":
    unittest.main()
