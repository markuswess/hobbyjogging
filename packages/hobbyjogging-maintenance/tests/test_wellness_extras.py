import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "wellness_extras_v1"


class WellnessExtrasTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test", {})

    def _wellness(self, day, payload):
        self.writer.upsert_source_record(
            source="intervals",
            record_type="wellness",
            external_id=day,
            checksum=f"c-{day}",
            import_run_id=self.run_id,
            payload_json=json.dumps(payload),
        )
        self.conn.commit()

    def _sheet(self, activity_id, day, weight):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) VALUES (?, ?, 'run')",
            (activity_id, day),
        )
        record_id = self.writer.upsert_source_record(
            source="sheet",
            record_type="activity",
            external_id=f"sheet-{activity_id}",
            checksum=f"c-{activity_id}",
            import_run_id=self.run_id,
            payload_json=json.dumps({"values": {"Gewicht nachher": weight}}),
        )
        self.conn.execute(
            "INSERT INTO activity_sources "
            "(activity_id, source_record_id, match_method) VALUES (?, ?, 'test')",
            (activity_id, record_id),
        )
        self.conn.commit()

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _row(self, day):
        return self.conn.execute(
            "SELECT weight_kg, sleep_score, sleep_quality, spo2, steps, "
            "floors_climbed, ctl, atl FROM wellness_days WHERE local_date = ?",
            (day,),
        ).fetchone()

    def test_fills_the_extras(self):
        self._wellness("2026-05-01", {
            "sleepScore": 82.0,
            "sleepQuality": 3,
            "spO2": 95.0,
            "weight": 65.2,
            "steps": 12000,
            "floorsClimbed": 12,
            "ctl": 41.5,
            "atl": 33.2,
        })

        result = self._run()

        self.assertEqual(1, result.counts["written"])
        row = self._row("2026-05-01")
        self.assertAlmostEqual(65.2, row["weight_kg"])
        self.assertAlmostEqual(82.0, row["sleep_score"])
        self.assertAlmostEqual(3.0, row["sleep_quality"])
        self.assertAlmostEqual(95.0, row["spo2"])
        self.assertEqual(12000, row["steps"])
        self.assertEqual(12, row["floors_climbed"])
        self.assertAlmostEqual(41.5, row["ctl"])
        self.assertAlmostEqual(33.2, row["atl"])

    def test_existing_values_are_kept(self):
        self.conn.execute(
            "INSERT INTO wellness_days (local_date, hrv, resting_hr) "
            "VALUES ('2026-05-01', 60.0, 51.0)"
        )
        self.conn.commit()
        self._wellness("2026-05-01", {"sleepScore": 82.0})

        self._run()

        row = self.conn.execute(
            "SELECT hrv, resting_hr, sleep_score FROM wellness_days "
            "WHERE local_date = '2026-05-01'"
        ).fetchone()
        self.assertAlmostEqual(60.0, row["hrv"])
        self.assertAlmostEqual(51.0, row["resting_hr"])
        self.assertAlmostEqual(82.0, row["sleep_score"])

    def test_the_sheet_weight_fills_a_missing_weight(self):
        self._wellness("2019-01-23", {"sleepScore": 70.0})
        self._sheet("a1", "2019-01-23", 68.5)

        self._run()

        self.assertAlmostEqual(68.5, self._row("2019-01-23")["weight_kg"])

    def test_an_intervals_weight_beats_the_sheet(self):
        self._wellness("2019-01-23", {"weight": 67.0})
        self._sheet("a1", "2019-01-23", 68.5)

        self._run()

        self.assertAlmostEqual(67.0, self._row("2019-01-23")["weight_kg"])

    def test_a_forced_rerun_is_a_no_op(self):
        self._wellness("2026-05-01", {"sleepScore": 82.0})

        self._run()
        result = self._run(force=True)

        self.assertEqual(0, result.counts.get("written", 0))
        self.assertEqual(1, result.counts["unchanged"])


if __name__ == "__main__":
    unittest.main()
