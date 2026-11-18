import json
import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.quality import AMBIGUOUS_EQUIPMENT
from hobbyjogging_import.runalyze_gear import (
    RunalyzeGearImporter,
    format_gear_summary,
)


class RunalyzeGearTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")

    def _activity(self, activity_id, local_date="2026-01-01"):
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": local_date,
                "started_at_utc": f"{local_date}T06:00:00Z",
                "sport": "run",
                "name": "Run",
                "duration_s": 3600,
                "elapsed_s": 3600,
                "distance_m": 10000,
            },
            source="fit",
            source_record_id=None,
        )

    def _gear(
        self,
        gear_id,
        name,
        category_id=78697,
        *,
        date_start=None,
        date_end=None,
        notes="",
    ):
        return {
            "id": gear_id,
            "name": name,
            "category_id": category_id,
            "date_start": date_start,
            "date_end": date_end,
            "notes": notes,
        }

    def _runalyze(self, activity_id, items):
        payload = {
            "id": int(activity_id.lstrip("a") or 1),
            "equipment": items,
            "edited_at": 1,
        }
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

    def _equipment(self, equipment_id, name, *, type="shoe"):
        self.writer.upsert_equipment(
            equipment_id,
            type=type,
            name=name,
        )

    def _sheet_link(self, activity_id, equipment_id, *, role="primary"):
        self.writer.link_activity_equipment(
            activity_id,
            equipment_id,
            source="sheet",
            role=role,
        )

    def _import(self, **kwargs):
        return RunalyzeGearImporter(self.conn).import_gear(**kwargs)

    def _links(self, activity_id=None):
        sql = (
            "SELECT activity_id, equipment_id, role, source, is_manual "
            "FROM activity_equipment"
        )
        params = []
        if activity_id is not None:
            sql += " WHERE activity_id = ?"
            params.append(activity_id)
        sql += " ORDER BY activity_id, role, equipment_id"
        return [
            tuple(row)
            for row in self.conn.execute(sql, params)
        ]

    def _equipment_row(self, equipment_id):
        return self.conn.execute(
            "SELECT * FROM equipment WHERE id = ?",
            (equipment_id,),
        ).fetchone()

    def _gear_source_link(self, gear_id):
        return self.conn.execute(
            """
            SELECT esl.equipment_id
            FROM equipment_source_links esl
            JOIN source_records sr ON sr.id = esl.source_record_id
            WHERE sr.source = 'runalyze'
              AND sr.record_type = 'gear'
              AND sr.external_id = ?
            """,
            (f"runalyze:{gear_id}",),
        ).fetchone()

    # -- new rows -----------------------------------------------------------

    def test_creates_a_new_row_with_dates_notes_and_a_primary_link(self):
        self._activity("a1")
        self._runalyze(
            "a1",
            [
                self._gear(
                    1,
                    "Lunge Neo Run (blau)",
                    date_start="2025-06-18",
                    notes="Gr. 10",
                )
            ],
        )

        summary = self._import()

        self.assertEqual(1, summary.created)
        row = self._equipment_row("runalyze:equipment:1")
        self.assertEqual("Lunge Neo Run (blau)", row["name"])
        self.assertEqual("shoe", row["type"])
        self.assertEqual("2025-06-18", row["acquired_on"])
        self.assertEqual("Gr. 10", row["notes"])
        self.assertEqual("", row["brand"])
        self.assertEqual("", row["model"])
        self.assertEqual(
            [("a1", "runalyze:equipment:1", "primary", "runalyze", 0)],
            self._links(),
        )
        linked = self._gear_source_link(1)
        self.assertEqual("runalyze:equipment:1", linked["equipment_id"])

    def test_first_shoe_is_primary_and_the_second_secondary(self):
        self._activity("a1")
        self._runalyze(
            "a1",
            [
                self._gear(1, "Shoe One"),
                self._gear(2, "Shoe Two"),
            ],
        )

        self._import()

        self.assertEqual(
            [
                ("a1", "runalyze:equipment:1", "primary", "runalyze", 0),
                ("a1", "runalyze:equipment:2", "secondary", "runalyze", 0),
            ],
            self._links(),
        )

    def test_sheet_primary_is_preserved_and_the_gear_becomes_secondary(self):
        self._equipment("sheet:equipment:9", "Sheet Shoe")
        self._activity("a1")
        self._sheet_link("a1", "sheet:equipment:9")
        self._runalyze("a1", [self._gear(1, "Lunge Neo Run (blau)")])

        self._import()

        self.assertEqual(
            [
                ("a1", "sheet:equipment:9", "primary", "sheet", 0),
                ("a1", "runalyze:equipment:1", "secondary", "runalyze", 0),
            ],
            self._links(),
        )

    def test_manual_link_is_not_duplicated(self):
        self._equipment("manual:shoe", "Demo Shoe")
        self._activity("a1")
        self.writer.link_activity_equipment(
            "a1",
            "manual:shoe",
            source="manual",
            is_manual=True,
        )
        self._runalyze("a1", [self._gear(1, "demo shoe")])

        summary = self._import()

        self.assertEqual(1, summary.linked_existing)
        self.assertEqual(1, summary.skipped_links)
        self.assertEqual(
            [("a1", "manual:shoe", "primary", "manual", 1)],
            self._links(),
        )
        self.assertEqual(
            "manual:shoe",
            self._gear_source_link(1)["equipment_id"],
        )

    # -- identity -----------------------------------------------------------

    def test_co_occurrence_links_a_gear_to_the_sheet_shoe(self):
        self._equipment("sheet:equipment:5", "Lunge C-Dur")
        for activity_id in ("a1", "a2", "a3"):
            self._activity(activity_id)
            self._sheet_link(activity_id, "sheet:equipment:5")
            self._runalyze(
                activity_id,
                [self._gear(10, "Lunge classic run (rot)")],
            )

        summary = self._import()

        self.assertEqual(1, summary.linked_existing)
        self.assertEqual(0, summary.created)
        self.assertEqual(
            "sheet:equipment:5",
            self._gear_source_link(10)["equipment_id"],
        )
        self.assertEqual(
            3,
            self.conn.execute(
                "SELECT COUNT(*) FROM activity_equipment"
            ).fetchone()[0],
        )

    def test_split_co_occurrence_is_ambiguous(self):
        self._equipment("sheet:equipment:5", "Lunge C-Dur A")
        self._equipment("sheet:equipment:6", "Lunge C-Dur B")
        for index, equipment_id in enumerate(
            ("sheet:equipment:5", "sheet:equipment:5",
             "sheet:equipment:6", "sheet:equipment:6"),
            start=1,
        ):
            activity_id = f"a{index}"
            self._activity(activity_id)
            self._sheet_link(activity_id, equipment_id)
            self._runalyze(activity_id, [self._gear(11, "Split Gear")])

        summary = self._import()

        self.assertEqual(1, summary.ambiguous)
        self.assertEqual(0, summary.linked_existing)
        self.assertIsNone(self._gear_source_link(11))
        item = self.conn.execute(
            "SELECT * FROM review_items WHERE category = ?",
            (AMBIGUOUS_EQUIPMENT,),
        ).fetchone()
        self.assertIsNotNone(item)
        candidates = json.loads(item["context_json"])["candidates"]
        self.assertEqual(2, len(candidates))
        self.assertEqual(
            {"sheet:equipment:5", "sheet:equipment:6"},
            {candidate["equipment_id"] for candidate in candidates},
        )

    def test_unique_normalized_name_links_an_existing_row(self):
        self._equipment("manual:shoe", "Demo Shoe")
        self._activity("a1")
        self._runalyze("a1", [self._gear(1, "demo_shoe")])

        summary = self._import()

        self.assertEqual(1, summary.linked_existing)
        self.assertIsNotNone(self._equipment_row("manual:shoe"))
        self.assertIsNone(
            self._equipment_row("runalyze:equipment:1")
        )
        self.assertEqual(
            "manual:shoe",
            self._gear_source_link(1)["equipment_id"],
        )

    def test_several_name_matches_are_ambiguous(self):
        self._equipment("sheet:equipment:5", "Lunge C-Dur")
        self._equipment("sheet:equipment:6", "Lunge C-Dur")
        self._activity("a1")
        self._runalyze("a1", [self._gear(1, "Lunge C-Dur")])

        summary = self._import()

        self.assertEqual(1, summary.ambiguous)
        self.assertIsNone(self._gear_source_link(1))
        item = self.conn.execute(
            "SELECT * FROM review_items WHERE category = ?",
            (AMBIGUOUS_EQUIPMENT,),
        ).fetchone()
        self.assertIsNotNone(item)

    def test_bike_and_other_categories_map_to_types(self):
        self._activity("a1")
        self._runalyze(
            "a1",
            [
                self._gear(20, "Rennrad", category_id=78699),
                self._gear(21, "Thule", category_id=379240),
            ],
        )

        self._import()

        self.assertEqual(
            "bike", self._equipment_row("runalyze:equipment:20")["type"]
        )
        self.assertEqual(
            "other", self._equipment_row("runalyze:equipment:21")["type"]
        )

    def test_clothing_is_skipped(self):
        self._activity("a1")
        self._runalyze(
            "a1",
            [
                self._gear(30, "Laufshirt", category_id=78698),
                self._gear(31, "Lunge Neo Run (blau)"),
            ],
        )

        summary = self._import()

        self.assertEqual(1, summary.skipped_clothing)
        self.assertEqual(1, summary.created)
        self.assertIsNone(self._equipment_row("runalyze:equipment:30"))
        self.assertIsNotNone(self._equipment_row("runalyze:equipment:31"))
        self.assertEqual(1, summary.activity_links)

    def test_parenthetical_is_stripped_for_a_unique_match(self):
        # Runalyze tracks gear from 2023 on, so its colour parenthetical is the
        # only difference from the sheet names before that.
        self._equipment("sheet:equipment:7", "Lunge Fis")
        self._activity("a1")
        self._runalyze("a1", [self._gear(7, "Lunge Fis (dunkelblau)")])

        summary = self._import()

        self.assertEqual(1, summary.linked_existing)
        self.assertIsNone(self._equipment_row("runalyze:equipment:7"))
        self.assertEqual(
            "sheet:equipment:7",
            self._gear_source_link(7)["equipment_id"],
        )

    def test_parenthetical_keeps_two_sheet_rows_ambiguous(self):
        self._equipment("sheet:equipment:5", "Lunge C-Dur")
        self._equipment("sheet:equipment:6", "Lunge C-Dur")
        self._activity("a1")
        self._runalyze("a1", [self._gear(9, "Lunge C-Dur (rot)")])

        summary = self._import()

        self.assertEqual(1, summary.ambiguous)
        self.assertEqual(0, summary.created)
        item = self.conn.execute(
            "SELECT context_json FROM review_items WHERE category = ?",
            (AMBIGUOUS_EQUIPMENT,),
        ).fetchone()
        candidates = json.loads(item["context_json"])["candidates"]
        self.assertEqual(
            {"sheet:equipment:5", "sheet:equipment:6"},
            {candidate["equipment_id"] for candidate in candidates},
        )

    def test_acquired_date_breaks_a_same_name_tie(self):
        # Same name, different colour: Runalyze's date_start is the
        # acquisition date, which the sheet records as acquired_on.
        self.writer.upsert_equipment(
            "sheet:equipment:5",
            type="shoe",
            name="Lunge C-Dur",
            acquired_on="2016-03-25",
            notes="Farbe rot",
        )
        self.writer.upsert_equipment(
            "sheet:equipment:6",
            type="shoe",
            name="Lunge C-Dur",
            acquired_on="2018-04-09",
            notes="Farbe schwarz",
        )
        self._activity("a1")
        self._runalyze(
            "a1",
            [self._gear(9, "Lunge C-Dur (rot)", date_start="2016-03-25")],
        )

        summary = self._import()

        self.assertEqual(1, summary.linked_existing)
        self.assertEqual(0, summary.ambiguous)
        self.assertEqual(
            "sheet:equipment:5",
            self._gear_source_link(9)["equipment_id"],
        )

    def test_acquired_date_that_matches_no_row_stays_ambiguous(self):
        self.writer.upsert_equipment(
            "sheet:equipment:5",
            type="shoe",
            name="Lunge C-Dur",
            acquired_on="2016-04-01",
        )
        self.writer.upsert_equipment(
            "sheet:equipment:6",
            type="shoe",
            name="Lunge C-Dur",
            acquired_on="2018-04-09",
        )
        self._activity("a1")
        self._runalyze(
            "a1",
            [self._gear(9, "Lunge C-Dur (rot)", date_start="2016-03-25")],
        )

        summary = self._import()

        self.assertEqual(1, summary.ambiguous)
        self.assertEqual(0, summary.linked_existing)
        self.assertIsNone(self._gear_source_link(9))

    def test_payloads_from_two_gear_records_stay_separate(self):
        self._activity("a1")
        self._runalyze(
            "a1",
            [
                self._gear(1, "Lunge C-Dur (schwarz)"),
                self._gear(2, "Lunge C-Dur (rot)"),
            ],
        )

        summary = self._import()

        self.assertEqual(2, summary.created)
        self.assertIsNotNone(self._equipment_row("runalyze:equipment:1"))
        self.assertIsNotNone(self._equipment_row("runalyze:equipment:2"))

    def test_an_importer_duplicate_is_reconciled_onto_the_sheet_row(self):
        self._activity("a1")
        self._runalyze("a1", [self._gear(1, "Lunge Neo Run (grau)")])
        self._import()
        self.assertIsNotNone(self._equipment_row("runalyze:equipment:1"))

        self._equipment("sheet:equipment:10", "Lunge Neo Run")
        summary = self._import()

        self.assertEqual(1, summary.reconciled)
        self.assertIsNone(self._equipment_row("runalyze:equipment:1"))
        self.assertIsNotNone(self._equipment_row("sheet:equipment:10"))
        self.assertEqual(
            "sheet:equipment:10",
            self._gear_source_link(1)["equipment_id"],
        )
        self.assertEqual(
            [
                ("a1", "sheet:equipment:10", "primary", "runalyze", 0),
            ],
            self._links(),
        )

    def test_reconciliation_keeps_a_sheet_primary(self):
        self._equipment("sheet:equipment:11", "Old Shoe")
        self._activity("a1")
        self._sheet_link("a1", "sheet:equipment:11")
        self._runalyze("a1", [self._gear(1, "Lunge Neo Run (grau)")])
        self._import()

        self._equipment("sheet:equipment:10", "Lunge Neo Run")
        summary = self._import()

        self.assertEqual(1, summary.reconciled)
        self.assertEqual(
            [
                ("a1", "sheet:equipment:11", "primary", "sheet", 0),
                ("a1", "sheet:equipment:10", "secondary", "runalyze", 0),
            ],
            self._links(),
        )

    def test_a_manual_link_blocks_reconciliation(self):
        self._activity("a1")
        self._runalyze("a1", [self._gear(1, "Demo Shoe (blau)")])
        self._import()
        # A human confirming the importer's row makes it human-owned.
        self.writer.link_activity_equipment(
            "a1",
            "runalyze:equipment:1",
            source="manual",
            is_manual=True,
        )
        self._equipment("manual:shoe", "Demo Shoe")

        summary = self._import()

        self.assertEqual(0, summary.reconciled)
        self.assertIsNotNone(self._equipment_row("runalyze:equipment:1"))
        self.assertEqual(
            "runalyze:equipment:1",
            self._gear_source_link(1)["equipment_id"],
        )

    # -- idempotency and dry run -------------------------------------------

    def test_reimport_is_idempotent(self):
        self._activity("a1")
        self._runalyze("a1", [self._gear(1, "Lunge Neo Run (blau)")])

        first = self._import()
        second = self._import()

        self.assertEqual(1, first.created)
        self.assertEqual(0, second.created)
        self.assertEqual(1, second.already_linked)
        self.assertEqual(0, second.activity_links)
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM equipment"
            ).fetchone()[0],
        )
        self.assertEqual(1, len(self._links()))

    def test_dry_run_writes_nothing(self):
        self._activity("a1")
        self._runalyze("a1", [self._gear(1, "Lunge Neo Run (blau)")])

        summary = self._import(dry_run=True)

        self.assertEqual(1, summary.created)
        self.assertEqual(1, summary.activity_links)
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM equipment"
            ).fetchone()[0],
        )
        self.assertEqual([], self._links())
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records "
                "WHERE source = 'runalyze' AND record_type = 'gear'"
            ).fetchone()[0],
        )

    def test_writes_the_ambiguous_report(self):
        self._equipment("sheet:equipment:5", "Lunge C-Dur")
        self._equipment("sheet:equipment:6", "Lunge C-Dur")
        self._activity("a1")
        self._runalyze("a1", [self._gear(1, "Lunge C-Dur")])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ambiguous.json"
            self._import(output=output)
            payload = json.loads(output.read_text("utf-8"))

        self.assertEqual(1, len(payload["ambiguous"]))
        self.assertEqual(
            "runalyze:1",
            payload["ambiguous"][0]["gear_external_id"],
        )

    def test_summary_format(self):
        self._activity("a1")
        self._runalyze("a1", [self._gear(1, "Lunge Neo Run (blau)")])

        summary = self._import(dry_run=True)

        text = format_gear_summary(summary)
        self.assertIn("Runalyze gear dry run", text)
        self.assertIn("created: 1", text)
        self.assertIn("activity links: 1", text)


class RunalyzeGearCliTests(unittest.TestCase):

    def test_parser_accepts_gear_options(self):
        args = build_parser().parse_args(
            [
                "runalyze",
                "gear",
                "--dry-run",
                "--limit",
                "5",
                "--output",
                "/tmp/gear.json",
            ]
        )

        self.assertEqual("runalyze", args.command)
        self.assertEqual("gear", args.runalyze_action)
        self.assertTrue(args.dry_run)
        self.assertEqual(5, args.limit)
        self.assertEqual(Path("/tmp/gear.json"), args.output)


if __name__ == "__main__":
    unittest.main()
