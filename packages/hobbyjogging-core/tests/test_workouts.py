import unittest

from hobbyjogging_core.workouts import (
    QUALITY_METHODS,
    QUALITY_TARGETS,
    WORKOUT_METHODS,
    WORKOUT_TARGETS,
    canonical_method,
    canonical_target,
    classification_for_category,
    classification_for_sheet_code,
    is_quality,
    method_label,
    target_label,
)


class WorkoutVocabularyTests(unittest.TestCase):

    def test_method_aliases(self):
        self.assertEqual("continuous", canonical_method("easy"))
        self.assertEqual("continuous", canonical_method("Recovery"))
        self.assertEqual("intervals", canonical_method("reps"))
        self.assertEqual("long_run", canonical_method("long"))
        self.assertEqual("progression", canonical_method("progressive"))
        self.assertEqual("race", canonical_method("competition"))
        self.assertEqual("strides", canonical_method("stride"))

    def test_target_aliases(self):
        self.assertEqual("base", canonical_target("easy"))
        self.assertEqual("lt1", canonical_target("aerobic_threshold"))
        self.assertEqual("subthreshold", canonical_target("subT"))
        self.assertEqual("threshold", canonical_target("lactate_threshold"))
        self.assertEqual("vo2max", canonical_target("vo2"))
        self.assertEqual("speed", canonical_target("speedwork"))
        self.assertEqual("marathon", canonical_target("marathon_specific"))
        self.assertEqual("recovery", canonical_target("regeneration"))

    def test_unknown_values_become_other(self):
        self.assertEqual("other", canonical_method("fartlek"))
        self.assertEqual("other", canonical_target("nonsense"))

    def test_labels(self):
        self.assertEqual("Long Run", method_label("long_run"))
        self.assertEqual("Sub-Threshold", target_label("subT"))

    def test_quality_from_methods(self):
        self.assertTrue(is_quality(["intervals"], []))
        self.assertTrue(is_quality(["long_run"], []))
        self.assertTrue(is_quality(["tempo"], []))
        self.assertTrue(is_quality(["progression"], []))
        self.assertTrue(is_quality(["race"], []))
        self.assertFalse(is_quality(["continuous"], []))
        self.assertFalse(is_quality(["strides"], []))
        self.assertIsNone(is_quality([], []))

    def test_quality_from_targets(self):
        for target in QUALITY_TARGETS:
            self.assertTrue(is_quality([], [target]), target)
        self.assertFalse(is_quality([], ["base"]))
        self.assertFalse(is_quality([], ["recovery"]))
        self.assertFalse(is_quality([], ["other"]))
        self.assertIsNone(is_quality([], []))

    def test_strides_do_not_make_a_base_run_quality(self):
        self.assertFalse(is_quality(["continuous", "strides"], ["base"]))

    def test_category_mapping(self):
        self.assertEqual(
            ({"intervals"}, {"subthreshold"}),
            classification_for_category("quality", "intervals", "subt-long"),
        )
        self.assertEqual(
            ({"intervals"}, {"lt1"}),
            classification_for_category("quality", "intervals", "lt1"),
        )
        self.assertEqual(
            ({"long_run"}, {"base"}),
            classification_for_category("quality", "longrun"),
        )
        self.assertEqual(
            ({"race"}, {"other"}),
            classification_for_category("quality", "race"),
        )
        self.assertEqual(
            ({"continuous"}, {"base"}),
            classification_for_category("non-quality", "easy"),
        )
        self.assertEqual(
            ({"continuous"}, {"recovery"}),
            classification_for_category("non-quality", "recovery"),
        )
        self.assertEqual(
            (set(), set()),
            classification_for_category("cross-training"),
        )

    def test_sheet_codes(self):
        self.assertEqual(
            ({"intervals"}, {"vo2max"}, {"hills"}),
            classification_for_sheet_code("bi"),
        )
        self.assertEqual(
            ({"intervals"}, set(), set()),
            classification_for_sheet_code("fs"),
        )
        self.assertEqual(
            (set(), set(), {"strength"}),
            classification_for_sheet_code("k"),
        )
        self.assertEqual(
            ({"tempo"}, set(), set()),
            classification_for_sheet_code("idl"),
        )
        self.assertEqual(
            (set(), set(), {"bad data"}),
            classification_for_sheet_code("u"),
        )
        self.assertEqual(
            ({"race"}, {"other"}, set()),
            classification_for_sheet_code("lt"),
        )
        self.assertEqual(
            (set(), set(), set()),
            classification_for_sheet_code(""),
        )

    def test_every_token_has_a_label(self):
        self.assertTrue(all(WORKOUT_METHODS.values()))
        self.assertTrue(all(WORKOUT_TARGETS.values()))
        self.assertTrue(QUALITY_METHODS <= set(WORKOUT_METHODS))
        self.assertTrue(QUALITY_TARGETS <= set(WORKOUT_TARGETS))


if __name__ == "__main__":
    unittest.main()
