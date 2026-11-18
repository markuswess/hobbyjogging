import unittest

from hobbyjogging_import.sheet_codes import classification_for_sheet_code


class SheetCodeTests(unittest.TestCase):

    def test_sheet_codes(self):
        self.assertEqual(
            ({"intervals"}, {"vo2max"}, {"hills"}),
            classification_for_sheet_code("bi"),
        )
        self.assertEqual(
            ({"fartlek"}, {"vo2max"}, set()),
            classification_for_sheet_code("fs"),
        )
        self.assertEqual(
            (set(), set(), {"strength"}),
            classification_for_sheet_code("k"),
        )
        self.assertEqual(
            ({"continuous"}, set(), set()),
            classification_for_sheet_code("idl"),
        )
        self.assertEqual(
            ({"continuous"}, {"threshold"}, set()),
            classification_for_sheet_code("tdl"),
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


if __name__ == "__main__":
    unittest.main()
