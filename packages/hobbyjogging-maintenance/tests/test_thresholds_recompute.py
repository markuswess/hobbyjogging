import json
import unittest

from hobbyjogging_core import TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

THRESHOLDS = "athlete_thresholds_current"
ZONES = "activity_zone_configs_current"


class ThresholdRecomputeTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test", {})

    def _activity(self, activity_id, day, payload):
        self.conn.execute(
            "INSERT INTO activities (id, local_date, sport) VALUES (?, ?, 'run')",
            (activity_id, day),
        )
        record_id = self.writer.upsert_source_record(
            source="intervals",
            record_type="activity",
            external_id=f"i-{activity_id}",
            checksum=f"c-{activity_id}",
            import_run_id=self.run_id,
            payload_json=json.dumps(payload),
        )
        self.conn.execute(
            "INSERT INTO activity_sources "
            "(activity_id, source_record_id, match_method) VALUES (?, ?, 'test')",
            (activity_id, record_id),
        )
        self.conn.commit()

    def _run(self, task, **kwargs):
        return run_task(self.conn, get_task(task), **kwargs)

    def _snapshots(self):
        return [
            tuple(row)
            for row in self.conn.execute(
                "SELECT effective_from, max_hr, lthr, threshold_pace_mps "
                "FROM athlete_thresholds ORDER BY effective_from"
            )
        ]

    def test_a_change_starts_a_new_snapshot(self):
        self._activity("a1", "2024-01-01", {
            "athlete_max_hr": 190, "lthr": 174, "threshold_pace": 4.5,
        })
        self._activity("a2", "2024-06-01", {
            "athlete_max_hr": 192, "lthr": 174, "threshold_pace": 4.7,
        })
        self._activity("a3", "2024-07-01", {
            "athlete_max_hr": 192, "lthr": 174, "threshold_pace": 4.7,
        })

        self._run(THRESHOLDS)

        self.assertEqual(
            [
                ("2024-01-01", 190.0, 174.0, 4.5),
                ("2024-06-01", 192.0, 174.0, 4.7),
            ],
            self._snapshots(),
        )

    def test_a_missing_pace_carries_forward(self):
        self._activity("a1", "2024-01-01", {
            "athlete_max_hr": 190, "lthr": 174, "threshold_pace": 4.5,
        })
        self._activity("a2", "2024-02-01", {
            "athlete_max_hr": 190, "lthr": 174, "threshold_pace": 0,
        })

        self._run(THRESHOLDS)

        self.assertEqual([("2024-01-01", 190.0, 174.0, 4.5)], self._snapshots())

    def test_an_implausible_pace_is_ignored(self):
        self._activity("a1", "2024-01-01", {
            "athlete_max_hr": 190, "lthr": 174, "threshold_pace": 0.83,
        })

        self._run(THRESHOLDS)

        self.assertEqual([("2024-01-01", 190.0, 174.0, None)], self._snapshots())

    def test_a_rerun_is_a_no_op(self):
        self._activity("a1", "2024-01-01", {
            "athlete_max_hr": 190, "lthr": 174, "threshold_pace": 4.5,
        })

        self._run(THRESHOLDS)
        result = self._run(THRESHOLDS, force=True)

        self.assertEqual(0, result.counts.get("snapshots", 0))
        self.assertEqual(1, len(self._snapshots()))

    def test_zone_configs_are_shared_per_era(self):
        boundaries = {
            "icu_hr_zones": [135, 156, 174, 192],
            "pace_zones": [73.0, 83.0, 100.0, 999.0],
        }
        self._activity("a1", "2024-01-01", boundaries)
        self._activity("a2", "2024-02-01", boundaries)

        self._run(ZONES)

        configs = self.conn.execute(
            "SELECT kind, COUNT(*) FROM zone_configs GROUP BY kind"
        ).fetchall()
        self.assertEqual(
            [("hr", 1), ("pace", 1)],
            [tuple(row) for row in configs],
        )
        linked = self.conn.execute(
            "SELECT COUNT(*) FROM activities "
            "WHERE hr_zone_config_id IS NOT NULL "
            "AND pace_zone_config_id IS NOT NULL"
        ).fetchone()[0]
        self.assertEqual(2, linked)

    def test_a_changed_boundary_set_is_a_new_config(self):
        self._activity("a1", "2024-01-01", {"icu_hr_zones": [135, 156, 174, 192]})
        self._activity("a2", "2024-06-01", {"icu_hr_zones": [136, 158, 176, 194]})

        self._run(ZONES)

        self.assertEqual(
            2,
            self.conn.execute("SELECT COUNT(*) FROM zone_configs").fetchone()[0],
        )

    def test_a_zone_rerun_is_a_no_op(self):
        self._activity("a1", "2024-01-01", {"icu_hr_zones": [135, 156, 174, 192]})

        self._run(ZONES)
        result = self._run(ZONES, force=True)

        self.assertEqual(0, result.counts.get("updated", 0))
        self.assertEqual(1, result.counts["unchanged"])


if __name__ == "__main__":
    unittest.main()
