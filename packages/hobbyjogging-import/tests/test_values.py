import unittest

from hobbyjogging_import.values import (
    format_distance_m,
    format_duration_s,
    parse_distance_m,
    parse_duration_s,
    parse_sport,
)


class ParseDurationTests(unittest.TestCase):

    def test_minutes_seconds(self):
        self.assertEqual(2780, parse_duration_s("46:20"))

    def test_hours_minutes_seconds(self):
        self.assertEqual(3723, parse_duration_s("1:02:03"))

    def test_plain_number_is_seconds(self):
        self.assertEqual(2780, parse_duration_s("2780"))
        self.assertEqual(2780.5, parse_duration_s("2780.5"))

    def test_zero_minutes_component(self):
        self.assertEqual(3630, parse_duration_s("1:00:30"))

    def test_rejects_garbage(self):
        for value in ("", "  ", "foo", "46:20:", "46:20:30:40", "-5", "0"):
            with self.assertRaises(ValueError, msg=value):
                parse_duration_s(value)


class ParseDistanceTests(unittest.TestCase):

    def test_kilometres(self):
        self.assertEqual(8200, parse_distance_m("8.2km"))

    def test_metres(self):
        self.assertEqual(8200, parse_distance_m("8200m"))

    def test_plain_number_is_kilometres(self):
        self.assertEqual(8200, parse_distance_m("8.2"))

    def test_rejects_garbage(self):
        for value in ("", "  ", "8,2 km", "8.2mi", "-5km", "0m"):
            with self.assertRaises(ValueError, msg=value):
                parse_distance_m(value)


class ParseSportTests(unittest.TestCase):

    def test_aliases_are_normalized(self):
        self.assertEqual("run", parse_sport("running"))
        self.assertEqual("trail_run", parse_sport("trail_running"))
        self.assertEqual("ride", parse_sport("Cycling"))

    def test_canonical_names_pass_through(self):
        self.assertEqual("mtb_ride", parse_sport("mtb_ride"))

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            parse_sport("   ")


class FormatTests(unittest.TestCase):

    def test_format_duration(self):
        self.assertEqual("46:20", format_duration_s(2780))
        self.assertEqual("1:02:03", format_duration_s(3723))
        self.assertEqual("0:00", format_duration_s(0))
        self.assertEqual("-", format_duration_s(None))

    def test_format_distance(self):
        self.assertEqual("8.20 km", format_distance_m(8200))
        self.assertEqual("-", format_distance_m(None))


if __name__ == "__main__":
    unittest.main()
