import unittest

from hobbyjogging_import.tag_lexicon import (
    lookup_tag,
    meaning_label,
    normalize_tag,
    tags_with_kind,
    workout_meanings,
)


class TagLexiconTests(unittest.TestCase):

    def test_normalizes_case_and_whitespace(self):
        self.assertEqual("sub threshold", normalize_tag("  Sub   Threshold "))
        self.assertEqual("lt1", normalize_tag("LT1"))

    def test_workout_tags_carry_methods_and_targets(self):
        sub = lookup_tag("sub threshold")
        self.assertEqual("workout", sub.kind)
        self.assertEqual({"intervals"}, set(sub.methods))
        self.assertEqual({"subthreshold"}, set(sub.targets))

        lt1 = lookup_tag("LT1")
        self.assertEqual({"intervals"}, set(lt1.methods))
        self.assertEqual({"lt1"}, set(lt1.targets))

        long = lookup_tag("Longjog")
        self.assertEqual({"long_run"}, set(long.methods))
        self.assertEqual({"base"}, set(long.targets))

    def test_illness_recovery_race_trail_and_area_kinds(self):
        self.assertEqual("illness", lookup_tag("verkühlt").kind)
        self.assertEqual("recovered", lookup_tag("wieder gesund").kind)
        self.assertEqual("race", lookup_tag("Raceday").kind)
        self.assertEqual("trail", lookup_tag("Trail").kind)
        self.assertEqual("area", lookup_tag("w").kind)
        self.assertEqual("ignore", lookup_tag("schlapp").kind)

    def test_rep_time_and_distance_tags(self):
        self.assertEqual(360.0, lookup_tag("6'").value)
        self.assertEqual(210.0, lookup_tag("3'30''").value)
        self.assertEqual(30.0, lookup_tag("30''").value)
        self.assertEqual(400.0, lookup_tag("400m").value)
        self.assertEqual(1000.0, lookup_tag("1km").value)
        self.assertEqual(1609.34, lookup_tag("Meile").value)

    def test_unmapped_tags_stay_unmapped(self):
        self.assertIsNone(lookup_tag("Wienerberg"))
        self.assertEqual("unmapped", meaning_label("Wienerberg"))

    def test_workout_meanings_and_kind_filters(self):
        tags = ["Longjog", "strides", "verkühlt", "Trail", "w"]

        self.assertEqual(
            ["long run", "strides"],
            [meaning.label for meaning in workout_meanings(tags)],
        )
        self.assertEqual(
            ["illness"],
            [meaning.label for meaning in tags_with_kind(tags, "illness")],
        )
        self.assertEqual(
            ["trail"],
            [meaning.label for meaning in tags_with_kind(tags, "trail")],
        )


if __name__ == "__main__":
    unittest.main()
