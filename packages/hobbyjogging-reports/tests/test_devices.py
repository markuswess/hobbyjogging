import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import Device

from hobbyjogging_report.analysis import device_changes, device_usage
from hobbyjogging_report.sessions import session_report
from support import FakeSource, activity_factory

D = date(2026, 10, 1)
activity = activity_factory()


def device(id, name, product, acquired=None, retired=None):
    return Device(
        id=id,
        manufacturer="Garmin",
        name=name,
        product=product,
        acquired_on=acquired,
        retired_on=retired,
    )


class DeviceUsageTests(unittest.TestCase):

    def test_counts_periods_and_changes(self):
        watch = device(
            "watch",
            "Forerunner 645",
            "Forerunner 645",
            acquired=date(2024, 1, 1),
            retired=date(2025, 1, 1),
        )
        newer = device(
            "newer",
            "Enduro",
            "Enduro",
            acquired=date(2025, 1, 1),
        )
        activities = [
            activity(id="a", date=D, equipment=[], device_id="watch"),
            activity(id="b", date=D + timedelta(days=1), device_id="watch"),
            activity(
                id="c",
                date=D + timedelta(days=30),
                type="ride",
                device_id="newer",
            ),
        ]

        stats = device_usage([newer, watch], activities)
        by_id = {stat.device.id: stat for stat in stats}

        self.assertEqual(["watch", "newer"], [stat.device.id for stat in stats])
        self.assertEqual(2, by_id["watch"].activities)
        self.assertEqual(2, by_id["watch"].runs)
        self.assertEqual(D, by_id["watch"].first_used)
        self.assertEqual(D + timedelta(days=1), by_id["watch"].last_used)
        self.assertTrue(by_id["watch"].retired)
        self.assertEqual(1, by_id["newer"].activities)
        self.assertEqual(0, by_id["newer"].runs)
        self.assertEqual(
            [
                (D, "Forerunner 645"),
                (D + timedelta(days=30), "Enduro"),
            ],
            device_changes(stats),
        )

    def test_session_report_names_the_device(self):
        watch = device(
            "watch",
            "Forerunner 645",
            "Forerunner 645",
        )
        source = FakeSource(
            [activity(id="a", date=D, device_id="watch")],
            devices=[watch],
        )

        report = session_report("a", source)

        self.assertIn("- Device: Forerunner 645", report)


if __name__ == "__main__":
    unittest.main()
