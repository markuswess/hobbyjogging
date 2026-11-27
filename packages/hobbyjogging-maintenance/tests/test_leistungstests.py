import tempfile
import unittest
from datetime import date
from pathlib import Path

from hobbyjogging_core import TrainingWriter, connect, migrate
from hobbyjogging_import.performance_tests import (
    PerformanceSplit,
    PerformanceTest,
)

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "leistungstests_v1"


class LeistungstestsBackfillTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("sheet", {})
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.report = Path(self.directory.name) / "report.txt"
        self._row = 0

    def _activity(
        self,
        activity_id="a1",
        day=date(2016, 4, 10),
        distance=10000.0,
        *,
        start="2016-04-10T07:00:00Z",
        offset=120,
        methods=(),
    ):
        self.conn.execute(
            """
            INSERT INTO activities (
                id, local_date, sport, distance_m, duration_s,
                started_at_utc, tz_offset_min
            ) VALUES (?, ?, 'run', ?, 3600, ?, ?)
            """,
            (activity_id, day.isoformat(), distance, start, offset),
        )
        for method in methods:
            self.conn.execute(
                "INSERT INTO activity_workout_methods "
                "(activity_id, method, source) VALUES (?, ?, 'sheet')",
                (activity_id, method),
            )
        self.conn.commit()
        return activity_id

    def _block(
        self,
        day,
        *,
        distance=10000.0,
        time_s=3600.0,
        title="Race",
        result="",
        splits=2,
        place=None,
        ageclass=None,
        start_time="10:00:00",
        date_source="cell",
    ):
        self._row += 1
        parts = [
            PerformanceSplit(
                index=index + 1,
                distance_m=distance / splits,
                duration_s=time_s / splits,
                cumulative_m=distance / splits * (index + 1),
                avg_hr=150.0,
            )
            for index in range(splits)
        ]
        return PerformanceTest(
            row=self._row,
            date=day,
            date_source=date_source,
            start_time=start_time,
            distance_m=distance,
            title=title,
            splits=parts,
            official_distance_m=distance,
            official_time_s=time_s,
            result_text=result,
            place_total=place,
            place_ageclass=ageclass,
        )

    def _record(self, block):
        record_id = self.writer.upsert_source_record(
            source="sheet",
            record_type="performance_test",
            external_id=block.external_id,
            checksum=f"c-{block.external_id}",
            import_run_id=self.run_id,
            payload_json=block.payload(),
        )
        self.conn.commit()
        return record_id

    def _run(self, **kwargs):
        kwargs.setdefault("output", self.report)
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _result(self, activity_id="a1"):
        row = self.conn.execute(
            "SELECT * FROM race_results WHERE activity_id = ?",
            (activity_id,),
        ).fetchone()
        return None if row is None else dict(row)

    def _laps(self, activity_id="a1"):
        return self.conn.execute(
            "SELECT * FROM activity_laps WHERE activity_id = ? "
            "ORDER BY source, lap_index",
            (activity_id,),
        ).fetchall()

    def test_race_block_writes_a_result_and_split_laps(self):
        self._activity(distance=42195.0)
        block = self._block(
            date(2016, 4, 10),
            distance=42195.0,
            time_s=10541.0,
            title="Vienna City Marathon",
            result="Gesamt 173., M-30: 34.",
            splits=3,
            place=173,
            ageclass=34,
        )
        record_id = self._record(block)

        result = self._run()

        self.assertEqual(1, result.counts["matched"])
        self.assertEqual(1, result.counts["race_results"])
        self.assertEqual(3, result.counts["split_rows"])
        row = self._result()
        self.assertEqual("sheet", row["source"])
        self.assertEqual("Vienna City Marathon", row["name"])
        self.assertEqual(42195.0, row["official_distance_m"])
        self.assertEqual(10541.0, row["official_time_s"])
        self.assertEqual(0, row["officially_measured"])
        self.assertEqual(173, row["place_total"])
        self.assertEqual(34, row["place_ageclass"])
        self.assertEqual("completed", row["status"])
        laps = self._laps()
        self.assertEqual(3, len(laps))
        self.assertEqual({"sheet_test"}, {lap["source"] for lap in laps})
        self.assertEqual({record_id}, {lap["source_record_id"] for lap in laps})
        self.assertEqual([1, 2, 3], [lap["lap_index"] for lap in laps])

    def test_a_runalyze_result_is_kept_while_splits_still_land(self):
        self._activity(distance=42195.0)
        self.writer.upsert_race_result(
            "a1",
            source="runalyze",
            official_time_s=10500.0,
        )
        self._record(self._block(
            date(2016, 4, 10),
            distance=42195.0,
            time_s=10541.0,
            title="Vienna City Marathon",
        ))
        self.conn.commit()

        result = self._run()

        self.assertEqual(1, result.counts["results_kept"])
        self.assertEqual(0, result.counts["race_results"])
        row = self._result()
        self.assertEqual("runalyze", row["source"])
        self.assertEqual(10500.0, row["official_time_s"])
        self.assertEqual(2, len(self._laps()))

    def test_a_test_block_tags_time_trial_without_a_result(self):
        self._activity(day=date(2016, 3, 18), distance=7500.0)
        self.writer.replace_activity_tags("a1", ["w"], source="sheet")
        self._record(self._block(
            date(2016, 3, 18),
            distance=7500.0,
            title="Geschw/Puls Test",
        ))
        self.conn.commit()

        result = self._run()

        self.assertEqual(1, result.counts["tags"])
        self.assertIsNone(self._result())
        tags = {
            row["tag"]: row["source"]
            for row in self.conn.execute(
                "SELECT tag, source FROM activity_tags WHERE activity_id = 'a1'"
            )
        }
        self.assertEqual(
            {"w": "sheet", "time trial": "sheet_test"},
            tags,
        )
        self.assertEqual(2, len(self._laps()))

    def test_a_relay_is_a_normal_race_result(self):
        self._activity(day=date(2019, 4, 7), distance=15900.0)
        self._record(self._block(
            date(2019, 4, 7),
            distance=15900.0,
            time_s=3535.0,
            title="Vienna City Marathon Staffel",
            result="Gesamtstaffel 8., Klasse 7.",
            place=8,
            ageclass=7,
            splits=14,
        ))

        result = self._run()

        self.assertEqual(1, result.counts["race_results"])
        row = self._result()
        self.assertEqual("completed", row["status"])
        self.assertEqual(8, row["place_total"])
        self.assertEqual(14, len(self._laps()))

    def test_an_unmatched_block_writes_nothing_and_is_reported(self):
        self._activity(distance=50000.0)
        self._record(self._block(date(2016, 4, 10), distance=10000.0))

        result = self._run()

        self.assertEqual(1, result.counts["unmatched"])
        self.assertIsNone(self._result())
        self.assertEqual([], self._laps())
        self.assertIn("unmatched", self.report.read_text(encoding="utf-8"))

    def test_an_ambiguous_match_is_reported(self):
        self._activity("a1", distance=10000.0)
        self._activity("a2", distance=10000.0)
        self._record(self._block(date(2016, 4, 10), distance=10000.0))

        result = self._run()

        self.assertEqual(1, result.counts["ambiguous"])
        self.assertIsNone(self._result("a1"))
        self.assertIsNone(self._result("a2"))
        self.assertIn("ambiguous", self.report.read_text(encoding="utf-8"))

    def test_a_broken_block_is_reported_without_writing(self):
        self._activity(distance=10000.0)
        block = self._block(date(2021, 9, 11), distance=10000.0, splits=1)
        block.splits = []
        block.official_time_s = None
        block.problems = ["no splits", "no time"]
        self._record(block)

        result = self._run()

        self.assertEqual(1, result.counts["broken"])
        self.assertIsNone(self._result())
        self.assertIn("broken", self.report.read_text(encoding="utf-8"))

    def test_a_dry_run_writes_nothing(self):
        self._activity(distance=10000.0)
        self._record(self._block(date(2016, 4, 10), distance=10000.0))

        result = self._run(dry_run=True)

        self.assertEqual(1, result.counts["matched"])
        self.assertIsNone(self._result())
        self.assertEqual([], self._laps())

    def test_a_forced_rerun_is_idempotent(self):
        self._activity(distance=10000.0)
        self._record(self._block(date(2016, 4, 10), distance=10000.0))

        self._run()
        self._run(force=True)

        self.assertEqual(1, len(self.conn.execute(
            "SELECT * FROM race_results WHERE activity_id = 'a1'"
        ).fetchall()))
        self.assertEqual(2, len(self._laps()))

    def test_date_assumptions_are_reported(self):
        self._activity(day=date(2018, 9, 29), distance=10000.0)
        self._record(self._block(
            date(2018, 9, 29),
            distance=10000.0,
            date_source="inferred-year",
        ))

        result = self._run()

        self.assertTrue(any("year inferred" in note for note in result.notes))


if __name__ == "__main__":
    unittest.main()
