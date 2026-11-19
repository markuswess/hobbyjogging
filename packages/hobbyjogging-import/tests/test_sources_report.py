import tempfile
import unittest
from pathlib import Path

from hobbyjogging_core.sources_config import load_sources
from hobbyjogging_import.sources_report import format_sources, settings_report

CONFIG = """
[sources.fit]
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


class SourcesReportTests(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "sources.toml"
        path.write_text(CONFIG, encoding="utf-8")
        self.config = load_sources(path)

    def test_sources_table_shows_the_policy(self):
        text = format_sources(self.config)

        self.assertIn("runalyze", text)
        self.assertIn("create=review", text)
        self.assertIn("strava", text)
        self.assertIn("create=ignore", text)
        self.assertIn("sheet", text)
        self.assertIn("enabled=False", text)

    def test_settings_report_has_the_sections(self):
        text = settings_report(self.config)

        for part in (
            "# Import settings",
            "## Sources",
            "## Field rules",
            "## Matching",
            "## Review categories",
            "## Conflict causes",
            "## Classification",
            "## Payload mapping",
            "## Manual edits",
            "`distance_m` ← distance",
        ):
            self.assertIn(part, text)


if __name__ == "__main__":
    unittest.main()
