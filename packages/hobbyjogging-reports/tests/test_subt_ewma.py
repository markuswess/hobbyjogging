import unittest
from datetime import date, timedelta

from hobbyjogging_report.analysis import subt_ewma
from hobbyjogging_report.model import SubtPoint
from hobbyjogging_report.subt_ewma_report import subt_ewma_markdown

END = date(2026, 11, 11)


def _point(day, category="short", pace=220, hr=160):
    return SubtPoint(
        day,
        category,
        pace_s_per_km=pace,
        avg_hr=hr,
    )


class SubtEwmaTests(unittest.TestCase):

    def test_one_row_per_category(self):
        rows = subt_ewma(
            [_point(END)],
            END - timedelta(days=10),
            END,
        )

        self.assertEqual(
            ["short", "medium", "long", "lt1"],
            [row.category for row in rows],
        )
        self.assertAlmostEqual(220.0, rows[0].pace[7])
        self.assertIsNone(rows[1].pace[7])

    def test_carries_the_last_session_between_dates(self):
        rows = subt_ewma(
            [_point(END - timedelta(days=2), pace=200, hr=150)],
            END - timedelta(days=10),
            END,
        )
        short = rows[0]

        self.assertAlmostEqual(200.0, short.pace[182])
        self.assertAlmostEqual(150.0, short.hr[182])

    def test_sparse_categories_do_not_leak(self):
        rows = subt_ewma(
            [
                _point(END, category="short", pace=200),
                _point(END, category="long", pace=260),
            ],
            END - timedelta(days=10),
            END,
        )

        long_row = next(row for row in rows if row.category == "long")

        self.assertAlmostEqual(260.0, long_row.pace[7])
        self.assertIsNone(
            next(row for row in rows if row.category == "medium").pace[7]
        )


class SubtEwmaMarkdownTests(unittest.TestCase):

    def test_tables_render_pace_and_hr(self):
        markdown = subt_ewma_markdown(
            [_point(END)],
            END,
        )

        self.assertIn("# subT EWMA Report", markdown)
        self.assertIn("## Pace", markdown)
        self.assertIn("## Heart rate", markdown)
        self.assertIn("| Short | 3:40/km | 3:40/km | 3:40/km |", markdown)
        self.assertIn("| Short | 160 bpm | 160 bpm | 160 bpm |", markdown)
        self.assertIn("| LT1 | - | - | - |", markdown)

    def test_without_points_all_cells_are_dashes(self):
        markdown = subt_ewma_markdown([], END)

        self.assertEqual(2, markdown.count("| Long | - | - | - |"))


if __name__ == "__main__":
    unittest.main()
