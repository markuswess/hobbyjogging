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

ATHLETE2 = """
[sources.fit]
enabled = false

[sources.intervals]
enabled = false

[sources.garmin]
enabled = true
wellness = true

[sources.runalyze]
create = "review"
tags = true
gear = true
races = true
vo2max = true
workout_type = true
trimp = true

[sources.strava]
enabled = false

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

    def _athlete2(self, text=ATHLETE2):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "athlete2.toml"
        path.write_text(text, encoding="utf-8")
        return load_sources(path)

    def test_sources_table_shows_the_policy(self):
        text = format_sources(self.config)

        self.assertIn("runalyze", text)
        self.assertIn("create=review", text)
        self.assertIn("strava", text)
        self.assertIn("create=ignore", text)
        self.assertIn("sheet", text)
        self.assertIn("enabled=False", text)
        self.assertIn("capabilities=tags,gear,races,vo2max,workout_type,trimp", text)
        self.assertIn("disabled=-", text)

    def test_settings_report_has_the_sections(self):
        text = settings_report(self.config)

        for part in (
            "# Import settings",
            "## Sources",
            "## Capability matrix",
            "## Capability selection",
            "## Uncovered record types",
            "## Uncovered activity fields",
            "## Dashboard capabilities",
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

    def test_the_matrix_shows_record_types_budget_and_creation_fields(self):
        text = settings_report(self._athlete2())

        self.assertIn("| runalyze | yes | yes | exact_twin | "
                      "runalyze_window | yes |", text)
        self.assertIn("workout_type", text)
        self.assertIn("trimp", text)
        self.assertIn("| garmin | yes | no | none | garmin | no |", text)
        self.assertIn("training_load", text)
        self.assertIn("| garmin | wellness | yes |", text)

    def test_the_inverse_distinguishes_disabled_from_unavailable(self):
        text = settings_report(self._athlete2())

        self.assertIn("## Uncovered record types", text)
        self.assertIn("`social` — strava (source disabled)", text)
        self.assertIn("`zones` — intervals (source disabled)", text)
        self.assertIn("## Uncovered activity fields", text)
        self.assertIn("`device_id` — fit (source disabled)", text)

    def test_dashboard_capabilities_name_the_missing_ones(self):
        text = settings_report(self._athlete2())

        self.assertIn("wellness (resting HR/HRV/sleep): covered by garmin", text)
        self.assertIn("training load: covered by runalyze", text)
        self.assertIn(
            "social text: available in strava (source disabled)",
            text,
        )
        self.assertIn("HR/pace zones: available in intervals (source disabled)", text)
        self.assertIn("threshold add", text)

    def test_a_disabled_capability_is_visible_in_the_selection(self):
        text = settings_report(
            self._athlete2(
                ATHLETE2.replace("workout_type = true", "workout_type = false")
            )
        )

        self.assertIn("| runalyze | workout_type | no |", text)
        self.assertIn(
            "typed reps/intervals: available in intervals (source disabled); "
            "available in runalyze (capability disabled)",
            text,
        )


if __name__ == "__main__":
    unittest.main()
