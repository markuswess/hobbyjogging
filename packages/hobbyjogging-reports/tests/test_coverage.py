import unittest
from datetime import date

from hobbyjogging_report.analysis import yearly_coverage
from support import activity_factory

activity = activity_factory()


class YearCoverageTests(unittest.TestCase):

    def test_groups_by_year_newest_first(self):
        rows = yearly_coverage(
            [
                activity(id="a", date=date(2024, 5, 1), max_hr=175),
                activity(id="b", date=date(2024, 6, 1)),
                activity(id="c", date=date(2026, 1, 1), max_hr=182),
            ],
            {"a", "c"},
        )

        self.assertEqual([2026, 2024], [row.year for row in rows])
        self.assertEqual((1, 1, 1), (
            rows[0].activities,
            rows[0].weather,
            rows[0].max_hr,
        ))
        self.assertAlmostEqual(1.0, rows[0].weather_share)
        self.assertAlmostEqual(1.0, rows[0].max_hr_share)
        self.assertEqual((2, 1, 1), (
            rows[1].activities,
            rows[1].weather,
            rows[1].max_hr,
        ))
        self.assertAlmostEqual(0.5, rows[1].weather_share)
        self.assertAlmostEqual(0.5, rows[1].max_hr_share)

    def test_an_empty_year_is_not_invented(self):
        rows = yearly_coverage(
            [activity(id="a", date=date(2025, 7, 1))],
            set(),
        )

        self.assertEqual([2025], [row.year for row in rows])
        self.assertEqual(0, rows[0].weather)
        self.assertEqual(0, rows[0].max_hr)
        self.assertAlmostEqual(0.0, rows[0].weather_share)
        self.assertAlmostEqual(0.0, rows[0].max_hr_share)

    def test_empty_history(self):
        self.assertEqual([], yearly_coverage([], set()))


if __name__ == "__main__":
    unittest.main()
