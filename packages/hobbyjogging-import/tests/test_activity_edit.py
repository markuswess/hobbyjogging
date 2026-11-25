import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import TrainingWriter, open_database
from hobbyjogging_import.activity_cli import run_activity
from hobbyjogging_import.parsers import build_parser


class ActivityEditTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "activity.db"

        self.conn = open_database(self.database)
        self.addCleanup(self.conn.close)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.source_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="f1",
            checksum="c1",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            "a1",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "Morning run",
                "description": "Easy run",
                "duration_s": 3600,
                "elapsed_s": 3700,
                "distance_m": 10000,
                "avg_hr": 145,
                "max_hr": 170,
                "rpe": 5,
                "feel": 3,
            },
            source="fit",
            source_record_id=self.source_id,
        )
        self.conn.commit()

    def _run(self, argv, read=None):
        parser = build_parser()
        args = parser.parse_args(argv)
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = run_activity(
                args,
                parser,
                read=read or (lambda prompt: ""),
                print=print,
            )
        return code, captured.getvalue()

    def _edit(self, *options, read=None):
        return self._run(
            [
                "activity",
                "--database",
                str(self.database),
                "edit",
                "a1",
                *options,
            ],
            read=read,
        )

    def _value(self, column):
        return self.conn.execute(
            f"SELECT {column} FROM activities WHERE id = 'a1'"
        ).fetchone()[0]

    def _star(self, field):
        return self.conn.execute(
            """
            SELECT source, is_manual, value_json FROM activity_field_sources
            WHERE activity_id = 'a1' AND field_name = ?
            """,
            (field,),
        ).fetchone()

    def _manual(self, field):
        return self.conn.execute(
            """
            SELECT value_json FROM activity_manual_fields
            WHERE activity_id = 'a1' AND field_name = ?
            """,
            (field,),
        ).fetchone()

    def _edit_log(self):
        return self.conn.execute(
            "SELECT * FROM edit_log ORDER BY id"
        ).fetchall()

    # -- scalar writes ----------------------------------------------------

    def test_scalar_flags_write_manual_provenance(self):
        code, output = self._edit(
            "--name", "Evening run",
            "--description", "Steady",
            "--rpe", "8",
            "--feel", "2",
            "--sub-sport", "trail",
        )

        self.assertEqual(0, code)
        self.assertIn("set name: Morning run → Evening run (manual)", output)
        self.assertIn("set sub_sport: - → trail (manual)", output)
        self.assertEqual("Evening run", self._value("name"))
        self.assertEqual("Steady", self._value("description"))
        self.assertEqual(8.0, self._value("rpe"))
        self.assertEqual(2, self._value("feel"))
        self.assertEqual("trail", self._value("sub_sport"))
        self.assertEqual(1, self._star("name")["is_manual"])
        self.assertEqual(5, len(self._edit_log()))

    def _second_activity(self):
        self.writer.upsert_activity(
            "a2",
            {
                "local_date": "2026-10-01",
                "sport": "run",
                "name": "Evening run",
                "duration_s": 1800,
                "distance_m": 5000,
            },
            source="fit",
            source_record_id=None,
        )
        self.conn.commit()

    def test_selector_accepts_a_unique_name_or_date(self):
        code, _ = self._run(
            [
                "activity", "--database", str(self.database),
                "edit", "Morning run", "--rpe", "7",
            ]
        )
        self.assertEqual(0, code)
        self.assertEqual(7.0, self._value("rpe"))

        code, _ = self._run(
            [
                "activity", "--database", str(self.database),
                "edit", "2026-10-01", "--name", "Morning edit",
            ]
        )
        self.assertEqual(0, code)
        self.assertEqual("Morning edit", self._value("name"))

    def test_ambiguous_selector_with_flags_errors(self):
        self._second_activity()
        with self.assertRaises(SystemExit):
            self._run(
                [
                    "activity", "--database", str(self.database),
                    "edit", "run", "--rpe", "7",
                ]
            )

    def test_interactive_ambiguous_selector_prompts(self):
        self._second_activity()
        answers = iter(["2"] + [""] * 12)

        def read(prompt):
            try:
                return next(answers)
            except StopIteration:
                return ""

        code, output = self._run(
            [
                "activity", "--database", str(self.database),
                "edit", "run",
            ],
            read=read,
        )

        self.assertEqual(0, code)
        self.assertIn("Matched several records", output)
        self.assertIn("Nothing to change.", output)

    def test_history_by_name(self):
        self._edit("--rpe", "7")

        code, output = self._run(
            [
                "activity", "--database", str(self.database),
                "edit", "Morning run", "--history",
            ]
        )

        self.assertEqual(0, code)
        self.assertIn("rpe", output)

    def test_manual_edit_survives_a_reimport(self):
        self._edit("--name", "Edited name", "--sub-sport", "trail")

        self.writer.upsert_activity(
            "a1",
            {"name": "Imported name", "sub_sport": "road"},
            source="fit",
            source_record_id=self.source_id,
        )
        self.conn.commit()

        self.assertEqual("Edited name", self._value("name"))
        self.assertEqual("trail", self._value("sub_sport"))
        self.assertEqual(1, self._star("name")["is_manual"])
        self.assertEqual(1, self._star("sub_sport")["is_manual"])

    def test_clear_removes_value_and_manual_ownership(self):
        self._edit("--sub-sport", "trail")
        self.assertIsNotNone(self._manual("sub_sport"))

        code, output = self._edit("--clear", "sub-sport")

        self.assertEqual(0, code)
        self.assertIn("set sub_sport: trail → - (manual)", output)
        self.assertIsNone(self._value("sub_sport"))
        self.assertIsNone(self._manual("sub_sport"))
        self.assertIsNone(self._star("sub_sport"))

    def test_clear_restores_the_source_snapshot(self):
        self._edit("--name", "Edited name")

        code, output = self._edit("--clear", "name")

        self.assertEqual(0, code)
        self.assertIn("set name: Edited name → Morning run (manual)", output)
        self.assertEqual("Morning run", self._value("name"))
        self.assertIsNone(self._manual("name"))
        self.assertEqual(0, self._star("name")["is_manual"])

    def test_dry_run_writes_nothing(self):
        code, output = self._edit("--name", "Draft", "--dry-run")

        self.assertEqual(0, code)
        self.assertIn("Dry run", output)
        self.assertEqual("Morning run", self._value("name"))
        self.assertIsNone(self._manual("name"))
        self.assertEqual([], self._edit_log())

    # -- history ----------------------------------------------------------

    def test_history_shows_the_prior_value_and_resolved_items(self):
        item_id = self.writer.record_review_item(
            category="field_conflict",
            detail="duration differs",
            context={"rule": "field_conflict", "field": "duration_s"},
            fingerprint="fp-history",
            activity_id="a1",
        )[0]
        self.conn.commit()

        self._edit("--duration", "46:00", "--item", str(item_id))
        code, output = self._run(
            [
                "activity",
                "--database",
                str(self.database),
                "edit",
                "a1",
                "--history",
            ]
        )

        self.assertEqual(0, code)
        self.assertIn("duration_s: 1:00:00 → 46:00", output)
        self.assertIn("[activity-edit]", output)
        self.assertIn(f"resolved review item(s) #{item_id}", output)

    # -- quality ----------------------------------------------------------

    def test_quality_findings_print_after_an_edit(self):
        code, output = self._edit("--duration", "600")

        self.assertEqual(0, code)
        self.assertIn("quality: still flagged", output)
        self.assertIn("implied_pace", output)
        item = self.conn.execute(
            """
            SELECT detail FROM review_items
            WHERE category = 'quality' AND activity_id = 'a1'
              AND status = 'open'
            """
        ).fetchone()
        self.assertIsNotNone(item)

    # -- sets -------------------------------------------------------------

    def test_sets_replace_as_whole_sets(self):
        self.writer.replace_activity_tags(
            "a1", ["race"], source="runalyze"
        )
        self.writer.replace_activity_workout_methods(
            "a1", ["continuous"], source="intervals"
        )
        self.writer.replace_activity_workout_targets(
            "a1", ["base"], source="intervals"
        )
        self.conn.commit()

        code, output = self._edit(
            "--tag", "key",
            "--tag", "morning",
            "--method", "intervals",
            "--target", "threshold",
            "--target", "vo2max",
        )

        self.assertEqual(0, code)
        self.assertIn("set methods: continuous → intervals (manual)", output)
        tags = [
            tuple(row)
            for row in self.conn.execute(
                "SELECT tag, source, is_manual FROM activity_tags "
                "WHERE activity_id = 'a1' ORDER BY tag"
            )
        ]
        self.assertEqual(
            [
                ("key", "manual", 1),
                ("morning", "manual", 1),
                ("race", "runalyze", 0),
            ],
            tags,
        )
        methods = [
            row[0]
            for row in self.conn.execute(
                "SELECT method FROM activity_workout_methods "
                "WHERE activity_id = 'a1' ORDER BY method"
            )
        ]
        self.assertEqual(["intervals"], methods)
        targets = [
            row[0]
            for row in self.conn.execute(
                "SELECT target FROM activity_workout_targets "
                "WHERE activity_id = 'a1' ORDER BY target"
            )
        ]
        self.assertEqual(["threshold", "vo2max"], targets)

        self._edit("--tag", "other")
        tags = [
            tuple(row)
            for row in self.conn.execute(
                "SELECT tag, source, is_manual FROM activity_tags "
                "WHERE activity_id = 'a1' ORDER BY tag"
            )
        ]
        self.assertEqual(
            [("other", "manual", 1), ("race", "runalyze", 0)],
            tags,
        )

    def test_equipment_replaces_the_manual_links(self):
        self.writer.upsert_equipment("e1", type="shoe", name="Daily")
        self.writer.upsert_equipment("e2", type="shoe", name="Race")
        self.conn.commit()

        self._edit("--equipment", "e1")
        self.assertEqual(
            [("e1", "primary")],
            [
                tuple(row)
                for row in self.conn.execute(
                    "SELECT equipment_id, role FROM activity_equipment "
                    "WHERE activity_id = 'a1'"
                )
            ],
        )

        self._edit("--equipment", "e2")
        self.assertEqual(
            [("e2", "primary")],
            [
                tuple(row)
                for row in self.conn.execute(
                    "SELECT equipment_id, role FROM activity_equipment "
                    "WHERE activity_id = 'a1'"
                )
            ],
        )

    # -- review-item lifecycle -------------------------------------------

    def test_item_less_edit_closes_only_the_touched_field_conflict(self):
        touched = self.writer.record_review_item(
            category="field_conflict",
            detail="duration differs",
            context={"rule": "field_conflict", "field": "duration_s"},
            fingerprint="fp-duration",
            activity_id="a1",
        )[0]
        untouched = self.writer.record_review_item(
            category="field_conflict",
            detail="distance differs",
            context={"rule": "field_conflict", "field": "distance_m"},
            fingerprint="fp-distance",
            activity_id="a1",
        )[0]
        self.conn.commit()

        code, output = self._edit("--duration", "46:00")

        self.assertEqual(0, code)
        self.assertIn(f"resolved #{touched}", output)
        self.assertEqual(
            "resolved", self.writer.review_item(touched)["status"]
        )
        self.assertEqual(
            "open", self.writer.review_item(untouched)["status"]
        )

    def test_classification_edit_closes_the_classification_item(self):
        item_id = self.writer.record_review_item(
            category="workout_classification",
            detail="no decided method",
            context={},
            fingerprint="fp-classification",
            activity_id="a1",
            severity="info",
        )[0]
        self.conn.commit()

        code, output = self._edit("--method", "intervals")

        self.assertEqual(0, code)
        self.assertIn(f"resolved #{item_id}", output)
        self.assertEqual(
            "resolved", self.writer.review_item(item_id)["status"]
        )

    def test_item_flag_still_resolves_an_explicit_item(self):
        item_id = self.writer.record_review_item(
            category="manual_flag",
            detail="look at this",
            fingerprint="fp-flag",
            activity_id="a1",
        )[0]
        self.conn.commit()

        code, output = self._edit("--name", "Checked", "--item", str(item_id))

        self.assertEqual(0, code)
        self.assertIn(f"resolved #{item_id}", output)
        self.assertEqual(
            "resolved", self.writer.review_item(item_id)["status"]
        )

    # -- interactive ------------------------------------------------------

    def test_empty_interactive_answers_keep_current_values(self):
        code, output = self._edit()

        self.assertEqual(0, code)
        self.assertIn("Nothing to change.", output)
        self.assertEqual("Morning run", self._value("name"))
        self.assertEqual([], self._edit_log())

    def test_interactive_changes_use_the_current_value_as_default(self):
        answers = iter(
            [
                "Evening run",  # name
                "",  # description
                "",  # sport
                "trail",  # sub_sport
                "7",  # rpe
                "",  # feel
                "",  # duration
                "",  # distance
                "",  # tags
                "",  # methods
                "",  # targets
                "",  # equipment
            ]
        )
        prompts = []

        def read(prompt):
            prompts.append(prompt)
            return next(answers)

        code, output = self._edit(read=read)

        self.assertEqual(0, code)
        self.assertIn("set name: Morning run → Evening run (manual)", output)
        self.assertIn("set sub_sport: - → trail (manual)", output)
        self.assertIn("set rpe: 5 → 7 (manual)", output)
        self.assertEqual("Evening run", self._value("name"))
        self.assertEqual("trail", self._value("sub_sport"))
        self.assertEqual(7.0, self._value("rpe"))
        self.assertTrue(any("[Morning run]" in prompt for prompt in prompts))


if __name__ == "__main__":
    unittest.main()
