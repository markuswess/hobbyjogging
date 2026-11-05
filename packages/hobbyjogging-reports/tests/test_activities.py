import unittest
from datetime import date

from hobbyjogging_report.activity_list import (
    DEFAULT_COLUMNS,
    ActivityQuery,
    activities_report,
    parse_activities_args,
)
from hobbyjogging_report.commands import COMMANDS, command_help
from support import FakeSource, activity_factory, make_interval

make_activity = activity_factory()
TODAY = date(2026, 10, 30)


def data_rows(report):
    rows = [line for line in report.splitlines() if line.startswith("| ")]
    return rows[1:]


class ParseActivitiesArgsTests(unittest.TestCase):

    def test_defaults_use_last_twenty_and_default_columns(self):
        self.assertEqual(
            ActivityQuery(columns=DEFAULT_COLUMNS),
            parse_activities_args([], today=TODAY),
        )

    def test_default_columns_exclude_id_and_category(self):
        self.assertNotIn("id", DEFAULT_COLUMNS)
        self.assertNotIn("category", DEFAULT_COLUMNS)

    def test_add_appends_to_defaults(self):
        query = parse_activities_args(["--add", "id,category"], today=TODAY)

        self.assertEqual(
            (*DEFAULT_COLUMNS, "id", "category"),
            query.columns,
        )

    def test_add_existing_column_is_not_duplicated(self):
        query = parse_activities_args(["--add", "date"], today=TODAY)

        self.assertEqual(DEFAULT_COLUMNS, query.columns)

    def test_columns_replaces_defaults_in_given_order(self):
        query = parse_activities_args(
            ["--columns", "name,date,distance"],
            today=TODAY,
        )

        self.assertEqual(("name", "date", "distance"), query.columns)

    def test_columns_and_add_are_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            parse_activities_args(
                ["--columns", "date", "--add", "id"],
                today=TODAY,
            )

    def test_unknown_column_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "bogus"):
            parse_activities_args(["--columns", "bogus"], today=TODAY)

    def test_limit_must_be_positive(self):
        with self.assertRaises(ValueError):
            parse_activities_args(["--limit", "0"], today=TODAY)

    def test_days_option_selects_a_range_without_limit(self):
        query = parse_activities_args(["--days", "7"], today=TODAY)

        self.assertEqual(date(2026, 10, 23), query.start)
        self.assertEqual(TODAY, query.end)
        self.assertIsNone(query.limit)

    def test_to_alone_counts_back_default_days(self):
        query = parse_activities_args(
            ["--to", "2026-10-10"],
            today=TODAY,
        )

        self.assertEqual(date(2026, 9, 10), query.start)
        self.assertEqual(date(2026, 10, 10), query.end)


class ActivitiesReportTests(unittest.TestCase):

    def setUp(self):
        self.source = FakeSource(
            [
                make_activity(
                    id=f"a{day}",
                    date=date(2026, 10, day),
                    name=f"Run {day}",
                )
                for day in range(1, 26)
            ]
        )

    def test_default_shows_newest_twenty(self):
        report = activities_report(
            self.source,
            ActivityQuery(),
            today=TODAY,
        )

        rows = data_rows(report)

        self.assertEqual(20, len(rows))
        self.assertIn("2026-10-25", rows[0])
        self.assertIn("2026-10-06", rows[-1])
        self.assertNotIn("2026-10-05", report)

    def test_range_with_limit_is_capped(self):
        report = activities_report(
            self.source,
            ActivityQuery(date(2026, 10, 1), date(2026, 10, 25), 3),
            today=TODAY,
        )

        rows = data_rows(report)

        self.assertEqual(3, len(rows))
        self.assertIn("2026-10-23", rows[-1])

    def test_range_without_limit_shows_everything_in_range(self):
        report = activities_report(
            self.source,
            ActivityQuery(date(2026, 10, 1), date(2026, 10, 5)),
            today=TODAY,
        )

        self.assertEqual(5, len(data_rows(report)))

    def test_default_columns_omit_id(self):
        source = FakeSource([make_activity(id="abc-123", name="Easy")])

        report = activities_report(source, ActivityQuery(), today=TODAY)

        self.assertNotIn("abc-123", report)

    def test_added_id_column_is_shown(self):
        source = FakeSource([make_activity(id="abc-123", name="Easy")])
        query = ActivityQuery(columns=(*DEFAULT_COLUMNS, "id"))

        report = activities_report(source, query, today=TODAY)

        self.assertIn("abc-123", report)

    def test_category_is_computed_from_intervals_for_subt(self):
        source = FakeSource(
            [
                make_activity(
                    id="s1",
                    name="5x5' subT medium",
                    rpe=5,
                ),
            ],
            {
                "s1": [
                    make_interval(300, 1000, group_id="g")
                    for _ in range(5)
                ],
            },
        )
        query = ActivityQuery(columns=("date", "name", "category"))

        report = activities_report(source, query, today=TODAY)

        self.assertIn("quality/intervals/subt-medium", report)

    def test_review_excluded_activities_are_skipped_with_note(self):
        source = FakeSource(
            [
                make_activity(id="ok", date=date(2026, 10, 2), name="Kept"),
                make_activity(
                    id="flag",
                    date=date(2026, 10, 3),
                    name="Hidden",
                    needs_review=True,
                ),
            ]
        )

        report = activities_report(
            source,
            ActivityQuery(date(2026, 10, 1), date(2026, 10, 5)),
            today=TODAY,
        )

        self.assertIn("1 activity excluded (import review)", report)
        self.assertNotIn("Hidden", report)
        self.assertIn("Kept", report)

    def test_pipes_in_names_do_not_break_the_table(self):
        source = FakeSource([make_activity(name="a | b")])

        report = activities_report(source, ActivityQuery(), today=TODAY)

        self.assertIn("a / b", report)

    def test_empty_range_message(self):
        report = activities_report(
            FakeSource(),
            ActivityQuery(date(2026, 10, 1), date(2026, 10, 2)),
            today=TODAY,
        )

        self.assertIn("- No activities", report)
        self.assertNotIn("| date", report)


class ActivitiesCommandTests(unittest.TestCase):

    def test_help_lists_default_and_available_columns(self):
        output = command_help(COMMANDS["activities"])

        self.assertIn("default columns:", output)
        self.assertIn("available columns:", output)
        self.assertIn("category", output)


if __name__ == "__main__":
    unittest.main()
