import tempfile
import unittest
from pathlib import Path

from hobbyjogging_report.sources import DEFAULT_SOURCE, create_source
from hobbyjogging_report.sources.database import DatabaseSource


class SourceFactoryTests(unittest.TestCase):

    def test_database_is_the_default_source(self):
        self.assertEqual("database", DEFAULT_SOURCE)

    def test_creates_database_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "training.db"
            source = create_source("database", database_path=path)
            self.addCleanup(source.close)

            self.assertIsInstance(source, DatabaseSource)
            self.assertTrue(path.exists())

    def test_rejects_unknown_source(self):
        with self.assertRaises(ValueError):
            create_source("runalyze")


if __name__ == "__main__":
    unittest.main()
