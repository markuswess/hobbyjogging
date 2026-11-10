import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_report.sources import create_source
from hobbyjogging_report.sources.database import DatabaseSource


class SourceFactoryTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "reports.db"

    def test_creates_the_database_source(self):
        source = create_source(database_path=self.database)

        self.assertIsInstance(source, DatabaseSource)
        source.close()

    def test_opens_the_configured_database(self):
        with patch.dict(os.environ, {"HOBBYJOGGING_DB": str(self.database)}):
            source = create_source()
            try:
                self.assertIsInstance(source, DatabaseSource)
                self.assertEqual(
                    str(self.database),
                    source.connection.execute(
                        "PRAGMA database_list"
                    ).fetchone()[2],
                )
            finally:
                source.close()


if __name__ == "__main__":
    unittest.main()
