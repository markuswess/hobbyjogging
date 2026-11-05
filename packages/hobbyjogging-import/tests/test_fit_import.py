import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from hobbyjogging_core import TrainingRepository, connect, migrate
from hobbyjogging_import.fit import FitFileSummary, FitLap, FitSession
from hobbyjogging_import.fit_import import FitImporter, discover_fit_files

START_UTC = "2026-10-01T06:00:00Z"
LOCAL_START = "2026-10-01T08:00:00+02:00"


def _summary(
    path: Path,
    *,
    start_utc: str = START_UTC,
    local_start: str = LOCAL_START,
    elapsed_s: float = 3700,
    duration_s: float = 3600,
    distance_m: float = 10000,
    name: str = "FIT Run",
    lap_start: str = "2026-10-01T06:00:00Z",
    vo2max_garmin: float | None = None,
) -> FitFileSummary:
    return FitFileSummary(
        path=path,
        file_type="activity",
        manufacturer="garmin",
        product="enduro",
        serial_number="123",
        time_created="2026-10-01T05:59:00Z",
        record_count=10,
        sessions=[
            FitSession(
                index=1,
                start_time_utc=start_utc,
                local_start=local_start,
                tz_offset_min=120,
                sport="running",
                sub_sport="generic",
                canonical_sport="run",
                name=name,
                elapsed_s=elapsed_s,
                duration_s=duration_s,
                distance_m=distance_m,
                avg_hr=140,
                max_hr=170,
                ascent_m=20,
                calories=500,
                vo2max_garmin=vo2max_garmin,
                laps=[
                    FitLap(
                        index=1,
                        start_time_utc=lap_start,
                        duration_s=duration_s,
                        distance_m=distance_m,
                        avg_hr=140,
                        max_hr=170,
                        elevation_gain_m=20,
                    )
                ],
            )
        ],
    )


class FitImporterTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.fit_dir = Path(self.temp_dir.name)
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.importer = FitImporter(self.conn)
        self.repository = TrainingRepository(self.conn)

    def _file(self, name: str, content: bytes) -> Path:
        path = self.fit_dir / name
        path.write_bytes(content)
        return path

    def _import(self, summaries, **kwargs):
        by_name = {summary.path.name: summary for summary in summaries}
        with patch(
            "hobbyjogging_import.fit_import.read_fit_file_id",
            return_value={"type": "activity"},
        ), patch(
            "hobbyjogging_import.fit_import.parse_fit_file",
            side_effect=lambda path: by_name[Path(path).name],
        ):
            return self.importer.import_paths([self.fit_dir], **kwargs)

    def _activities(self):
        return self.repository.activities(
            date(2026, 10, 1),
            date(2026, 10, 1),
        )

    def test_import_creates_activity_source_link_and_laps(self):
        path = self._file("one.fit", b"one")

        summary = self._import([_summary(path)])

        self.assertEqual(1, summary.files_seen)
        self.assertEqual(1, summary.files_imported)
        self.assertEqual(1, summary.activities_imported)
        self.assertEqual(1, summary.activities_created)
        self.assertEqual(0, summary.activities_matched)
        self.assertEqual(1, summary.laps_imported)
        self.assertEqual(0, summary.activities_skipped)

        activities = self._activities()
        self.assertEqual(1, len(activities))
        activity = activities[0]
        self.assertEqual("run", activity.type)
        self.assertEqual("FIT Run", activity.name)
        self.assertEqual(3600, activity.duration_s)
        self.assertEqual(3700, activity.elapsed_s)
        self.assertEqual(10000, activity.distance_m)
        self.assertEqual(140, activity.avg_hr)
        self.assertEqual(START_UTC, activity.started_at_utc)

        sources = self.conn.execute(
            "SELECT source, record_type, external_id FROM source_records"
        ).fetchall()
        self.assertEqual(1, len(sources))
        self.assertEqual("fit", sources[0]["source"])
        self.assertEqual("activity", sources[0]["record_type"])

        links = self.conn.execute(
            "SELECT match_method, is_primary FROM activity_sources"
        ).fetchall()
        self.assertEqual(1, len(links))
        self.assertEqual("created", links[0]["match_method"])
        self.assertEqual(1, links[0]["is_primary"])

        laps = self.repository.activity_laps(activity.id)
        self.assertEqual(1, len(laps))
        self.assertEqual(10000, laps[0].distance_m)

        run = self.conn.execute(
            "SELECT status, records_seen, records_imported "
            "FROM import_runs WHERE id = ?",
            (summary.run_id,),
        ).fetchone()
        self.assertEqual("success", run["status"])
        self.assertEqual(1, run["records_seen"])
        self.assertEqual(1, run["records_imported"])

    def test_import_writes_garmin_vo2max_without_rounding(self):
        path = self._file("one.fit", b"one")

        summary = self._import(
            [_summary(path, vo2max_garmin=65.283935546875)]
        )

        self.assertEqual(1, summary.vo2max_imported)
        activity = self._activities()[0]
        self.assertAlmostEqual(65.283935546875, activity.vo2max_garmin)
        self.assertIsNone(activity.vo2max_runalyze)
        self.assertAlmostEqual(65.283935546875, activity.vo2max)

    def test_import_without_vo2max_leaves_the_fields_empty(self):
        path = self._file("one.fit", b"one")

        summary = self._import([_summary(path)])

        self.assertEqual(0, summary.vo2max_imported)
        activity = self._activities()[0]
        self.assertIsNone(activity.vo2max_garmin)
        self.assertIsNone(activity.vo2max_runalyze)
        self.assertIsNone(activity.vo2max)

    def test_reimport_is_idempotent(self):
        path = self._file("one.fit", b"one")
        first = self._import([_summary(path)])
        activity_id = self._activities()[0].id

        second = self._import([_summary(path)])

        self.assertEqual(1, len(self._activities()))
        self.assertEqual(activity_id, self._activities()[0].id)
        self.assertEqual(0, second.activities_created)
        self.assertEqual(1, second.activities_matched)
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM activity_sources"
            ).fetchone()[0],
        )
        self.assertNotEqual(first.run_id, second.run_id)

    def test_matches_existing_activity_and_keeps_intervals_subjective_fields(self):
        existing_id = "intervals-1"
        run_id = self.importer.writer.start_import_run("intervals")
        source_id = self.importer.writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id="i1",
            checksum="intervals-checksum",
            import_run_id=run_id,
        )
        self.importer.writer.upsert_activity(
            existing_id,
            {
                "local_date": "2026-10-01",
                "started_at_utc": START_UTC,
                "sport": "run",
                "name": "Morning run",
                "duration_s": 3550,
                "elapsed_s": 3650,
                "distance_m": 9950,
                "avg_hr": 138,
                "training_load": 50,
            },
            source="intervals",
            source_record_id=source_id,
        )
        self.importer.writer.link_activity_source(
            existing_id,
            source_id,
            match_method="external_id",
        )

        path = self._file("one.fit", b"one")
        summary = self._import([_summary(path)])

        self.assertEqual(1, summary.activities_matched)
        self.assertEqual(0, summary.activities_created)

        activities = self._activities()
        self.assertEqual(1, len(activities))
        activity = activities[0]
        self.assertEqual(existing_id, activity.id)
        # No source has automatic priority: the Intervals owner keeps every
        # field it wrote, and FIT's disagreeing values become review items.
        self.assertEqual("Morning run", activity.name)
        self.assertEqual(3550, activity.duration_s)
        self.assertEqual(3650, activity.elapsed_s)
        self.assertEqual(9950, activity.distance_m)
        self.assertEqual(138, activity.avg_hr)
        self.assertEqual(50, activity.training_load)

        conflicts = self.importer.writer.review_items(
            category="field_conflict",
            status="open",
        )
        self.assertEqual(
            {"duration_s", "elapsed_s"},
            {json.loads(item["context_json"])["field"] for item in conflicts},
        )
        for item in conflicts:
            self.assertEqual(existing_id, item["activity_id"])

        links = self.conn.execute(
            "SELECT source_record_id, match_method, is_primary "
            "FROM activity_sources ORDER BY source_record_id"
        ).fetchall()
        self.assertEqual(2, len(links))
        self.assertEqual(0, links[1]["is_primary"])
        self.assertEqual("temporal_overlap", links[1]["match_method"])

    def test_ambiguous_match_is_reported_and_not_merged(self):
        for activity_id in ("a1", "a2"):
            self.conn.execute(
                """
                INSERT INTO activities (
                    id, local_date, started_at_utc, sport,
                    elapsed_s, duration_s
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    "2026-10-01",
                    "2026-10-01T06:00:00Z",
                    "run",
                    3700,
                    3600,
                ),
            )

        path = self._file("one.fit", b"one")
        summary = self._import([_summary(path)], dry_run=True)

        self.assertEqual(1, summary.activities_skipped)
        self.assertEqual(0, summary.activities_imported)
        self.assertEqual(1, len(summary.actions))
        self.assertEqual("ambiguous", summary.actions[0].action)
        self.assertEqual(2, len(summary.actions[0].matches))
        self.assertEqual(
            2,
            self.conn.execute(
                "SELECT COUNT(*) FROM activities"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )

    def _review_items(self):
        return self.importer.writer.review_items(status="all")

    def _context(self, item) -> dict:
        import json

        return json.loads(item["context_json"] or "{}")

    def test_ambiguous_match_persists_review_item(self):
        for activity_id in ("a1", "a2"):
            self.conn.execute(
                """
                INSERT INTO activities (
                    id, local_date, started_at_utc, sport,
                    elapsed_s, duration_s
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    "2026-10-01",
                    "2026-10-01T06:00:00Z",
                    "run",
                    3700,
                    3600,
                ),
            )

        path = self._file("one.fit", b"one")
        first = self._import([_summary(path)])

        self.assertEqual(1, first.activities_skipped)
        self.assertEqual(1, first.review_recorded)

        items = self._review_items()
        self.assertEqual(1, len(items))
        self.assertEqual("ambiguous_match", items[0]["category"])
        self.assertEqual("open", items[0]["status"])
        self.assertIsNone(items[0]["activity_id"])

        candidates = self._context(items[0])["candidates"]
        self.assertEqual(
            {"a1", "a2"},
            {candidate["activity_id"] for candidate in candidates},
        )

        second = self._import([_summary(path)])

        self.assertEqual(0, second.review_recorded)
        self.assertEqual(1, len(self._review_items()))
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM activity_sources"
            ).fetchone()[0],
        )

    def test_resolved_ambiguous_match_is_not_reopened(self):
        for activity_id in ("a1", "a2"):
            self.conn.execute(
                """
                INSERT INTO activities (
                    id, local_date, started_at_utc, sport,
                    elapsed_s, duration_s
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    "2026-10-01",
                    "2026-10-01T06:00:00Z",
                    "run",
                    3700,
                    3600,
                ),
            )

        path = self._file("one.fit", b"one")
        self._import([_summary(path)])

        from hobbyjogging_core import TrainingWriter

        writer = TrainingWriter(self.conn)
        item_id = writer.review_items(status="open")[0]["id"]
        writer.resolve_review_match(item_id, "a1", note="a1 wins")
        self.conn.commit()

        summary = self._import([_summary(path)])

        self.assertEqual(1, summary.activities_imported)
        self.assertEqual(1, summary.activities_matched)
        self.assertEqual(0, summary.review_recorded)

        links = self.conn.execute(
            """
            SELECT match_method FROM activity_sources
            WHERE source_record_id = (
                SELECT id FROM source_records LIMIT 1
            )
            """,
        ).fetchall()
        self.assertEqual(1, len(links))
        self.assertEqual("review_resolved", links[0]["match_method"])

    def test_quality_issue_is_recorded_and_flags_activity(self):
        path = self._file("degenerate.fit", b"degenerate")

        summary = self._import([_summary(path, distance_m=0)])

        self.assertEqual(1, summary.review_recorded)
        items = self._review_items()
        self.assertEqual(1, len(items))
        self.assertEqual("quality", items[0]["category"])
        self.assertEqual("zero_distance", self._context(items[0])["rule"])

        activities = self._activities()
        self.assertEqual(1, len(activities))
        self.assertTrue(activities[0].needs_review)

    def test_date_filter_skips_session_before_writing(self):
        path = self._file("one.fit", b"one")

        summary = self._import(
            [_summary(path)],
            start=date(2026, 10, 2),
        )

        self.assertEqual(0, summary.activities_imported)
        self.assertEqual(1, summary.activities_skipped)
        self.assertEqual("skip", summary.actions[0].action)
        self.assertEqual("outside_date_range", summary.actions[0].match_method)
        self.assertEqual([], self._activities())
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )

    def test_limit_applies_to_activity_files(self):
        first = self._file("a.fit", b"a")
        second = self._file("b.fit", b"b")

        summary = self._import(
            [_summary(first), _summary(second, name="Second")],
            limit=1,
        )

        self.assertEqual(2, summary.files_seen)
        self.assertEqual(1, summary.activities_imported)
        self.assertEqual(1, len(self._activities()))

    def test_multiple_fit_files_merge_into_one_activity(self):
        first = self._file("first.fit", b"first")
        second = self._file("second.fit", b"second")

        summary = self._import(
            [
                _summary(first, lap_start="2026-10-01T06:00:00Z"),
                _summary(second, lap_start="2026-10-01T06:30:00Z"),
            ]
        )

        self.assertEqual(1, summary.activities_created)
        self.assertEqual(1, summary.activities_matched)
        self.assertEqual(2, summary.activities_imported)
        self.assertEqual(2, summary.laps_imported)
        self.assertEqual(1, len(self._activities()))
        self.assertEqual(
            2,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )
        self.assertEqual(
            2,
            self.conn.execute(
                "SELECT COUNT(*) FROM activity_sources"
            ).fetchone()[0],
        )

        laps = self.repository.activity_laps(self._activities()[0].id)
        self.assertEqual(2, len(laps))
        self.assertEqual(
            ["2026-10-01T06:00:00Z", "2026-10-01T06:30:00Z"],
            [lap.start_time_utc for lap in laps],
        )

    def test_excluded_activity_is_not_resurrected_by_reimport(self):
        path = self._file("one.fit", b"one")
        first = self._import([_summary(path)])
        self.assertEqual(1, first.activities_imported)

        activity_id = self._activities()[0].id
        self.importer.writer.exclude_activity(activity_id)
        self.conn.commit()
        self.assertEqual([], self._activities())

        second = self._import([_summary(path)])

        self.assertEqual(1, second.activities_seen)
        self.assertEqual(0, second.activities_imported)
        self.assertEqual(0, second.activities_matched)
        self.assertEqual(0, second.activities_created)
        self.assertEqual(1, second.activities_skipped)
        self.assertEqual("skip", second.actions[0].action)
        self.assertEqual("excluded", second.actions[0].match_method)

        self.assertEqual(
            [],
            self._activities(),
        )
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM source_records"
            ).fetchone()[0],
        )
        self.assertIsNotNone(
            self.conn.execute(
                "SELECT excluded_at FROM source_records"
            ).fetchone()["excluded_at"],
        )

    def test_excluded_linked_activity_is_skipped_after_review_resolution(self):
        existing_id = "intervals-1"
        run_id = self.importer.writer.start_import_run("intervals")
        source_id = self.importer.writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id="i1",
            checksum="intervals-checksum",
            import_run_id=run_id,
        )
        self.importer.writer.upsert_activity(
            existing_id,
            {
                "local_date": "2026-10-01",
                "started_at_utc": START_UTC,
                "sport": "run",
                "name": "Morning run",
                "duration_s": 3550,
                "elapsed_s": 3650,
                "distance_m": 9950,
            },
            source="intervals",
            source_record_id=source_id,
        )
        self.importer.writer.link_activity_source(
            existing_id,
            source_id,
            match_method="external_id",
        )
        path = self._file("one.fit", b"one")
        self._import([_summary(path)])

        self.importer.writer.exclude_activity(existing_id)
        self.conn.commit()

        summary = self._import([_summary(path)])

        self.assertEqual(0, summary.activities_imported)
        self.assertEqual(1, summary.activities_skipped)
        self.assertEqual("excluded", summary.actions[0].match_method)

    def test_parse_error_is_skipped(self):
        self._file("one.fit", b"one")

        with patch(
            "hobbyjogging_import.fit_import.read_fit_file_id",
            return_value={"type": "activity"},
        ), patch(
            "hobbyjogging_import.fit_import.parse_fit_file",
            side_effect=ValueError("bad fit"),
        ):
            summary = self.importer.import_paths([self.fit_dir])

        self.assertEqual(1, summary.files_skipped)
        self.assertEqual(1, len(summary.errors))
        self.assertEqual(0, summary.activities_imported)


class FitDiscoveryTests(unittest.TestCase):

    def test_discovers_fit_files_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested"
            nested.mkdir()
            (root / "a.fit").write_bytes(b"a")
            (nested / "b.FIT").write_bytes(b"b")
            (root / "notes.txt").write_text("not fit")

            self.assertEqual(
                ["a.fit"],
                [
                    path.name
                    for path in discover_fit_files([root])
                ],
            )
            self.assertEqual(
                ["a.fit", "b.FIT"],
                [
                    path.name
                    for path in discover_fit_files(
                        [root],
                        recursive=True,
                    )
                ],
            )

    def test_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            discover_fit_files(["/does/not/exist"])


if __name__ == "__main__":
    unittest.main()
