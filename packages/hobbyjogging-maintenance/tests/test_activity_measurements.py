import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

ELEVATION = "activity_elevation_v1"
MAX_HR = "activity_max_hr_v1"


class ActivityMeasurementsTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test", {})

    def _activity(self, activity_id="a1", *, excluded=False):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) VALUES (?, ?, ?)",
            (activity_id, "2026-05-01", "run"),
        )
        if excluded:
            self.writer.exclude_activity(activity_id)
        self.conn.commit()
        return activity_id

    def _source(self, activity_id, source, payload, external="x1"):
        record_id = self.writer.upsert_source_record(
            source=source,
            record_type="activity",
            external_id=f"{source}-{external}",
            checksum=f"c-{source}-{external}",
            import_run_id=self.run_id,
            payload_json=json.dumps(payload),
        )
        self.conn.execute(
            "INSERT INTO activity_sources "
            "(activity_id, source_record_id, match_method) VALUES (?, ?, 'test')",
            (activity_id, record_id),
        )
        self.conn.commit()
        return record_id

    def _run(self, task, **kwargs):
        return run_task(self.conn, get_task(task), **kwargs)

    def _row(self, activity_id="a1"):
        return self.conn.execute(
            "SELECT elevation_gain_m, elevation_loss_m, max_hr FROM activities "
            "WHERE id = ?",
            (activity_id,),
        ).fetchone()

    def test_fills_elevation_from_intervals(self):
        self._activity()
        self._source(
            "a1",
            "intervals",
            {"total_elevation_gain": 120.0, "total_elevation_loss": 118.0},
        )

        result = self._run(ELEVATION)

        self.assertEqual(1, result.counts["written"])
        row = self._row()
        self.assertEqual(120.0, row["elevation_gain_m"])
        self.assertEqual(118.0, row["elevation_loss_m"])

    def test_fills_max_hr_from_intervals(self):
        self._activity()
        self._source("a1", "intervals", {"max_heartrate": 181.0})

        self._run(MAX_HR)

        self.assertEqual(181.0, self._row()["max_hr"])

    def test_sheet_supplies_gain_and_max_hr_but_no_loss(self):
        self._activity()
        self._source(
            "a1",
            "sheet",
            {"values": {"m bergauf": 85.0, "max. Hf": 176.0}},
        )

        self._run(ELEVATION)
        self._run(MAX_HR)

        row = self._row()
        self.assertEqual(85.0, row["elevation_gain_m"])
        self.assertIsNone(row["elevation_loss_m"])
        self.assertEqual(176.0, row["max_hr"])

    def test_fit_session_values_are_used(self):
        self._activity()
        self._source(
            "a1",
            "fit",
            {"session": {"ascent_m": 60.0, "descent_m": 55.0, "max_hr": 170.0}},
        )

        self._run(ELEVATION)
        self._run(MAX_HR)

        row = self._row()
        self.assertEqual(60.0, row["elevation_gain_m"])
        self.assertEqual(55.0, row["elevation_loss_m"])
        self.assertEqual(170.0, row["max_hr"])

    def test_a_manual_value_wins(self):
        self._activity()
        self.writer.set_manual_field("a1", "max_hr", 188.0)
        self._source("a1", "intervals", {"max_heartrate": 181.0})

        result = self._run(MAX_HR)

        self.assertEqual(0, result.counts["written"])
        self.assertEqual(188.0, self._row()["max_hr"])

    def test_excluded_activities_are_skipped(self):
        self._activity(excluded=True)
        self._source("a1", "intervals", {"total_elevation_gain": 10.0})

        self._run(ELEVATION)

        self.assertIsNone(self._row()["elevation_gain_m"])

    def test_a_forced_rerun_is_a_no_op(self):
        self._activity()
        self._source("a1", "intervals", {"total_elevation_gain": 120.0})

        self._run(ELEVATION)
        result = self._run(ELEVATION, force=True)

        self.assertEqual(0, result.counts.get("written", 0))
        self.assertEqual(1, result.counts["unchanged"])

    def test_dry_run_writes_nothing(self):
        self._activity()
        self._source("a1", "intervals", {"total_elevation_gain": 120.0})

        self._run(ELEVATION, dry_run=True)

        self.assertIsNone(self._row()["elevation_gain_m"])


if __name__ == "__main__":
    unittest.main()
