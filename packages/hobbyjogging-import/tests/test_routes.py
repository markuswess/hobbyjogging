import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_core import TrainingRepository, connect, migrate
from hobbyjogging_import.routes import (
    numbers_by_name,
    route_identity,
    route_number,
)
from hobbyjogging_import.sheet_import import SheetImporter

from ods_fixture import write_ods
from test_sheet_import import _rohdaten_rows


class RouteIdentityTests(unittest.TestCase):

    def test_a_number_is_the_key(self):
        route = route_identity("Wienerberg 8er", 25.0)

        self.assertEqual("sheet:route:25", route.id)
        self.assertEqual("25", route.external_ref)
        self.assertEqual("Wienerberg 8er", route.name)

    def test_a_fractional_number_keeps_its_form(self):
        self.assertEqual("16.5", route_number(16.5))

    def test_a_name_only_row_reuses_the_number_seen_for_it(self):
        known = numbers_by_name([("Kaserne", 6.0)])

        route = route_identity("Kaserne", None, known)

        self.assertEqual("sheet:route:6", route.id)

    def test_an_ambiguous_name_gets_its_own_key(self):
        known = numbers_by_name([("Lusthaus", 33.0), ("Lusthaus", 330.0)])

        route = route_identity("Lusthaus", None, known)

        self.assertEqual("sheet:route:name:lusthaus", route.id)

    def test_a_url_is_not_a_route(self):
        self.assertIsNone(
            route_identity("http://www.gmap-pedometer.com/?r=6722376", None)
        )


class SheetRouteImportTests(unittest.TestCase):

    def setUp(self):
        self.connection = connect(":memory:")
        self.addCleanup(self.connection.close)
        migrate(self.connection)
        self.importer = SheetImporter(self.connection)
        self.repository = TrainingRepository(self.connection)

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "book.ods"

    def _import(self, rows):
        write_ods(self.path, [("Rohdaten", _rohdaten_rows(rows))])
        return self.importer.import_sheet(self.path, "Rohdaten")

    def test_numbered_and_name_only_rows_share_a_route(self):
        summary = self._import([
            {
                "Datum": date(2019, 1, 23),
                "Streckennummer": 6.0,
                "Strecke": "Kaserne",
                "Distanz in m": 8000.0,
                "Zeit": timedelta(minutes=45),
            },
            {
                "Datum": date(2019, 1, 24),
                "Strecke": "Kaserne",
                "Distanz in m": 8000.0,
                "Zeit": timedelta(minutes=46),
            },
        ])

        self.assertEqual(2, summary.routes_linked)

        routes = self.repository.routes()
        self.assertEqual(["sheet:route:6"], [route.id for route in routes])
        self.assertEqual("6", routes[0].external_ref)
        self.assertEqual("Kaserne", routes[0].name)

        activities = self.repository.activities(
            date(2019, 1, 23), date(2019, 1, 24)
        )
        self.assertEqual(
            [["sheet:route:6"], ["sheet:route:6"]],
            [[route.id for route in activity.routes] for activity in activities],
        )


if __name__ == "__main__":
    unittest.main()
