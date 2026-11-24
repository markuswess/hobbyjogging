"""Contract tests for the shared import rules and source profiles."""

import unittest

from hobbyjogging_core.db.writer import ACTIVITY_COLUMNS
from hobbyjogging_core.import_rules import (
    CONFLICT_FIELDS,
    FIELD_RULES,
    MANUAL_FIELDS,
    NUMERIC_TOLERANCES,
    SOURCES,
    authority_rank,
    source_profile,
)


class FieldRuleTests(unittest.TestCase):
    def test_conflict_fields_are_the_documented_set(self):
        self.assertEqual(
            {
                "duration_s",
                "elapsed_s",
                "moving_s",
                "distance_m",
                "elevation_gain_m",
                "elevation_loss_m",
                "max_hr",
                "avg_hr",
                "started_at_utc",
                "local_date",
                "tz_offset_min",
                "sport",
                "training_load",
            },
            set(CONFLICT_FIELDS),
        )

    def test_manual_fields_are_the_documented_set(self):
        self.assertEqual(
            {
                "duration_s",
                "elapsed_s",
                "moving_s",
                "distance_m",
                "elevation_gain_m",
                "elevation_loss_m",
                "max_hr",
                "avg_hr",
                "started_at_utc",
                "local_date",
                "tz_offset_min",
                "sport",
                "training_load",
                "vo2max_garmin",
                "vo2max_runalyze",
                "device_id",
            },
            set(MANUAL_FIELDS),
        )

    def test_tolerances_are_the_documented_set(self):
        self.assertEqual(
            {
                "duration_s": (0.05, 2.0),
                "elapsed_s": (0.01, 2.0),
                "moving_s": (0.01, 2.0),
                "distance_m": (0.01, 10.0),
                "avg_hr": (0.01, 5.0),
                "elevation_gain_m": (0.10, 20.0),
                "elevation_loss_m": (0.10, 20.0),
                "max_hr": (0.01, 2.0),
            },
            NUMERIC_TOLERANCES,
        )

    def test_ranked_authority_has_a_fallback(self):
        self.assertEqual(("intervals", "fit"), FIELD_RULES["moving_s"].authority)
        self.assertEqual(("intervals", "fit"), FIELD_RULES["elapsed_s"].authority)
        self.assertEqual(("fit",), FIELD_RULES["device_id"].authority)
        self.assertEqual(("fit",), FIELD_RULES["vo2max_garmin"].authority)

    def test_authority_rank(self):
        rule = FIELD_RULES["moving_s"]
        self.assertEqual(0, authority_rank(rule, "intervals"))
        self.assertEqual(1, authority_rank(rule, "fit"))
        self.assertIsNone(authority_rank(rule, "runalyze"))

    def test_every_ranked_source_has_a_profile(self):
        for rule in FIELD_RULES.values():
            for source in rule.authority:
                self.assertIn(source, SOURCES)

    def test_rules_only_name_activity_columns(self):
        self.assertLessEqual(set(FIELD_RULES), ACTIVITY_COLUMNS)

    def test_text_and_subjective_fields_stay_owner_tracked(self):
        for field in ("name", "description", "rpe", "feel", "intensity"):
            self.assertNotIn(field, CONFLICT_FIELDS)
            self.assertNotIn(field, MANUAL_FIELDS)


class SourceProfileTests(unittest.TestCase):
    def test_profiles_are_internally_consistent(self):
        for name, profile in SOURCES.items():
            self.assertEqual(name, profile.name)
            self.assertTrue(profile.label)
            self.assertTrue(profile.entities)
            self.assertIn(
                profile.match,
                {"temporal", "contained_fit", "exact_twin", "none"},
            )
            self.assertIn(
                profile.absence,
                {"ignore", "events", "manual"},
            )

    def test_runalyze_yields_activities_but_needs_details(self):
        profile = source_profile("runalyze")
        self.assertTrue(profile.yields_activities)
        self.assertTrue(profile.detail_required)
        self.assertIn("vo2max_runalyze", profile.creation_fields)

    def test_phase_two_capabilities_are_declared(self):
        self.assertLessEqual(
            {"workout_type", "trimp"},
            source_profile("runalyze").entities,
        )
        self.assertIn("wellness", source_profile("garmin").entities)
        self.assertIn("training_load", source_profile("runalyze").creation_fields)
        self.assertIn("intervals", source_profile("intervals").entities)

    def test_activity_sources_yield_activities(self):
        for name in ("fit", "intervals", "sheet", "runalyze", "strava"):
            self.assertTrue(source_profile(name).yields_activities, name)
        self.assertFalse(source_profile("garmin").yields_activities)

    def test_creation_fields_are_declared(self):
        self.assertIn("duration_s", source_profile("fit").creation_fields)
        self.assertIn("distance_m", source_profile("strava").creation_fields)
        self.assertEqual(
            frozenset(),
            source_profile("garmin").creation_fields,
        )

    def test_strava_csv_is_social_and_gear_first(self):
        profile = source_profile("strava")
        self.assertTrue(profile.yields_activities)
        self.assertEqual(
            {"activity", "gear", "social"},
            set(profile.entities),
        )
        self.assertEqual("temporal", profile.match)

    def test_unknown_source_fails_loudly(self):
        with self.assertRaises(KeyError) as raised:
            source_profile("nope")
        self.assertIn("known sources", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
