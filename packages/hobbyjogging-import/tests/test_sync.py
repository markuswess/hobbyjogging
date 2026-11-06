import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hobbyjogging_core import connect, migrate
from hobbyjogging_import.cli import (
    build_parser,
    resolve_sync_range,
    run_sync_command,
)
from hobbyjogging_import.sync import (
    SyncSummary,
    format_sync_summary,
    run_sync,
)

SAMPLE_FIT = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "fit"
    / "30285-220489711.fit"
)

CALLS = []


class FakeGarminFetcher:

    fail = False
    downloaded = 3
    failed = 0
    errors: list[str] = []

    def __init__(self, connection):
        self.connection = connection

    def fetch(self, start, end):
        CALLS.append(("garmin", start, end))
        if type(self).fail:
            raise RuntimeError("garmin down")
        return SimpleNamespace(
            downloaded=type(self).downloaded,
            failed=type(self).failed,
            errors=list(type(self).errors),
        )


class FakeIntervalsImporter:

    fail = False

    def __init__(self, connection):
        self.connection = connection

    def import_range(self, start, end, *, plan_end=None):
        CALLS.append(("intervals", start, end, plan_end))
        if type(self).fail:
            raise RuntimeError("intervals down")
        return SimpleNamespace(
            activities_imported=4,
            wellness_imported=5,
            events_imported=6,
            events_removed=1,
            events_revived=2,
        )


class FakeFitImporter:

    fail = False

    def __init__(self, connection):
        self.connection = connection

    def import_paths(self, paths, *, recursive=False, skip_known=False):
        CALLS.append(
            ("fit", [Path(path) for path in paths], recursive, skip_known)
        )
        if type(self).fail:
            raise RuntimeError("fit down")
        return SimpleNamespace(
            files_imported=7,
            activities_imported=8,
            activities_matched=9,
            activities_created=1,
        )


def fake_scan(writer, **kwargs):
    CALLS.append(("scan",))
    return SimpleNamespace(recorded=2, findings=3, activities=10)


class SyncTests(unittest.TestCase):

    def setUp(self):
        CALLS.clear()
        FakeGarminFetcher.fail = False
        FakeGarminFetcher.downloaded = 3
        FakeGarminFetcher.failed = 0
        FakeGarminFetcher.errors = []
        FakeIntervalsImporter.fail = False
        FakeFitImporter.fail = False

        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.start = date(2026, 10, 7)
        self.end = date(2026, 11, 6)
        self.plan_end = date(2027, 5, 7)
        self.fit_dir = Path("/tmp/fit")

    def _run(self, **kwargs):
        with patch(
            "hobbyjogging_import.sync.GarminFetcher",
            FakeGarminFetcher,
        ), patch(
            "hobbyjogging_import.sync.IntervalsImporter",
            FakeIntervalsImporter,
        ), patch(
            "hobbyjogging_import.sync.FitImporter",
            FakeFitImporter,
        ), patch(
            "hobbyjogging_import.sync.scan_quality",
            fake_scan,
        ):
            return run_sync(
                self.conn,
                start=self.start,
                end=self.end,
                plan_end=self.plan_end,
                fit_dir=self.fit_dir,
                **kwargs,
            )

    def test_runs_sources_in_order_and_collects_counts(self):
        summary = self._run()

        self.assertEqual(
            ["garmin", "intervals", "fit", "scan"],
            [call[0] for call in CALLS],
        )
        self.assertEqual(
            ("garmin", self.start, self.end),
            CALLS[0],
        )
        self.assertEqual(
            ("intervals", self.start, self.end, self.plan_end),
            CALLS[1],
        )
        self.assertEqual(
            ("fit", [self.fit_dir], True, True),
            CALLS[2],
        )
        self.assertEqual(("scan",), CALLS[3])

        self.assertEqual(3, summary.garmin_fetched)
        self.assertEqual(0, summary.garmin_failed)
        self.assertEqual(4, summary.intervals_activities)
        self.assertEqual(5, summary.intervals_wellness)
        self.assertEqual(6, summary.intervals_events)
        self.assertEqual(1, summary.intervals_removed)
        self.assertEqual(2, summary.intervals_revived)
        self.assertEqual(7, summary.fit_files)
        self.assertEqual(8, summary.fit_activities)
        self.assertEqual(9, summary.fit_matched)
        self.assertEqual(1, summary.fit_created)
        self.assertEqual(2, summary.review_new)
        self.assertEqual(0, summary.review_open)
        self.assertEqual([], summary.failures)

    def test_disabled_sources_are_skipped(self):
        summary = self._run(
            include_garmin=False,
            include_intervals=False,
            include_fit=False,
            include_scan=False,
        )

        self.assertEqual([], CALLS)
        text = format_sync_summary(summary)
        self.assertIn("garmin:    skipped", text)
        self.assertIn("intervals: skipped", text)
        self.assertIn("fit:       skipped", text)
        self.assertIn("review:    skipped", text)

    def test_full_disables_skip_known(self):
        self._run(full=True)

        fit_call = [call for call in CALLS if call[0] == "fit"][0]
        self.assertFalse(fit_call[3])

    def test_scan_defaults_on_and_can_be_disabled(self):
        self._run()
        self.assertIn("scan", [call[0] for call in CALLS])

        CALLS.clear()
        self._run(include_scan=False)
        self.assertNotIn("scan", [call[0] for call in CALLS])

    def test_source_failure_continues_with_remaining_sources(self):
        FakeGarminFetcher.fail = True

        summary = self._run()

        self.assertEqual(
            ["garmin", "intervals", "fit", "scan"],
            [call[0] for call in CALLS],
        )
        self.assertEqual("garmin", summary.failures[0][0])
        self.assertIn(
            "Failures: garmin: garmin down",
            format_sync_summary(summary),
        )

    def test_partial_garmin_failure_is_reported(self):
        FakeGarminFetcher.failed = 1
        FakeGarminFetcher.errors = ["one download failed"]

        summary = self._run()

        self.assertEqual(1, summary.garmin_failed)
        self.assertEqual(("garmin", "one download failed"), summary.failures[0])

    def test_second_sync_has_no_new_failures(self):
        first = self._run()
        second = self._run()

        self.assertEqual([], first.failures)
        self.assertEqual([], second.failures)
        self.assertEqual(2, sum(1 for call in CALLS if call[0] == "garmin"))

    def test_summary_format(self):
        summary = SyncSummary(
            start=date(2026, 10, 7),
            end=date(2026, 11, 6),
            plan_end=date(2027, 5, 7),
            garmin_fetched=3,
            garmin_failed=1,
            intervals_activities=4,
            intervals_wellness=5,
            intervals_events=6,
            intervals_removed=1,
            intervals_revived=2,
            fit_files=7,
            fit_activities=8,
            fit_matched=9,
            fit_created=1,
            review_new=2,
            review_open=11,
            failures=[("garmin", "one download failed")],
        )

        text = format_sync_summary(summary)

        self.assertIn(
            "Sync 2026-11-06 (2026-10-07 .. 2026-11-06, "
            "events to 2027-05-07)",
            text,
        )
        self.assertIn("garmin:    3 fetched, 1 failed", text)
        self.assertIn(
            "intervals: 4 activities, 5 wellness, 6 events "
            "(1 removed, 2 revived)",
            text,
        )
        self.assertIn(
            "fit:       7 files, 8 activities (9 matched, 1 created)",
            text,
        )
        self.assertIn("review:    2 new items, 11 open", text)
        self.assertIn("Failures: garmin: one download failed", text)


class SyncCliTests(unittest.TestCase):

    def test_resolve_range_defaults(self):
        start, end = resolve_sync_range(
            30,
            None,
            today=date(2026, 11, 6),
        )

        self.assertEqual(date(2026, 10, 7), start)
        self.assertEqual(date(2026, 11, 6), end)

    def test_since_overrides_days(self):
        start, end = resolve_sync_range(
            30,
            date(2026, 9, 1),
            today=date(2026, 11, 6),
        )

        self.assertEqual(date(2026, 9, 1), start)
        self.assertEqual(date(2026, 11, 6), end)

    def test_future_since_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_sync_range(
                30,
                date(2026, 11, 7),
                today=date(2026, 11, 6),
            )

    def test_parser_defaults_and_flags(self):
        args = build_parser().parse_args(["sync"])

        self.assertEqual(30, args.days)
        self.assertIsNone(args.since)
        self.assertEqual(182, args.plan_days)
        self.assertFalse(args.no_garmin)
        self.assertFalse(args.no_intervals)
        self.assertFalse(args.no_fit)
        self.assertFalse(args.no_scan)
        self.assertFalse(args.full)

        args = build_parser().parse_args(
            [
                "sync",
                "--days",
                "7",
                "--since",
                "2026-10-01",
                "--plan-days",
                "90",
                "--no-garmin",
                "--no-intervals",
                "--no-fit",
                "--no-scan",
                "--full",
            ]
        )
        self.assertEqual(7, args.days)
        self.assertEqual("2026-10-01", args.since.isoformat())
        self.assertEqual(90, args.plan_days)
        self.assertTrue(args.no_garmin)
        self.assertTrue(args.no_intervals)
        self.assertTrue(args.no_fit)
        self.assertTrue(args.no_scan)
        self.assertTrue(args.full)

    def test_run_command_exits_nonzero_on_failure(self):
        args = build_parser().parse_args(["sync"])
        summary = SyncSummary(
            start=date(2026, 10, 7),
            end=date(2026, 11, 6),
            plan_end=date(2027, 5, 7),
            failures=[("garmin", "down")],
        )

        class FakeConnection:
            def close(self):
                pass

        with patch(
            "hobbyjogging_import.cli.open_database",
            return_value=FakeConnection(),
        ), patch(
            "hobbyjogging_import.cli.run_sync",
            return_value=summary,
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                code = run_sync_command(args, build_parser())

        self.assertEqual(1, code)
        self.assertIn("Failures: garmin: down", output.getvalue())


class SyncIdempotenceTests(unittest.TestCase):

    @unittest.skipUnless(
        SAMPLE_FIT.exists(),
        "sample FIT file is not available",
    )
    def test_second_sync_skips_known_fit_paths(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        fit_dir = Path(temp_dir.name)
        shutil.copy(SAMPLE_FIT, fit_dir / SAMPLE_FIT.name)

        conn = connect(":memory:")
        self.addCleanup(conn.close)
        migrate(conn)

        common = {
            "start": date(2026, 10, 7),
            "end": date(2026, 11, 6),
            "plan_end": date(2027, 5, 7),
            "include_garmin": False,
            "include_intervals": False,
            "include_fit": True,
            "include_scan": True,
            "fit_dir": fit_dir,
        }

        first = run_sync(conn, **common)
        second = run_sync(conn, **common)

        self.assertEqual(1, first.fit_files)
        self.assertEqual(1, first.fit_activities)
        self.assertEqual(0, second.fit_files)
        self.assertEqual(0, second.fit_activities)
        self.assertEqual(
            1,
            conn.execute(
                "SELECT COUNT(*) FROM activities"
            ).fetchone()[0],
        )


if __name__ == "__main__":
    unittest.main()
