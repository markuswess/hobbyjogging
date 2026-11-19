import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core.sources_config import (
    CONFIG_ENV,
    default_policies,
    load_sources,
)

CONFIG = """
[sources.fit]
enabled = true

[sources.intervals]
enabled = true

[sources.garmin]
enabled = true

[sources.runalyze]
create = "review"

[sources.strava]
create = "ignore"
title = "social"
description = "social"

[sources.sheet]
enabled = false
"""


class SourcesConfigTests(unittest.TestCase):

    def _load(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "sources.toml"
        path.write_text(text, encoding="utf-8")
        return load_sources(path)

    def test_code_defaults(self):
        policies = default_policies()

        self.assertTrue(policies["fit"].enabled)
        self.assertEqual("create", policies["fit"].create)
        self.assertEqual("ignore", policies["garmin"].create)
        self.assertEqual("social", policies["strava"].title)

    def test_reads_the_athlete_config(self):
        config = self._load(CONFIG)

        self.assertEqual("review", config.create("runalyze"))
        self.assertEqual("ignore", config.create("strava"))
        self.assertEqual("social", config.policy("strava").title)
        self.assertFalse(config.enabled("sheet"))
        self.assertTrue(config.enabled("fit"))
        self.assertEqual("create", config.create("fit"))

    def test_a_one_off_override_wins(self):
        config = self._load(CONFIG)

        self.assertEqual("create", config.create("strava", "create"))

    def test_an_unknown_source_is_an_error(self):
        with self.assertRaises(ValueError) as raised:
            self._load("[sources.nope]\nenabled = true\n")

        self.assertIn("unknown source", str(raised.exception))

    def test_an_unknown_key_is_an_error(self):
        with self.assertRaises(ValueError) as raised:
            self._load("[sources.fit]\ncolour = 'red'\n")

        self.assertIn("unknown key", str(raised.exception))

    def test_create_on_garmin_is_an_error(self):
        with self.assertRaises(ValueError) as raised:
            self._load("[sources.garmin]\ncreate = 'create'\n")

        self.assertIn("does not yield activity rows", str(raised.exception))

    def test_an_invalid_create_value_is_an_error(self):
        with self.assertRaises(ValueError):
            self._load("[sources.strava]\ncreate = 'sometimes'\n")

    def test_manual_is_not_configurable(self):
        with self.assertRaises(ValueError):
            self._load("[sources.manual]\nenabled = true\n")

    def test_the_environment_path_is_used(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "athlete.toml"
        path.write_text(CONFIG, encoding="utf-8")

        with patch.dict(os.environ, {CONFIG_ENV: str(path)}):
            config = load_sources()

        self.assertEqual("review", config.create("runalyze"))

    def test_a_missing_explicit_file_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            load_sources("/nonexistent/sources.toml")


if __name__ == "__main__":
    unittest.main()
