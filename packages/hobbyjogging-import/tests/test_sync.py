import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hobbyjogging_core import connect, migrate
from hobbyjogging_core.sources_config import SourcesConfig, default_policies
from hobbyjogging_import.sync import (
    SyncSummary,
    format_sync_summary,
    run_sync,
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


class FakeRunalyzeEnricher:

    stopped = ""

    def __init__(self, connection, client=None, *, create="review"):
        self.connection = connection

    def enrich(self, *, start=None, end=None, **kwargs):
        CALLS.append(("runalyze", start, end))
        return SimpleNamespace(
            processed=10,
            matched=8,
            unmatched=1,
            ambiguous=1,
            not_processed=2 if type(self).stopped else 0,
            stopped_reason=type(self).stopped,
        )


class FakeGearImporter:

    def __init__(self, connection):
        self.connection = connection

    def import_gear(self, **kwargs):
        CALLS.append(("gear",))
        return SimpleNamespace(created=2, linked_existing=1)


class FakeVo2maxImporter:

    def __init__(self, connection):
        self.connection = connection

    def import_vo2max(self, **kwargs):
        CALLS.append(("vo2max",))
        return SimpleNamespace(written=5)


class FakeRaceImporter:

    def __init__(self, connection, client):
        self.connection = connection

    def import_races(self, **kwargs):
        CALLS.append(("races",))
        return SimpleNamespace(written=1)


class FakeStravaImporter:

    def __init__(self, connection, *, create, title, description):
        self.connection = connection

    def import_export(self, path, **kwargs):
        CALLS.append(("strava", Path(path)))
        return SimpleNamespace(social_written=20, activities_created=2)


def fake_scan(writer, **kwargs):
    CALLS.append(("scan",))
    return SimpleNamespace(recorded=2, findings=3, activities=10)


def all_enabled(**overrides):
    policies = dict(default_policies())
    for name, values in overrides.items():
        policies[name] = policies[name].__class__(
            **{**policies[name].__dict__, **values}
        )
    return SourcesConfig(policies=policies)


class SyncTests(unittest.TestCase):

    def setUp(self):
        CALLS.clear()
        FakeGarminFetcher.fail = False
        FakeGarminFetcher.downloaded = 3
        FakeGarminFetcher.failed = 0
        FakeGarminFetcher.errors = []
        FakeIntervalsImporter.fail = False
        FakeFitImporter.fail = False
        FakeRunalyzeEnricher.stopped = ""

        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.start = date(2026, 10, 7)
        self.end = date(2026, 11, 6)
        self.plan_end = date(2027, 5, 7)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fit_dir = Path(self.tmp.name) / "fit"
        self.fit_dir.mkdir()
        self.export = Path(self.tmp.name) / "export_1.zip"
        self.export.write_bytes(b"zip")
        self.config = all_enabled()

    def _run(
        self,
        *,
        garmin_key="garmin-key",
        intervals=("athlete", "key"),
        runalyze_key="runalyze-key",
        export=Ellipsis,
        **kwargs,
    ):
        export = self.export if export is Ellipsis else export
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
            "hobbyjogging_import.sync.RunalyzeEnricher",
            FakeRunalyzeEnricher,
        ), patch(
            "hobbyjogging_import.sync.RunalyzeGearImporter",
            FakeGearImporter,
        ), patch(
            "hobbyjogging_import.sync.RunalyzeClient",
            return_value=object(),
        ), patch(
            "hobbyjogging_import.sync.RunalyzeVo2maxImporter",
            FakeVo2maxImporter,
        ), patch(
            "hobbyjogging_import.sync.RunalyzeRaceImporter",
            FakeRaceImporter,
        ), patch(
            "hobbyjogging_import.sync.StravaCsvImporter",
            FakeStravaImporter,
        ), patch(
            "hobbyjogging_import.sync.newest_unimported_export",
            return_value=export,
        ), patch(
            "hobbyjogging_import.sync.garmin_api_key",
            return_value=garmin_key,
        ), patch(
            "hobbyjogging_import.sync.intervals_credentials",
            return_value=intervals,
        ), patch(
            "hobbyjogging_import.sync.runalyze_api_key",
            return_value=runalyze_key,
        ), patch(
            "hobbyjogging_import.sync.scan_quality",
            fake_scan,
        ):
            return run_sync(
                self.conn,
                start=self.start,
                end=self.end,
                plan_end=self.plan_end,
                config=self.config,
                fit_dir=self.fit_dir,
                strava_dir=Path(self.tmp.name),
                **kwargs,
            )

    def test_runs_sources_in_order_and_collects_counts(self):
        summary = self._run()

        self.assertEqual(
            [
                "garmin",
                "intervals",
                "fit",
                "runalyze",
                "gear",
                "vo2max",
                "races",
                "strava",
                "scan",
            ],
            [call[0] for call in CALLS],
        )
        self.assertEqual(("garmin", self.start, self.end), CALLS[0])
        self.assertEqual(
            ("intervals", self.start, self.end, self.plan_end),
            CALLS[1],
        )
        self.assertEqual(("fit", [self.fit_dir], True, True), CALLS[2])
        self.assertEqual(("runalyze", self.start, self.end), CALLS[3])
        self.assertEqual(("scan",), CALLS[-1])

        self.assertEqual(3, summary.garmin_fetched)
        self.assertEqual(4, summary.intervals_activities)
        self.assertEqual(7, summary.fit_files)
        self.assertEqual(10, summary.runalyze_processed)
        self.assertEqual(2, summary.runalyze_unmatched)
        self.assertEqual(3, summary.runalyze_gear)
        self.assertEqual(5, summary.runalyze_vo2max)
        self.assertEqual(1, summary.runalyze_races)
        self.assertEqual(self.export, summary.strava_path)
        self.assertEqual(20, summary.strava_social)
        self.assertEqual(2, summary.strava_created)
        self.assertEqual(2, summary.review_new)
        self.assertEqual([], summary.failures)
        self.assertEqual([], summary.skips)

        text = format_sync_summary(summary)
        self.assertIn("runalyze:", text)
        self.assertIn("strava:", text)
        self.assertIn("derived:", text)
        self.assertIn("timing:", text)

    def test_disabled_sources_are_skipped(self):
        summary = self._run(
            include_garmin=False,
            include_intervals=False,
            include_fit=False,
            include_runalyze=False,
            include_strava=False,
            include_scan=False,
        )

        self.assertEqual([], CALLS)
        text = format_sync_summary(summary)
        self.assertIn("garmin:    skipped", text)
        self.assertIn("intervals: skipped", text)
        self.assertIn("fit:       skipped", text)
        self.assertIn("runalyze:  skipped", text)
        self.assertIn("strava:    skipped", text)
        self.assertIn("review:    skipped", text)
        self.assertNotIn("timing:", text)

    def test_a_missing_credential_skips_the_source(self):
        summary = self._run(
            garmin_key=None,
            intervals=(None, None),
            runalyze_key=None,
        )

        self.assertEqual([], summary.failures)
        sources = [source for source, _ in summary.skips]
        self.assertIn("garmin", sources)
        self.assertIn("intervals", sources)
        self.assertIn("runalyze", sources)
        # The offline derivations still run without a key.
        self.assertEqual(5, summary.runalyze_vo2max)
        self.assertNotIn(("races",), CALLS)
        self.assertIn("Skipped: garmin:", format_sync_summary(summary))

    def test_sources_disabled_in_the_config_are_skipped(self):
        self.config = all_enabled(
            garmin={"enabled": False},
            intervals={"enabled": False},
        )

        summary = self._run()

        self.assertEqual([], summary.failures)
        self.assertIn(
            ("garmin", "disabled in sources.toml"),
            summary.skips,
        )
        self.assertIn(
            ("intervals", "disabled in sources.toml"),
            summary.skips,
        )
        self.assertNotIn("garmin", [call[0] for call in CALLS])

    def test_a_missing_fit_directory_is_a_skip(self):
        self.fit_dir.rmdir()

        summary = self._run()

        self.assertEqual([], summary.failures)
        self.assertIn("fit", [source for source, _ in summary.skips])

    def test_a_source_failure_continues_with_remaining_sources(self):
        FakeGarminFetcher.fail = True

        summary = self._run()

        self.assertIn("scan", [call[0] for call in CALLS])
        self.assertEqual("garmin", summary.failures[0][0])
        self.assertIn(
            "Failures: garmin: garmin down",
            format_sync_summary(summary),
        )

    def test_a_rate_limited_runalyze_is_a_warning_not_a_failure(self):
        FakeRunalyzeEnricher.stopped = "rate limit"

        summary = self._run()

        self.assertEqual([], summary.failures)
        self.assertEqual("rate limit", summary.runalyze_stopped)
        self.assertEqual(2, summary.runalyze_pending)
        self.assertIn("runalyze", [source for source, _ in summary.skips])

    def test_no_new_strava_export_is_a_skip(self):
        summary = self._run(export=None)

        self.assertEqual([], summary.failures)
        self.assertIn("strava", [source for source, _ in summary.skips])
        self.assertIn("strava:    no new export", format_sync_summary(summary))

    def test_partial_garmin_failure_is_reported(self):
        FakeGarminFetcher.failed = 1
        FakeGarminFetcher.errors = ["one download failed"]

        summary = self._run()

        self.assertEqual(1, summary.garmin_failed)
        self.assertEqual(("garmin", "one download failed"), summary.failures[0])

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
            runalyze_processed=10,
            runalyze_matched=8,
            runalyze_unmatched=2,
            runalyze_gear=3,
            runalyze_vo2max=4,
            runalyze_races=1,
            strava_path=Path("export_1.zip"),
            strava_social=20,
            strava_created=2,
            review_new=2,
            review_open=11,
            skips=[("garmin", "no key")],
            failures=[("garmin", "one download failed")],
        )
        text = format_sync_summary(summary)
        self.assertIn("Sync 2026-11-06", text)
        self.assertIn("runalyze:  10 processed", text)
        self.assertIn("strava:    export_1.zip: 20 social, 2 created", text)
        self.assertIn("Skipped: garmin: no key", text)
        self.assertIn("Failures: garmin: one download failed", text)


if __name__ == "__main__":
    unittest.main()
