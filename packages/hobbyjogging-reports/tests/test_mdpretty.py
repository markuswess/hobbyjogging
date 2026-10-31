import unittest

from intervals_report.mdpretty import render_markdown


class MarkdownRendererTests(unittest.TestCase):

    def test_headings_lose_hash_markers(self):
        output = render_markdown("# Title\n", color=False)

        self.assertIn("Title", output)
        self.assertNotIn("# Title", output)
        self.assertIn("━", output)

    def test_bullets_use_terminal_marker(self):
        output = render_markdown("- one\n  - two\n", color=False)

        self.assertIn("• one", output)
        self.assertIn("  • two", output)

    def test_bold_is_removed_without_color(self):
        self.assertEqual(
            "Total\n",
            render_markdown("**Total**\n", color=False),
        )

    def test_tables_are_boxed_and_aligned(self):
        markdown = (
            "| Category | Sessions |\n"
            "|---|---:|\n"
            "| easy | 3 |\n"
            "| **Total** | 5 |\n"
        )

        output = render_markdown(markdown, color=False)

        self.assertIn("┌", output)
        self.assertIn("├", output)
        self.assertIn("└", output)
        self.assertIn("Category", output)
        self.assertIn("Total", output)
        self.assertNotIn("**", output)

    def test_color_adds_ansi_sequences(self):
        output = render_markdown("# Title\n", color=True)

        self.assertIn("\033[", output)


if __name__ == "__main__":
    unittest.main()
