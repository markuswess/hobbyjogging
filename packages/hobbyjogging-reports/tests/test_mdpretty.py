import unittest
from datetime import date

from hobbyjogging_core.model import Event
from hobbyjogging_report.mdpretty import render_markdown
from hobbyjogging_report.daily import format_event


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

    def test_fenced_code_block_is_not_inline_rendered(self):
        markdown = (
            "- Description:\n"
            "  ```\n"
            "  **Warm up**\n"
            "  - 10 min easy\n"
            "\n"
            "  ## Main\n"
            "  ```\n"
        )

        output = render_markdown(markdown, color=False)

        self.assertNotIn("```", output)
        self.assertIn("**Warm up**", output)
        self.assertIn("- 10 min easy", output)
        self.assertNotIn("• 10 min easy", output)
        self.assertNotIn("▌ Main", output)

    def test_code_block_ends_at_closing_fence(self):
        output = render_markdown(
            "```\ncode\n```\nafter\n",
            color=False,
        )

        self.assertIn("code", output)
        self.assertIn("after", output)
        self.assertNotIn("```", output)

    def test_planned_description_renders_as_nested_code(self):
        event = Event(
            date=date(2026, 11, 5),
            name="SubT",
            type="Run",
            description="# Warm up\n- 15 min easy\n\n## Main\n3 x 10 min",
            duration_s=3600,
        )

        markdown = "\n".join(format_event(event))

        self.assertIn("- Description:", markdown)
        self.assertIn("  ```", markdown)

        output = render_markdown(markdown, color=False)

        self.assertIn("15 min easy", output)
        self.assertIn("3 x 10 min", output)
        self.assertNotIn("```", output)
        self.assertNotIn("▌ Main", output)


if __name__ == "__main__":
    unittest.main()
