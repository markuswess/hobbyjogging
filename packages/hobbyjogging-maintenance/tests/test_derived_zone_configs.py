import unittest
from datetime import date

from hobbyjogging_core import Lap, TrainingWriter, connect, migrate

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "derived_zone_configs_current"


class DerivedZoneConfigTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _activity(self, day="2026-10-01", sport="run", laps=True):
        self.counter += 1
        activity_id = f"a{self.counter}"
        record_id = self.writer.upsert_source_record(
            source="fit",
            record_type="activity",
            external_id=activity_id,
            checksum=f"c-{activity_id}",
            import_run_id=self.run_id,
        )
        self.writer.upsert_activity(
            activity_id,
            {
                "local_date": day,
                "sport": sport,
                "duration_s": 800,
            },
            source="fit",
            source_record_id=record_id,
        )
        if laps:
            self.writer.replace_activity_laps(
                activity_id,
                [
                    Lap(
                        index=1,
                        start_time_utc=f"{day}T06:00:00Z",
                        duration_s=600,
                        distance_m=1000,
                        avg_hr=120,
                    ),
                    Lap(
                        index=2,
                        start_time_utc=f"{day}T06:10:00Z",
                        duration_s=200,
                        distance_m=1000,
                        avg_hr=165,
                    ),
                ],
            )
        self.conn.commit()
        return activity_id

    def _configs(self, activity_id):
        row = self.conn.execute(
            """
            SELECT hr_zone_config_id, pace_zone_config_id
            FROM activities WHERE id = ?
            """,
            (activity_id,),
        ).fetchone()
        return row["hr_zone_config_id"], row["pace_zone_config_id"]

    def _zone_times(self, activity_id, kind):
        return [
            (row["zone_index"], row["seconds"])
            for row in self.conn.execute(
                """
                SELECT zone_index, seconds FROM activity_zone_times
                WHERE activity_id = ? AND kind = ?
                ORDER BY zone_index
                """,
                (activity_id, kind),
            )
        ]

    def _threshold(self):
        self.writer.set_manual_threshold(
            "2026-01-01",
            "run",
            lthr=170,
            threshold_pace_mps=3.7,
        )
        self.conn.commit()

    def test_builds_configs_and_zone_times_from_a_manual_snapshot(self):
        self._threshold()
        activity_id = self._activity()

        run = self._run()

        self.assertEqual(2, run.counts["configs"])
        hr_id, pace_id = self._configs(activity_id)
        self.assertIsNotNone(hr_id)
        self.assertIsNotNone(pace_id)
        sources = {
            row["source"]
            for row in self.conn.execute(
                "SELECT source FROM zone_configs WHERE id IN (?, ?)",
                (hr_id, pace_id),
            )
        }
        self.assertEqual({"thresholds"}, sources)
        self.assertEqual([(1, 600), (3, 200)], self._zone_times(activity_id, "hr"))
        self.assertEqual([(1, 600), (4, 200)], self._zone_times(activity_id, "pace"))

    def test_a_second_run_is_a_no_op(self):
        self._threshold()
        activity_id = self._activity()
        self._run()

        second = self._run()

        self.assertEqual(1, second.counts["already"])
        self.assertEqual(
            [(1, 600), (3, 200)],
            self._zone_times(activity_id, "hr"),
        )

    def test_a_date_before_the_threshold_stays_unzoned(self):
        self.writer.set_manual_threshold(
            "2027-01-01",
            "run",
            lthr=170,
        )
        self.conn.commit()
        activity_id = self._activity()

        run = self._run()

        self.assertEqual(1, run.counts["no_threshold"])
        self.assertEqual((None, None), self._configs(activity_id))
        self.assertEqual([], self._zone_times(activity_id, "hr"))

    def test_an_existing_intervals_config_wins(self):
        self._threshold()
        activity_id = self._activity()
        config_id = self.writer.upsert_zone_config(
            kind="hr",
            boundaries=[135, 156, 174, 192],
            source="intervals",
        )
        self.writer.set_activity_zone_configs(
            activity_id,
            hr_zone_config_id=config_id,
        )
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["configs"])
        hr_id, pace_id = self._configs(activity_id)
        self.assertEqual(config_id, hr_id)
        self.assertIsNotNone(pace_id)

    def test_no_laps_still_sets_the_configs_without_zone_times(self):
        self._threshold()
        activity_id = self._activity(laps=False)

        run = self._run()

        self.assertEqual(2, run.counts["configs"])
        self.assertEqual(1, run.counts["no_laps"])
        self.assertIsNotNone(self._configs(activity_id)[0])
        self.assertEqual([], self._zone_times(activity_id, "hr"))

    def test_a_sport_without_a_threshold_stays_unzoned(self):
        self._threshold()
        activity_id = self._activity(sport="ride")

        run = self._run()

        self.assertEqual(1, run.counts["no_threshold"])
        self.assertEqual((None, None), self._configs(activity_id))


if __name__ == "__main__":
    unittest.main()
