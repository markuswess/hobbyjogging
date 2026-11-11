import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from hobbyjogging_report.__main__ import main
from hobbyjogging_report.commands import COMMANDS, command_help, usage

EXPECTED = {
    "activities",
    "daily",
    "overview",
    "weekly",
    "monthly",
    "yearly",
    "all",
    "dashboard",
    "report",
    "compare",
    "subt-report",
    "subt-ewma-report",
    "recovery-report",
    "planned",
    "session",
    "classify",
    "volume",
    "compare-chart",
    "overview-chart",
    "load",
    "pace-hr",
    "time",
    "recovery",
    "subt",
    "vo2max",
    "debug",
}


class CommandRegistryTests(unittest.TestCase):

    def test_expected_commands_exist(self):
        self.assertEqual(EXPECTED, set(COMMANDS))

    def test_every_command_has_help_and_handler(self):
        for command in COMMANDS.values():
            self.assertTrue(command.summary)
            self.assertTrue(command.usage)
            self.assertTrue(callable(command.run))

    def test_global_usage_lists_commands_and_help_hint(self):
        output = usage()

        for name in EXPECTED:
            self.assertIn(name, output)

        self.assertIn("--help", output)

    def test_command_help_contains_usage_and_examples(self):
        output = command_help(COMMANDS["time"])

        self.assertIn("time [output.png]", output)
        self.assertIn("charts.sh time --days 90", output)
        self.assertIn("global options", output)

    def test_debug_help_mentions_api_credentials(self):
        output = command_help(COMMANDS["debug"])

        self.assertIn("INTERVALS_ATHLETE_ID", output)
        self.assertNotIn("global options", output)


class MainHelpTests(unittest.TestCase):

    def test_global_help(self):
        output = io.StringIO()

        with redirect_stdout(output):
            main(["--help"])

        self.assertIn("commands:", output.getvalue())
        self.assertIn("recovery", output.getvalue())

    def test_command_help_does_not_open_a_source(self):
        output = io.StringIO()

        with redirect_stdout(output):
            main(["volume", "--help"])

        self.assertIn("volume [output.png]", output.getvalue())
        self.assertIn("charts.sh volume --days 90", output.getvalue())

    def test_session_help(self):
        output = io.StringIO()

        with redirect_stdout(output):
            main(["session", "--help"])

        self.assertIn("session [YYYY-MM-DD|ACTIVITY_ID|last]", output.getvalue())

    def test_unknown_command_exits_with_usage(self):
        output = io.StringIO()

        with redirect_stderr(output):
            with self.assertRaises(SystemExit) as caught:
                main(["not-a-command"])

        self.assertEqual(2, caught.exception.code)
        self.assertIn("commands:", output.getvalue())


if __name__ == "__main__":
    unittest.main()
