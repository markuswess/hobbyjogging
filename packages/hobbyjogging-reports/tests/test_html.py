import unittest

from hobbyjogging_report.html import TABLE_COLLAPSE_ROWS, table


def rows(count):
    return [[f"r{index}", str(index)] for index in range(count)]


class TableTests(unittest.TestCase):

    def test_a_short_table_stays_plain(self):
        html = table(["Name", "N"], rows(3), numeric=(1,), collapse="log")

        self.assertNotIn("table-toggle", html)
        self.assertNotIn("extra-row", html)
        self.assertIn("<td>r2</td>", html)

    def test_a_long_table_collapses_but_keeps_every_row(self):
        count = TABLE_COLLAPSE_ROWS + 2
        html = table(["Name", "N"], rows(count), numeric=(1,), collapse="log")

        self.assertIn('id="table-log"', html)
        self.assertIn('class="table-toggle"', html)
        self.assertIn(f"Show all {count} rows", html)
        self.assertIn(
            f"Showing the first {TABLE_COLLAPSE_ROWS} of {count} rows.",
            html,
        )
        self.assertEqual(2, html.count('<tr class="extra-row">'))
        # Every row is still in the HTML; only CSS hides the extras.
        self.assertEqual(count, html.count("<td>r"))

    def test_a_long_table_without_a_key_stays_plain(self):
        html = table(
            ["Name", "N"],
            rows(TABLE_COLLAPSE_ROWS + 2),
        )

        self.assertNotIn("table-toggle", html)
        self.assertNotIn("extra-row", html)

    def test_the_key_links_the_toggle_and_its_label(self):
        html = table(["Name"], rows(TABLE_COLLAPSE_ROWS + 1), collapse="races")

        self.assertIn('id="table-races"', html)
        self.assertIn('for="table-races"', html)
        self.assertIn("<span class=\"less\">Show fewer</span>", html)


if __name__ == "__main__":
    unittest.main()
