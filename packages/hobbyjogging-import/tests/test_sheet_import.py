import contextlib
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_core import (
    TrainingRepository,
    TrainingWriter,
    connect,
    migrate,
    open_database,
)
from hobbyjogging_import.cli import build_parser, run_sheet
from hobbyjogging_import.sheet_import import SheetImporter

from ods_fixture import write_ods

ROHDATEN_HEADER = [
    "Datum",
    "Startzeit",
    "Streckennummer",
    "Strecke",
    "Distanz in m",
    "Zeit",
    "m bergauf",
    "d. km/h",
    "km Schnitt",
    "d. Hf",
    "max. Hf",
    "Schrittfrequenz",
    "Bodenkontaktzeit",
    "Bodenkontaktbalance (50-R %)",
    "Vertikale Oszillation",
    "Horizontal/Vertikal",
    "Temperatur in °C",
    "Meter/Pulsschlag",
    "Gewicht nachher",
    "Trainigstyp",
    "Trainingsgebiet",
    "Schuhe",
    "Beschreibung",
    "Gmap Pedometer Link",
]

ALTERNATIV_HEADER = [
    "Datum",
    "Uhrzeit",
    "Was",
    "Zeit",
    "Beschreibung",
    "Distanz",
    "Höhenmeter",
    "Puls Durchschnitt",
    "Puls max",
    "Schnitt (km/h)",
    "Strecke",
]

MATERIAL_ROWS = [
    ["Schuhe"],
    [
        "Id",
        "Kaufdatum",
        "Marke",
        "Typ",
        None,
        "Größe",
        "Kaufpreis",
        "gesamt km",
        "Entsorgungsdatum",
        "Bemerkungen",
    ],
    [
        7.0,
        "9.4.2018",
        "Asics",
        "GT-2000 4",
        "blau",
        42.5,
        140.0,
        1197.8656,
        "9.4.2018",
        "Testschuh",
    ],
    [8.0, "14.3.2020", "Brooks", "Adrenaline 20", None, 43.0, 140.0, 10.0],
]


def _rohdaten_rows(rows):
    return [ROHDATEN_HEADER] + [
        [row.get(header) for header in ROHDATEN_HEADER] for row in rows
    ]


def _alternativ_rows(rows):
    return [ALTERNATIV_HEADER] + [
        [row.get(header) for header in ALTERNATIV_HEADER] for row in rows
    ]


class SheetImportTestCase(unittest.TestCase):

    def setUp(self):
        self.connection = connect(":memory:")
        self.addCleanup(self.connection.close)
        migrate(self.connection)
        self.writer = TrainingWriter(self.connection)
        self.repository = TrainingRepository(self.connection)
        self.importer = SheetImporter(self.connection)

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "book.ods"

    def _write(self, sheets):
        return write_ods(self.path, sheets)

    def _activities(self):
        return self.connection.execute(
            "SELECT * FROM activities ORDER BY local_date, id"
        ).fetchall()

    def _seed_fit_activity(self, **values):
        run_id = self.writer.start_import_run("fit")
        source_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id="fit-1",
            checksum="c",
            import_run_id=run_id,
        )
        payload = {
            "local_date": "2019-01-23",
            "started_at_utc": "2019-01-23T16:00:05Z",
            "tz_offset_min": 60,
            "sport": "run",
            "duration_s": 3900,
            "elapsed_s": 3900,
            "distance_m": 13710,
            "avg_hr": 142,
        }
        payload.update(values)
        self.writer.upsert_activity(
            "fit-uuid",
            payload,
            source="fit",
            source_record_id=source_id,
        )
        return source_id


class RohdatenImportTests(SheetImportTestCase):

    def test_imports_run_with_tags_equipment_and_payload(self):
        self._write(
            [
                ("Material", MATERIAL_ROWS),
                (
                    "Rohdaten",
                    _rohdaten_rows(
                        [
                            {
                                "Datum": date(2019, 1, 23),
                                "Startzeit": timedelta(hours=17),
                                "Strecke": "Liesingbachrunde",
                                "Distanz in m": 13710.0,
                                "Zeit": timedelta(minutes=65, seconds=29),
                                "d. Hf": 142.0,
                                "max. Hf": 168.0,
                                "Trainigstyp": "ll",
                                "Trainingsgebiet": "w",
                                "Schuhe": 7.0,
                                "Beschreibung": "Locker",
                            }
                        ]
                    ),
                ),
            ]
        )

        self.importer.import_sheet(self.path, "Material")
        summary = self.importer.import_sheet(self.path, "Rohdaten")

        self.assertEqual(1, summary.activities_created)
        self.assertEqual(1, summary.activities_imported)
        self.assertEqual(2, summary.tags_written)
        self.assertEqual(1, summary.equipment_linked)

        activity = self._activities()[0]
        self.assertEqual("2019-01-23", activity["local_date"])
        self.assertEqual("2019-01-23T16:00:00Z", activity["started_at_utc"])
        self.assertEqual(60, activity["tz_offset_min"])
        self.assertEqual(3929, activity["duration_s"])
        self.assertEqual(3929, activity["elapsed_s"])
        self.assertEqual(13710, activity["distance_m"])
        self.assertEqual(142, activity["avg_hr"])
        self.assertEqual("Liesingbachrunde", activity["name"])

        tags = self.connection.execute(
            """
            SELECT tag FROM activity_tags
            WHERE activity_id = ? AND source = 'sheet'
            ORDER BY tag
            """,
            (activity["id"],),
        ).fetchall()
        self.assertEqual(["ll", "w"], [row["tag"] for row in tags])

        link = self.connection.execute(
            """
            SELECT equipment_id, source FROM activity_equipment
            WHERE activity_id = ?
            """,
            (activity["id"],),
        ).fetchone()
        self.assertEqual("sheet:equipment:7", link["equipment_id"])
        self.assertEqual("sheet", link["source"])

        payload = self.connection.execute(
            """
            SELECT payload_json FROM source_records
            WHERE source = 'sheet' AND record_type = 'activity'
            """
        ).fetchone()["payload_json"]
        self.assertIn('"max. Hf":168.0', payload)
        self.assertIn('"sheet":"Rohdaten"', payload)

    def test_matches_existing_activity_without_touching_its_start_time(self):
        self._seed_fit_activity()
        self._write(
            [
                (
                    "Rohdaten",
                    _rohdaten_rows(
                        [
                            {
                                "Datum": date(2019, 1, 23),
                                "Startzeit": timedelta(hours=17),
                                "Distanz in m": 14500.0,
                                "Zeit": timedelta(minutes=65),
                                "d. Hf": 142.0,
                            }
                        ]
                    ),
                )
            ]
        )

        summary = self.importer.import_sheet(self.path, "Rohdaten")

        self.assertEqual(0, summary.activities_created)
        self.assertEqual(1, summary.activities_matched)
        self.assertEqual(1, len(self._activities()))

        activity = self._activities()[0]
        # The sheet logs minutes; FIT's precise start keeps ownership.
        self.assertEqual("2019-01-23T16:00:05Z", activity["started_at_utc"])

        conflicts = self.connection.execute(
            """
            SELECT context_json FROM review_items
            WHERE category = 'field_conflict'
            """
        ).fetchall()
        fields = {
            json.loads(row["context_json"])["field"]
            for row in conflicts
        }
        self.assertEqual({"distance_m"}, fields)

    def test_rows_without_start_time_create_dated_activities(self):
        self._seed_fit_activity()
        self._write(
            [
                (
                    "Rohdaten",
                    _rohdaten_rows(
                        [
                            {
                                "Datum": date(2019, 1, 23),
                                "Distanz in m": 5000.0,
                                "Zeit": timedelta(minutes=30),
                            }
                        ]
                    ),
                )
            ]
        )

        summary = self.importer.import_sheet(self.path, "Rohdaten")

        self.assertEqual(1, summary.activities_created)
        self.assertEqual(2, len(self._activities()))
        created = self.connection.execute(
            """
            SELECT started_at_utc FROM activities
            WHERE id NOT IN ('fit-uuid')
            """
        ).fetchone()
        self.assertIsNone(created["started_at_utc"])

    def test_duplicate_rows_get_distinct_external_ids(self):
        self._write(
            [
                (
                    "Rohdaten",
                    _rohdaten_rows(
                        [
                            {
                                "Datum": date(2020, 5, 1),
                                "Distanz in m": 5000.0,
                                "Zeit": timedelta(minutes=30),
                            },
                            {
                                "Datum": date(2020, 5, 1),
                                "Distanz in m": 8000.0,
                                "Zeit": timedelta(minutes=45),
                            },
                        ]
                    ),
                )
            ]
        )

        summary = self.importer.import_sheet(self.path, "Rohdaten")

        self.assertEqual(2, summary.activities_created)
        external_ids = self.connection.execute(
            """
            SELECT external_id FROM source_records
            WHERE source = 'sheet' AND record_type = 'activity'
            ORDER BY external_id
            """
        ).fetchall()
        self.assertEqual(2, len(external_ids))
        self.assertEqual(2, len({row["external_id"] for row in external_ids}))
        self.assertTrue(
            any("|" in row["external_id"] for row in external_ids)
        )

    def test_dry_run_writes_nothing(self):
        self._write(
            [
                (
                    "Rohdaten",
                    _rohdaten_rows(
                        [
                            {
                                "Datum": date(2019, 1, 23),
                                "Startzeit": timedelta(hours=17),
                                "Distanz in m": 13710.0,
                                "Zeit": timedelta(minutes=65),
                            }
                        ]
                    ),
                )
            ]
        )

        summary = self.importer.import_sheet(
            self.path,
            "Rohdaten",
            dry_run=True,
        )

        self.assertTrue(summary.dry_run)
        self.assertIsNone(summary.run_id)
        self.assertEqual(1, summary.activities_created)
        self.assertEqual(0, len(self._activities()))
        self.assertEqual(
            0,
            self.connection.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            self.connection.execute(
                "SELECT COUNT(*) FROM import_runs"
            ).fetchone()[0],
        )

    def test_limit_and_date_filter(self):
        self._write(
            [
                (
                    "Rohdaten",
                    _rohdaten_rows(
                        [
                            {
                                "Datum": day,
                                "Distanz in m": 5000.0,
                                "Zeit": timedelta(minutes=30),
                            }
                            for day in (
                                date(2020, 1, 1),
                                date(2020, 1, 2),
                                date(2020, 1, 3),
                            )
                        ]
                    ),
                )
            ]
        )

        summary = self.importer.import_sheet(
            self.path,
            "Rohdaten",
            start=date(2020, 1, 2),
            limit=1,
        )

        self.assertEqual(1, summary.activities_imported)
        self.assertEqual(1, summary.rows_filtered)
        self.assertEqual(1, summary.rows_limited)
        self.assertEqual(
            ["2020-01-02"],
            [row["local_date"] for row in self._activities()],
        )

    def test_reimport_is_idempotent(self):
        self._write(
            [
                (
                    "Rohdaten",
                    _rohdaten_rows(
                        [
                            {
                                "Datum": date(2019, 1, 23),
                                "Startzeit": timedelta(hours=17),
                                "Distanz in m": 13710.0,
                                "Zeit": timedelta(minutes=65),
                                "Trainigstyp": "ll",
                            }
                        ]
                    ),
                )
            ]
        )

        first = self.importer.import_sheet(self.path, "Rohdaten")
        second = self.importer.import_sheet(self.path, "Rohdaten")

        self.assertEqual(1, first.activities_created)
        self.assertEqual(0, second.activities_created)
        self.assertEqual(1, second.activities_matched)
        self.assertEqual(1, len(self._activities()))
        self.assertEqual(
            1,
            self.connection.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )
        self.assertEqual(
            1,
            self.connection.execute(
                "SELECT COUNT(*) FROM activity_tags"
            ).fetchone()[0],
        )
        self.assertEqual(0, second.review_recorded)

    def test_missing_equipment_is_reported(self):
        self._write(
            [
                (
                    "Rohdaten",
                    _rohdaten_rows(
                        [
                            {
                                "Datum": date(2019, 1, 23),
                                "Distanz in m": 5000.0,
                                "Zeit": timedelta(minutes=30),
                                "Schuhe": 99.0,
                            }
                        ]
                    ),
                )
            ]
        )

        summary = self.importer.import_sheet(self.path, "Rohdaten")

        self.assertEqual(1, summary.equipment_missing)
        self.assertEqual(0, summary.equipment_linked)
        self.assertEqual(
            0,
            self.connection.execute(
                "SELECT COUNT(*) FROM activity_equipment"
            ).fetchone()[0],
        )


class AlternativtrainingImportTests(SheetImportTestCase):

    def test_imports_sports_distance_and_heart_rate(self):
        self._write(
            [
                (
                    "Alternativtraining",
                    _alternativ_rows(
                        [
                            {
                                "Datum": date(2020, 8, 1),
                                "Uhrzeit": timedelta(hours=18),
                                "Was": "Kicken",
                                "Zeit": timedelta(hours=2),
                                "Puls Durchschnitt": 120.0,
                                "Distanz": 1.5,
                            },
                            {
                                "Datum": date(2020, 8, 2),
                                "Uhrzeit": timedelta(hours=18),
                                "Was": "Badminton",
                                "Zeit": timedelta(hours=1),
                            },
                            {
                                "Datum": date(2020, 8, 3),
                                "Uhrzeit": timedelta(hours=18),
                                "Was": "Radfahren",
                                "Zeit": timedelta(hours=1),
                                "Distanz": 15.68,
                            },
                        ]
                    ),
                )
            ]
        )

        summary = self.importer.import_sheet(
            self.path,
            "Alternativtraining",
        )

        self.assertEqual(3, summary.activities_created)
        rows = self._activities()
        self.assertEqual(
            ["soccer", "racket", "ride"],
            [row["sport"] for row in rows],
        )
        # Soccer is a no-distance sport; the writer keeps its canonical
        # distance at zero. The ride keeps the sheet's kilometres.
        self.assertEqual(0, rows[0]["distance_m"])
        self.assertEqual(15680, rows[2]["distance_m"])
        self.assertEqual(120, rows[0]["avg_hr"])
        self.assertEqual("Kicken", rows[0]["name"])
        self.assertEqual(
            "2020-08-01T16:00:00Z",
            rows[0]["started_at_utc"],
        )


class MaterialImportTests(SheetImportTestCase):

    def test_imports_equipment_and_is_idempotent(self):
        self._write([("Material", MATERIAL_ROWS)])

        first = self.importer.import_sheet(self.path, "Material")
        second = self.importer.import_sheet(self.path, "Material")

        self.assertEqual(2, first.equipment_created)
        self.assertEqual(0, second.equipment_created)
        self.assertEqual(2, second.equipment_updated)

        equipment = {
            item.id: item
            for item in self.repository.equipment()
        }
        self.assertEqual(2, len(equipment))
        shoe = equipment["sheet:equipment:7"]
        self.assertEqual("shoe", shoe.type)
        self.assertEqual("Asics GT-2000 4", shoe.name)
        self.assertEqual("Asics", shoe.brand)
        self.assertEqual(date(2018, 4, 9), shoe.acquired_on)
        self.assertEqual(date(2018, 4, 9), shoe.retired_on)
        self.assertIn("Größe 42.5", shoe.notes)
        self.assertIn("Testschuh", shoe.notes)

    def test_dry_run_does_not_create_equipment(self):
        self._write([("Material", MATERIAL_ROWS)])

        summary = self.importer.import_sheet(
            self.path,
            "Material",
            dry_run=True,
        )

        self.assertEqual(2, summary.equipment_created)
        self.assertEqual([], self.repository.equipment())


class SheetCliTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "book.ods"
        self.database = Path(self.directory.name) / "db.sqlite"
        write_ods(
            self.path,
            [
                ("Rohdaten", _rohdaten_rows([{
                    "Datum": date(2019, 1, 23),
                    "Distanz in m": 5000.0,
                    "Zeit": timedelta(minutes=30),
                }])),
            ],
        )

    def test_parser_accepts_sheet_options(self):
        args = build_parser().parse_args(
            [
                "sheet",
                str(self.path),
                "--sheet",
                "Rohdaten",
                "--dry-run",
            ]
        )

        self.assertEqual("sheet", args.command)
        self.assertEqual(str(self.path), str(args.path))
        self.assertEqual("Rohdaten", args.sheet_name)
        self.assertTrue(args.dry_run)

    def test_inspect_lists_sheets_and_headers(self):
        args = build_parser().parse_args(
            ["sheet", "--inspect", str(self.path)]
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_sheet(args, build_parser())

        self.assertEqual(0, code)
        self.assertIn("Rohdaten", output.getvalue())
        self.assertIn("Distanz in m", output.getvalue())

    def test_dry_run_command_writes_nothing(self):
        args = build_parser().parse_args(
            [
                "sheet",
                str(self.path),
                "--sheet",
                "Rohdaten",
                "--dry-run",
                "--database",
                str(self.database),
            ]
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_sheet(args, build_parser())

        self.assertEqual(0, code)
        self.assertIn("Sheet dry run", output.getvalue())
        self.assertIn("1 activities", output.getvalue())

        connection = open_database(self.database)
        self.addCleanup(connection.close)
        self.assertEqual(
            0,
            connection.execute(
                "SELECT COUNT(*) FROM activities"
            ).fetchone()[0],
        )


if __name__ == "__main__":
    unittest.main()
