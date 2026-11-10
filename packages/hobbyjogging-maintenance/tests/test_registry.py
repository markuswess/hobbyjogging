import unittest

from hobbyjogging_maintenance.registry import (
    all_tasks,
    get_task,
    preserve_registry,
    task,
)


class RegistryTests(unittest.TestCase):

    def test_registers_a_task(self):
        with preserve_registry():

            @task(
                "example_v1",
                kind="backfill",
                description="  example   task ",
            )
            def example(context):
                pass

            registered = get_task("example_v1")

        self.assertEqual("example_v1", registered.id)
        self.assertEqual("backfill", registered.kind)
        self.assertEqual("example task", registered.description)
        self.assertTrue(registered.applied_once)
        self.assertIs(example, registered.run)

    def test_recompute_tasks_always_run(self):
        with preserve_registry():

            @task("example_recompute", kind="recompute")
            def example(context):
                pass

            self.assertFalse(get_task("example_recompute").applied_once)

    def test_duplicate_ids_are_rejected(self):
        with preserve_registry():

            @task("duplicate_v1")
            def first(context):
                pass

            with self.assertRaises(ValueError):
                task("duplicate_v1")(first)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            task("bad_kind", kind="migration")

    def test_empty_id_is_rejected(self):
        with self.assertRaises(ValueError):
            task("")

    def test_unknown_task_lists_known_tasks(self):
        with preserve_registry():

            @task("known_v1")
            def known(context):
                pass

            with self.assertRaises(KeyError) as raised:
                get_task("missing")

        self.assertIn("known_v1", str(raised.exception))

    def test_shipped_tasks_are_registered(self):
        ids = {item.id for item in all_tasks()}

        self.assertIn("event_zones_v1", ids)
        self.assertIn("workout_classification_v1", ids)


if __name__ == "__main__":
    unittest.main()
