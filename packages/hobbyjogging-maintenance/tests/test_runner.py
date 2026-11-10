import unittest

from hobbyjogging_core import connect, migrate

from hobbyjogging_maintenance.context import Scope
from hobbyjogging_maintenance.registry import get_task, preserve_registry, task
from hobbyjogging_maintenance.runner import run_task
from hobbyjogging_maintenance.store import applied_ids, is_applied


def _insert_activity(context):
    context.connection.execute(
        "INSERT OR IGNORE INTO activities (id, local_date, sport) "
        "VALUES ('a1', '2026-10-01', 'run')"
    )
    context.count("written")


def _fail(context):
    context.connection.execute(
        "INSERT INTO activities (id, local_date, sport) "
        "VALUES ('a1', '2026-10-01', 'run')"
    )
    raise RuntimeError("boom")


class RunnerTests(unittest.TestCase):

    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)
        migrate(self.conn)

    def _activities(self):
        return [
            row["id"]
            for row in self.conn.execute("SELECT id FROM activities")
        ]

    def _runs(self):
        return self.conn.execute(
            "SELECT * FROM maintenance_runs ORDER BY id"
        ).fetchall()

    def test_dry_run_rolls_back_and_is_logged(self):
        with preserve_registry():
            task("write_v1")(_insert_activity)
            run = run_task(
                self.conn,
                get_task("write_v1"),
                dry_run=True,
            )

        self.assertEqual("ok", run.status)
        self.assertEqual({"written": 1}, run.counts)
        self.assertEqual([], self._activities())
        self.assertFalse(is_applied(self.conn, "write_v1"))

        runs = self._runs()
        self.assertEqual(1, len(runs))
        self.assertEqual(1, runs[0]["dry_run"])
        self.assertEqual("ok", runs[0]["status"])

    def test_backfill_is_recorded_and_then_skipped(self):
        with preserve_registry():
            task("write_v1")(_insert_activity)
            first = run_task(self.conn, get_task("write_v1"))
            second = run_task(self.conn, get_task("write_v1"))

        self.assertEqual("ok", first.status)
        self.assertEqual(["a1"], self._activities())
        self.assertTrue(is_applied(self.conn, "write_v1"))
        self.assertEqual("skipped", second.status)
        # A skip is not a run, so only the first one is logged.
        self.assertEqual(1, len(self._runs()))

    def test_force_reruns_an_applied_backfill(self):
        with preserve_registry():
            task("write_v1")(_insert_activity)
            run_task(self.conn, get_task("write_v1"))
            forced = run_task(self.conn, get_task("write_v1"), force=True)

        self.assertEqual("ok", forced.status)
        self.assertEqual(["a1"], self._activities())

    def test_failure_rolls_back_and_records_the_error(self):
        with preserve_registry():
            task("fail_v1")(_fail)
            run = run_task(self.conn, get_task("fail_v1"))

        self.assertEqual("failed", run.status)
        self.assertIn("boom", run.error)
        self.assertEqual([], self._activities())
        self.assertFalse(is_applied(self.conn, "fail_v1"))

        runs = self._runs()
        self.assertEqual("failed", runs[0]["status"])
        self.assertIn("boom", runs[0]["details_json"])

    def test_recompute_runs_every_time_and_is_not_applied(self):
        with preserve_registry():

            @task("recompute_v1", kind="recompute")
            def recompute(context):
                context.count("passes")

            first = run_task(self.conn, get_task("recompute_v1"))
            second = run_task(self.conn, get_task("recompute_v1"))

        self.assertEqual("ok", first.status)
        self.assertEqual("ok", second.status)
        self.assertEqual({}, applied_ids(self.conn))
        self.assertEqual(2, len(self._runs()))

    def test_applied_details_are_stored(self):
        with preserve_registry():

            @task("details_v1")
            def details(context):
                context.count("seen")
                context.details["note"] = "kept"

            run_task(self.conn, get_task("details_v1"))

        row = applied_ids(self.conn)["details_v1"]
        self.assertIn("kept", row["details_json"])

    def test_scope_is_passed_to_the_task(self):
        seen = {}

        with preserve_registry():

            @task("scope_v1")
            def scoped(context):
                seen["scope"] = context.scope

            run_task(
                self.conn,
                get_task("scope_v1"),
                scope=Scope(limit=5),
            )

        self.assertEqual(5, seen["scope"].limit)


if __name__ == "__main__":
    unittest.main()
