import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_import.cli import build_parser
from hobbyjogging_import.config import default_fit_dir, resolve_fit_path
from hobbyjogging_import.fit import (
    canonical_sport,
    fit_file_to_dict,
    format_duration,
    format_fit_file,
    format_pace,
    format_speed,
    parse_fit_file,
    read_fit_file_id,
    summarize_fit_messages,
)

UTC = timezone.utc
SAMPLE_FIT = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "fit"
    / "30285-220489711.fit"
)
SAMPLE_VO2MAX_FIT = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "fit"
    / "30285-18667256.fit"
)


def _sample_messages():
    start = datetime(2026, 11, 1, 9, 35, 8, tzinfo=UTC)
    finish = datetime(2026, 11, 1, 10, 18, 1, tzinfo=UTC)

    file_id = {
        "type": "activity",
        "manufacturer": "garmin",
        "garmin_product": "enduro",
        "serial_number": 3386253273,
        "time_created": datetime(2026, 11, 1, 9, 35, 7, tzinfo=UTC),
    }
    activity = {
        "timestamp": finish,
        "local_timestamp": datetime(2026, 11, 1, 11, 18, 1, tzinfo=UTC),
    }
    session = {
        "start_time": start,
        "sport": "running",
        "sub_sport": "generic",
        "sport_profile_name": "Run",
        "total_elapsed_time": 2562.121,
        "total_timer_time": 2562.121,
        "total_moving_time": 2500.0,
        "total_distance": 10166.61,
        "avg_heart_rate": 151,
        "max_heart_rate": 169,
        "total_ascent": 41,
        "total_calories": 628,
        "first_lap_index": 0,
        "num_laps": 1,
    }
    lap = {
        "start_time": start,
        "total_timer_time": 325.873,
        "total_distance": 1179.55,
        "avg_heart_rate": 123,
        "max_heart_rate": 132,
        "total_ascent": 2,
    }

    return file_id, activity, session, lap


class FitSummaryTests(unittest.TestCase):

    def test_maps_session_and_lap(self):
        file_id, activity, session, lap = _sample_messages()

        summary = summarize_fit_messages(
            Path("sample.fit"),
            file_id,
            activity,
            [session],
            [lap],
            record_count=10,
        )

        self.assertEqual("activity", summary.file_type)
        self.assertEqual("garmin", summary.manufacturer)
        self.assertEqual("enduro", summary.product)
        self.assertEqual("2026-11-01T09:35:07Z", summary.time_created)
        self.assertEqual(10, summary.record_count)
        self.assertEqual(1, len(summary.sessions))

        mapped = summary.sessions[0]

        self.assertEqual("2026-11-01T09:35:08Z", mapped.start_time_utc)
        self.assertEqual("2026-11-01T10:35:08+01:00", mapped.local_start)
        self.assertEqual(60, mapped.tz_offset_min)
        self.assertEqual("run", mapped.canonical_sport)
        self.assertEqual("Run", mapped.name)
        self.assertEqual(2562.121, mapped.duration_s)
        self.assertEqual(2500.0, mapped.moving_s)
        self.assertEqual(10166.61, mapped.distance_m)
        self.assertEqual(151, mapped.avg_hr)
        self.assertEqual(169, mapped.max_hr)
        self.assertEqual(41, mapped.ascent_m)
        self.assertEqual(628, mapped.calories)
        self.assertEqual(1, len(mapped.laps))

        lap_summary = mapped.laps[0]

        self.assertEqual(1, lap_summary.index)
        self.assertEqual(325.873, lap_summary.duration_s)
        self.assertEqual(1179.55, lap_summary.distance_m)
        self.assertEqual(123, lap_summary.avg_hr)
        self.assertEqual(132, lap_summary.max_hr)
        self.assertEqual(2, lap_summary.elevation_gain_m)

    def test_maps_vo2max_to_single_session(self):
        file_id, activity, session, lap = _sample_messages()

        summary = summarize_fit_messages(
            Path("sample.fit"),
            file_id,
            activity,
            [session],
            [lap],
            vo2max_garmin=[65.283935546875],
        )

        self.assertAlmostEqual(
            65.283935546875,
            summary.sessions[0].vo2max_garmin,
        )

    def test_vo2max_values_follow_sessions_when_counts_match(self):
        start = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
        sessions = [
            {
                "start_time": start,
                "sport": "running",
                "first_lap_index": 0,
                "num_laps": 0,
            },
            {
                "start_time": datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
                "sport": "cycling",
                "first_lap_index": 0,
                "num_laps": 0,
            },
        ]

        summary = summarize_fit_messages(
            Path("sample.fit"),
            {"type": "activity"},
            {},
            sessions,
            [],
            vo2max_garmin=[60.1, 61.2],
        )

        self.assertEqual(60.1, summary.sessions[0].vo2max_garmin)
        self.assertEqual(61.2, summary.sessions[1].vo2max_garmin)

    def test_file_level_vo2max_goes_to_last_session(self):
        start = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
        sessions = [
            {
                "start_time": start,
                "sport": "running",
                "first_lap_index": 0,
                "num_laps": 0,
            },
            {
                "start_time": datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
                "sport": "cycling",
                "first_lap_index": 0,
                "num_laps": 0,
            },
        ]

        summary = summarize_fit_messages(
            Path("sample.fit"),
            {"type": "activity"},
            {},
            sessions,
            [],
            vo2max_garmin=[65.28],
        )

        self.assertIsNone(summary.sessions[0].vo2max_garmin)
        self.assertEqual(65.28, summary.sessions[1].vo2max_garmin)

    def test_slices_laps_for_multiple_sessions(self):
        start = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
        file_id = {"type": "activity"}
        sessions = [
            {
                "start_time": start,
                "sport": "running",
                "first_lap_index": 0,
                "num_laps": 1,
            },
            {
                "start_time": datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
                "sport": "cycling",
                "first_lap_index": 1,
                "num_laps": 1,
            },
        ]
        laps = [
            {"start_time": start, "total_timer_time": 60},
            {
                "start_time": datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
                "total_timer_time": 120,
            },
        ]

        summary = summarize_fit_messages(
            Path("sample.fit"),
            file_id,
            {},
            sessions,
            laps,
        )

        self.assertEqual(2, len(summary.sessions))
        self.assertEqual(1, len(summary.sessions[0].laps))
        self.assertEqual(1, len(summary.sessions[1].laps))
        self.assertEqual(2, summary.sessions[1].laps[0].index)
        self.assertEqual(120, summary.sessions[1].laps[0].duration_s)

    def test_non_activity_file_has_no_sessions(self):
        summary = summarize_fit_messages(
            Path("monitoring.fit"),
            {"type": "monitoring_b"},
            {},
            [],
            [],
        )

        self.assertEqual([], summary.sessions)
        self.assertIn(
            "No activity session found.",
            format_fit_file(summary),
        )

    def test_json_output_is_serializable(self):
        file_id, activity, session, lap = _sample_messages()
        summary = summarize_fit_messages(
            Path("sample.fit"),
            file_id,
            activity,
            [session],
            [lap],
            vo2max_garmin=[65.28],
        )

        payload = json.dumps(fit_file_to_dict(summary))
        self.assertIn('"canonical_sport": "run"', payload)
        self.assertIn('"vo2max_garmin": 65.28', payload)

    def test_formats_vo2max(self):
        file_id, activity, session, lap = _sample_messages()
        summary = summarize_fit_messages(
            Path("sample.fit"),
            file_id,
            activity,
            [session],
            [lap],
            vo2max_garmin=[65.283935546875],
        )

        self.assertIn(
            "VO2max: 65.28 mL/kg/min",
            format_fit_file(summary),
        )

    def test_formats_summary(self):
        file_id, activity, session, lap = _sample_messages()
        summary = summarize_fit_messages(
            Path("sample.fit"),
            file_id,
            activity,
            [session],
            [lap],
        )

        output = format_fit_file(summary)

        self.assertIn("Device: Garmin Enduro (serial 3386253273)", output)
        self.assertIn("Sport: running / generic -> run", output)
        self.assertIn("Pace: 4:12/km", output)
        self.assertIn("Laps: 1", output)


class FitFormattingTests(unittest.TestCase):

    def test_canonical_sport(self):
        self.assertEqual("run", canonical_sport("running", "generic"))
        self.assertEqual(
            "trail_run",
            canonical_sport("running", "trail"),
        )
        self.assertEqual("ride", canonical_sport("cycling", "road"))
        self.assertEqual("other", canonical_sport("other"))
        self.assertEqual(
            "gravel_ride",
            canonical_sport("cycling", "gravel_cycling"),
        )
        self.assertEqual("mtb_ride", canonical_sport("cycling", "mountain"))
        self.assertEqual(
            "treadmill_run",
            canonical_sport("running", "treadmill"),
        )
        self.assertEqual(
            "openwaterswim",
            canonical_sport("swimming", "open_water"),
        )

    def test_format_duration(self):
        self.assertEqual("0:00", format_duration(0))
        self.assertEqual("42:42", format_duration(2562.121))
        self.assertEqual("1:02:03", format_duration(3723))

    def test_format_pace(self):
        self.assertEqual("4:12/km", format_pace(2562.121, 10166.61))
        self.assertEqual("-", format_pace(0, 1000))
        self.assertEqual("-", format_pace(100, 0))

    def test_format_speed(self):
        self.assertEqual("14.3 km/h", format_speed(2562.121, 10166.61))
        self.assertEqual("-", format_speed(0, 1000))
        self.assertEqual("-", format_speed(100, 0))


class FitConfigTests(unittest.TestCase):

    def test_default_fit_dir(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Path("data/fit"), default_fit_dir())

    def test_fit_dir_from_environment(self):
        with patch.dict(
            os.environ,
            {"HOBBYJOGGING_FIT_DIR": "~/fit-files"},
            clear=True,
        ):
            self.assertEqual(
                Path("~/fit-files").expanduser(),
                default_fit_dir(),
            )

    def test_resolves_filename_from_fit_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "sample.fit"
            sample.write_bytes(b"")

            with patch.dict(
                os.environ,
                {"HOBBYJOGGING_FIT_DIR": tmp},
                clear=True,
            ):
                self.assertEqual(sample, resolve_fit_path("sample.fit"))


class FitCliTests(unittest.TestCase):

    def test_inspect_argument(self):
        args = build_parser().parse_args(
            ["fit", "--inspect", "data/fit/sample.fit"]
        )

        self.assertEqual(Path("data/fit/sample.fit"), args.inspect)
        self.assertFalse(args.json)

    def test_import_arguments(self):
        args = build_parser().parse_args(
            [
                "fit",
                "--from",
                "2026-10-01",
                "--to",
                "2026-10-02",
                "--recursive",
                "--dry-run",
                "--limit",
                "5",
                "data/fit",
            ]
        )

        self.assertIsNone(args.inspect)
        self.assertFalse(args.json)
        self.assertTrue(args.recursive)
        self.assertTrue(args.dry_run)
        self.assertEqual(5, args.limit)
        self.assertEqual("2026-10-01", args.start.isoformat())
        self.assertEqual("2026-10-02", args.end.isoformat())
        self.assertEqual([Path("data/fit")], args.paths)

    def test_limit_zero_parses_and_is_checked_at_runtime(self):
        args = build_parser().parse_args(["fit", "--limit", "0", "data/fit"])

        self.assertEqual(0, args.limit)


class FitSampleTests(unittest.TestCase):

    @unittest.skipUnless(
        SAMPLE_FIT.exists(),
        "sample FIT file is not available",
    )
    def test_reads_real_sample_file_id(self):
        file_id = read_fit_file_id(SAMPLE_FIT)

        self.assertEqual("activity", file_id["type"])
        self.assertEqual("garmin", file_id["manufacturer"])

    @unittest.skipUnless(
        SAMPLE_VO2MAX_FIT.exists(),
        "sample FIT file with VO2max is not available",
    )
    def test_parses_real_vo2max_without_rounding(self):
        summary = parse_fit_file(SAMPLE_VO2MAX_FIT)

        self.assertEqual(1, len(summary.sessions))
        self.assertAlmostEqual(
            62.98323059082031,
            summary.sessions[0].vo2max_garmin,
        )
        self.assertIn(
            "VO2max: 62.98 mL/kg/min",
            format_fit_file(summary),
        )

    def test_parses_real_sample(self):
        summary = parse_fit_file(SAMPLE_FIT)

        self.assertEqual("activity", summary.file_type)
        self.assertEqual(1, len(summary.sessions))

        session = summary.sessions[0]

        self.assertEqual("run", session.canonical_sport)
        self.assertEqual("2026-11-01T09:35:08Z", session.start_time_utc)
        self.assertEqual("2026-11-01T10:35:08+01:00", session.local_start)
        self.assertEqual(11, len(session.laps))
        self.assertEqual(151, session.avg_hr)
        self.assertEqual(10166.61, session.distance_m)


if __name__ == "__main__":
    unittest.main()
