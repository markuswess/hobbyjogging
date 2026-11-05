import unittest

from hobbyjogging_core.sports import (
    CANONICAL_SPORTS,
    PACE_SPORTS,
    RIDE_SPORTS,
    RUN_SPORTS,
    SPORT_LABELS,
    canonical_sport,
    is_known_sport,
    normalize_token,
)


class CanonicalSportTests(unittest.TestCase):

    def test_fit_sport_names(self):
        self.assertEqual("run", canonical_sport("running"))
        self.assertEqual("ride", canonical_sport("cycling"))
        self.assertEqual("swim", canonical_sport("swimming"))
        self.assertEqual("sup", canonical_sport("stand_up_paddleboarding"))
        self.assertEqual("alpine_skiing", canonical_sport("alpine_skiing"))
        self.assertEqual(
            "cross_country_skiing",
            canonical_sport("cross_country_skiing"),
        )

    def test_fit_sub_sports_carry_specificity(self):
        self.assertEqual("trail_run", canonical_sport("running", "trail"))
        self.assertEqual(
            "treadmill_run",
            canonical_sport("running", "treadmill"),
        )
        self.assertEqual("track_run", canonical_sport("running", "track"))
        self.assertEqual("run", canonical_sport("running", "generic"))
        self.assertEqual(
            "gravel_ride",
            canonical_sport("cycling", "gravel_cycling"),
        )
        self.assertEqual("mtb_ride", canonical_sport("cycling", "mountain"))
        self.assertEqual("ride", canonical_sport("cycling", "road"))
        self.assertEqual(
            "virtual_ride",
            canonical_sport("cycling", "virtual_activity"),
        )
        self.assertEqual(
            "virtual_run",
            canonical_sport("running", "virtual_activity"),
        )
        self.assertEqual("swim", canonical_sport("swimming", "open_water"))
        self.assertEqual(
            "training",
            canonical_sport("training", "strength_training"),
        )

    def test_intervals_type_names(self):
        self.assertEqual("run", canonical_sport("Run"))
        self.assertEqual("trail_run", canonical_sport("TrailRun"))
        self.assertEqual("gravel_ride", canonical_sport("GravelRide"))
        self.assertEqual("alpine_skiing", canonical_sport("AlpineSki"))
        self.assertEqual("soccer", canonical_sport("Soccer"))
        self.assertEqual("other", canonical_sport("Other"))
        self.assertEqual("mtb_ride", canonical_sport("MountainBikeRide"))
        self.assertEqual("virtual_ride", canonical_sport("VirtualRide"))
        self.assertEqual("racket", canonical_sport("Padel"))
        self.assertEqual("soccer", canonical_sport("Football"))

    def test_generic_becomes_other(self):
        self.assertEqual("other", canonical_sport("generic"))
        self.assertEqual("other", canonical_sport("generic", "generic"))
        self.assertEqual("other", canonical_sport("unknown"))

    def test_unknown_tokens_pass_through_normalized(self):
        self.assertEqual("golf", canonical_sport("Golf"))
        self.assertEqual("weird_sport", canonical_sport("Weird Sport"))
        self.assertEqual("", canonical_sport(""))

    def test_normalize_token(self):
        self.assertEqual("trail_run", normalize_token(" Trail-Run "))
        self.assertEqual("", normalize_token(None))

    def test_is_known_sport(self):
        self.assertTrue(is_known_sport("run"))
        self.assertTrue(is_known_sport("golf"))  # specific, just unmapped
        self.assertFalse(is_known_sport("other"))
        self.assertFalse(is_known_sport("generic"))
        self.assertFalse(is_known_sport(""))
        self.assertFalse(is_known_sport(None))

    def test_sport_groups(self):
        self.assertIn("run", RUN_SPORTS)
        self.assertIn("treadmill_run", RUN_SPORTS)
        self.assertIn("gravel_ride", RIDE_SPORTS)
        self.assertEqual(RUN_SPORTS | RIDE_SPORTS, PACE_SPORTS)
        self.assertNotIn("walk", PACE_SPORTS)

    def test_every_canonical_sport_has_a_label(self):
        self.assertTrue(CANONICAL_SPORTS <= set(SPORT_LABELS))


if __name__ == "__main__":
    unittest.main()
