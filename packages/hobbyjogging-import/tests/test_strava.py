import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from hobbyjogging_core import connect, migrate
from hobbyjogging_import.strava import read_export
from hobbyjogging_import.strava_import import StravaCsvImporter

ACTIVITIES_HEADER = (
    "Activity ID,Activity Date,Activity Name,Activity Type,"
    "Activity Description,Elapsed Time,Distance,Gear,Private,Commute\n"
)


def _activity_row(
    external_id="123",
    date="Oct 01, 2026, 8:05:00 AM",
    name="Bakery run",
    sport="Run",
    description="Race you to the bakery",
    elapsed=3600,
    distance="10.0",
    gear="Pegasus",
):
    return (
        f'{external_id},"{date}",{name},{sport},"{description}",'
        f"{elapsed},{distance},{gear},0,0\n"
    )


class StravaExportTests(unittest.TestCase):

    def test_reads_english_activities_and_gear(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "activities.csv").write_text(
                ACTIVITIES_HEADER + _activity_row(),
                encoding="utf-8",
            )
            (root / "shoes.csv").write_text(
                "Shoe Name,Shoe Brand,Shoe Model\n"
                "Pegasus,Nike,Pegasus 40\n",
                encoding="utf-8",
            )

            export = read_export(root)

        self.assertEqual(1, len(export.activities))
        activity = export.activities[0]
        self.assertEqual("123", activity.external_id)
        self.assertEqual("2026-10-01", activity.local_date)
        self.assertEqual(10000, activity.distance_m)
        self.assertEqual("Pegasus", activity.gear)
        self.assertEqual(
            "https://www.strava.com/activities/123",
            activity.url,
        )

        self.assertEqual(1, len(export.gear))
        gear = export.gear[0]
        self.assertEqual("shoe", gear.type)
        self.assertEqual("Pegasus", gear.name)
        self.assertEqual("Nike", gear.brand)
        self.assertEqual("Pegasus 40", gear.model)

    def test_reads_german_gear_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "activities.csv").write_text(
                ACTIVITIES_HEADER + _activity_row(),
                encoding="utf-8",
            )
            (root / "shoes.csv").write_text(
                "Schuhname,Schuhmarke,Schuhmodell\n"
                "Pegasus,Nike,Pegasus 40\n",
                encoding="utf-8",
            )

            export = read_export(root)

        self.assertEqual("Pegasus", export.gear[0].name)
        self.assertEqual("Nike", export.gear[0].brand)

    def test_reads_a_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "activities.csv",
                    ACTIVITIES_HEADER + _activity_row(),
                )
                archive.writestr(
                    "shoes.csv",
                    "Shoe Name,Shoe Brand,Shoe Model\n"
                    "Pegasus,Nike,Pegasus 40\n",
                )

            export = read_export(path)

        self.assertEqual(1, len(export.activities))
        self.assertEqual(1, len(export.gear))

    def test_rejects_an_export_without_activities(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                read_export(Path(tmp))


class StravaImportTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.conn.execute(
            """
            INSERT INTO activities (
                id, local_date, started_at_utc, tz_offset_min, sport,
                name, description, elapsed_s, duration_s, distance_m
            ) VALUES (
                'a1', '2026-10-01', '2026-10-01T06:00:00Z', 120, 'run',
                'Morning run', 'Easy', 3600, 3500, 10000
            )
            """
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _export(self, row=None, shoes=None):
        (self.root / "activities.csv").write_text(
            ACTIVITIES_HEADER + (row or _activity_row()),
            encoding="utf-8",
        )
        if shoes is not None:
            (self.root / "shoes.csv").write_text(shoes, encoding="utf-8")
        return self.root

    def _social(self):
        return self.conn.execute(
            "SELECT title, description, url FROM activity_social "
            "WHERE activity_id = 'a1' AND source = 'strava'"
        ).fetchall()

    def test_writes_social_without_touching_the_canonical_fields(self):
        summary = StravaCsvImporter(self.conn).import_export(self._export())

        self.assertEqual(1, summary.social_written)
        self.assertEqual(1, summary.social_created)
        rows = self._social()
        self.assertEqual(1, len(rows))
        self.assertEqual("Bakery run", rows[0]["title"])
        self.assertEqual("Race you to the bakery", rows[0]["description"])

        activity = self.conn.execute(
            "SELECT name, description FROM activities WHERE id = 'a1'"
        ).fetchone()
        self.assertEqual("Morning run", activity["name"])
        self.assertEqual("Easy", activity["description"])

    def test_unmatched_rows_write_nothing(self):
        row = _activity_row(
            external_id="999",
            date="Oct 05, 2026, 8:05:00 AM",
            name="Other run",
        )
        summary = StravaCsvImporter(self.conn).import_export(self._export(row))

        self.assertEqual(0, summary.social_written)
        self.assertEqual(1, summary.unmatched)
        self.assertEqual([], self._social())

    def test_rerun_is_idempotent(self):
        importer = StravaCsvImporter(self.conn)
        importer.import_export(self._export())
        importer.import_export(self._export())

        self.assertEqual(1, len(self._social()))
        count = self.conn.execute(
            "SELECT COUNT(*) FROM source_records "
            "WHERE source = 'strava' AND record_type = 'social'"
        ).fetchone()[0]
        self.assertEqual(1, count)

    def test_dry_run_writes_nothing(self):
        summary = StravaCsvImporter(self.conn).import_export(
            self._export(),
            dry_run=True,
        )

        self.assertEqual(1, summary.social_written)
        self.assertEqual([], self._social())
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records WHERE source = 'strava'"
            ).fetchone()[0],
        )

    def test_existing_gear_is_linked_not_rewritten(self):
        self.conn.execute(
            """
            INSERT INTO equipment (id, type, name, brand, model)
            VALUES ('sheet:equipment:1', 'shoe', 'Pegasus', 'Old', 'Old')
            """
        )
        shoes = (
            "Shoe Name,Shoe Brand,Shoe Model\n"
            "Pegasus,Nike,Pegasus 40\n"
        )
        summary = StravaCsvImporter(self.conn).import_export(
            self._export(shoes=shoes)
        )

        self.assertEqual(1, summary.gear_linked)
        self.assertEqual(0, summary.gear_created)
        gear = self.conn.execute(
            "SELECT name, brand, model FROM equipment "
            "WHERE id = 'sheet:equipment:1'"
        ).fetchone()
        self.assertEqual("Pegasus", gear["name"])
        self.assertEqual("Old", gear["brand"])
        self.assertEqual("Old", gear["model"])

        link = self.conn.execute(
            "SELECT equipment_id FROM activity_equipment "
            "WHERE activity_id = 'a1' AND source = 'strava'"
        ).fetchone()
        self.assertEqual("sheet:equipment:1", link["equipment_id"])

    def test_unknown_gear_creates_a_row_and_links_the_activity(self):
        row = _activity_row(gear="Cloudsurfer")
        shoes = (
            "Shoe Name,Shoe Brand,Shoe Model\n"
            "Cloudsurfer,On,Cloudsurfer 2\n"
        )
        summary = StravaCsvImporter(self.conn).import_export(
            self._export(row, shoes=shoes)
        )

        self.assertEqual(1, summary.gear_created)
        gear = self.conn.execute(
            "SELECT type, name, brand, model FROM equipment "
            "WHERE id = 'strava:gear:cloudsurfer'"
        ).fetchone()
        self.assertEqual("shoe", gear["type"])
        self.assertEqual("Cloudsurfer", gear["name"])
        self.assertEqual("On", gear["brand"])
        self.assertEqual("Cloudsurfer 2", gear["model"])

        link = self.conn.execute(
            "SELECT equipment_id FROM activity_equipment "
            "WHERE activity_id = 'a1' AND source = 'strava'"
        ).fetchone()
        self.assertEqual("strava:gear:cloudsurfer", link["equipment_id"])

    def test_date_range_filter(self):
        summary = StravaCsvImporter(self.conn).import_export(
            self._export(),
            start=date(2026, 10, 2),
        )

        self.assertEqual(0, summary.activities_seen)
        self.assertEqual([], self._social())


if __name__ == "__main__":
    unittest.main()
