import unittest

from hobbyjogging_core import (
    Interval,
    Lap,
    TrainingWriter,
    connect,
    migrate,
)

from hobbyjogging_maintenance.registry import get_task
from hobbyjogging_maintenance.runner import run_task

TASK = "derived_intervals_current"


class DerivedIntervalsTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)
        self.writer = TrainingWriter(self.conn)
        self.run_id = self.writer.start_import_run("test")
        self.counter = 0

    def _run(self, **kwargs):
        return run_task(self.conn, get_task(TASK), **kwargs)

    def _activity(self, *, intervals_methods=(), targets=(), sport="run"):
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
                "local_date": "2026-10-01",
                "sport": sport,
                "name": "",
                "duration_s": 3600,
            },
            source="fit",
            source_record_id=record_id,
        )
        if intervals_methods or targets:
            self.writer.replace_activity_workout_methods(
                activity_id,
                list(intervals_methods),
                source="runalyze",
            )
            self.writer.replace_activity_workout_targets(
                activity_id,
                list(targets),
                source="runalyze",
            )
        self.conn.commit()
        return activity_id

    def _laps(self, activity_id, laps):
        self.writer.replace_activity_laps(
            activity_id,
            [
                Lap(
                    index=index,
                    start_time_utc=f"2026-10-01T06:{index:02d}:00Z",
                    duration_s=duration,
                    distance_m=distance,
                    avg_hr=hr,
                    max_hr=hr + 5 if hr else None,
                )
                for index, (duration, distance, hr) in enumerate(laps, start=1)
            ],
        )
        self.conn.commit()

    def _intervals(self, activity_id):
        return [
            (row["type"], row["source"], row["distance_m"])
            for row in self.conn.execute(
                """
                SELECT type, source, distance_m FROM activity_intervals
                WHERE activity_id = ?
                ORDER BY interval_index
                """,
                (activity_id,),
            )
        ]

    def _structured_laps(self):
        return [
            (600, 1000, 130),   # warm-up, 10:00/km
            (300, 1000, 165),   # work, 5:00/km
            (120, 250, 140),    # recovery, 8:00/km
            (300, 1000, 168),   # work
            (600, 1000, 130),   # cool-down
        ]

    def test_derives_work_and_recovery_from_the_type(self):
        activity_id = self._activity(
            intervals_methods={"intervals"},
            targets={"subthreshold"},
        )
        self._laps(activity_id, self._structured_laps())

        run = self._run()

        self.assertEqual(1, run.counts["derived"])
        intervals = self._intervals(activity_id)
        self.assertEqual(
            ["RECOVERY", "WORK", "RECOVERY", "WORK", "RECOVERY"],
            [kind for kind, _, _ in intervals],
        )
        self.assertTrue(all(source == "derived" for _, source, _ in intervals))

    def test_lap_variance_derives_without_the_type(self):
        activity_id = self._activity()
        self._laps(activity_id, self._structured_laps())

        run = self._run()

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual(
            2,
            sum(1 for kind, _, _ in self._intervals(activity_id) if kind == "WORK"),
        )

    def test_a_uniform_easy_run_stays_laps(self):
        activity_id = self._activity()
        self._laps(
            activity_id,
            [(360, 1000, 140)] * 6,
        )

        run = self._run()

        self.assertEqual(1, run.counts["uniform"])
        self.assertEqual([], self._intervals(activity_id))

    def test_a_structured_type_does_not_fabricate_reps_from_uniform_laps(self):
        activity_id = self._activity(
            intervals_methods={"intervals"},
            targets={"subthreshold"},
        )
        self._laps(activity_id, [(360, 1000, 150)] * 4)

        run = self._run()

        self.assertEqual(1, run.counts["uniform"])
        self.assertEqual([], self._intervals(activity_id))

    def test_a_measured_set_is_never_touched(self):
        activity_id = self._activity(
            intervals_methods={"intervals"},
            targets={"subthreshold"},
        )
        self._laps(activity_id, self._structured_laps())
        self.writer.replace_activity_intervals(
            activity_id,
            [Interval(type="WORK", duration_s=300, distance_m=1000)],
            source="intervals",
        )
        self.conn.commit()

        run = self._run()

        self.assertEqual(1, run.counts["has_measured"])
        self.assertEqual(
            [("WORK", "intervals", 1000.0)],
            self._intervals(activity_id),
        )

    def test_a_second_run_is_a_no_op(self):
        activity_id = self._activity(
            intervals_methods={"intervals"},
            targets={"subthreshold"},
        )
        self._laps(activity_id, self._structured_laps())

        self._run()
        second = self._run()

        self.assertEqual(1, second.counts["unchanged"])
        self.assertEqual(0, second.counts["derived"])

    def test_a_dry_run_writes_nothing(self):
        activity_id = self._activity(
            intervals_methods={"intervals"},
            targets={"subthreshold"},
        )
        self._laps(activity_id, self._structured_laps())

        run = self._run(dry_run=True)

        self.assertEqual(1, run.counts["derived"])
        self.assertEqual([], self._intervals(activity_id))

    def test_no_laps_is_counted(self):
        self._activity(
            intervals_methods={"intervals"},
            targets={"subthreshold"},
        )

        run = self._run()

        self.assertEqual(1, run.counts["no_laps"])
        self.assertEqual(0, run.counts["derived"])


if __name__ == "__main__":
    unittest.main()
