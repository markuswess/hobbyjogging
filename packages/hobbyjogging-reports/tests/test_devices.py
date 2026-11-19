import unittest
from datetime import date, timedelta

from hobbyjogging_core.model import Device, Equipment

from hobbyjogging_report.analysis import (
    device_changes,
    device_label,
    device_usage,
)
from hobbyjogging_report.equipment_report import equipment_report
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


class DeviceLabelTests(unittest.TestCase):

    def test_a_fit_product_and_a_provider_name_read_the_same(self):
        fit = Device(
            id="fit:garmin:enduro:3386253273",
            manufacturer="garmin",
            product="enduro",
        )
        provider = Device(id="intervals:garmin-enduro", name="Garmin Enduro")

        self.assertEqual("Garmin Enduro", device_label(fit))
        self.assertEqual("Garmin Enduro", device_label(provider))

    def test_product_codes_use_their_marketing_names(self):
        for product, expected in (
            ("fr645", "Garmin Forerunner 645"),
            ("fr945", "Garmin Forerunner 945"),
            ("edge_540", "Garmin Edge 540"),
        ):
            self.assertEqual(
                expected,
                device_label(
                    Device(
                        id="fit:garmin:x:1",
                        manufacturer="garmin",
                        product=product,
                    )
                ),
            )

    def test_a_stored_name_wins_and_whitespace_is_cleaned(self):
        self.assertEqual(
            "Old watch",
            device_label(
                Device(
                    id="x",
                    manufacturer="garmin",
                    product="enduro",
                    name="  Old watch ",
                )
            ),
        )
        self.assertEqual(
            "Strava",
            device_label(Device(id="x", name=" Strava")),
        )

    def test_an_empty_device_falls_back_to_its_id(self):
        self.assertEqual("x", device_label(Device(id="x")))


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

    def test_session_report_names_a_product_only_device(self):
        watch = Device(
            id="fit:garmin:enduro:1",
            manufacturer="garmin",
            product="enduro",
        )
        source = FakeSource(
            [activity(id="a", date=D, device_id=watch.id)],
            devices=[watch],
        )

        report = session_report("a", source)

        self.assertIn("- Device: Garmin Enduro", report)

    def test_equipment_report_prints_one_device_column(self):
        watch = Device(
            id="fit:garmin:enduro:1",
            manufacturer="garmin",
            product="enduro",
        )
        shoe = Equipment(id="shoe", type="shoe", name="Demo Shoe")
        source = FakeSource(
            [
                activity(
                    id="a",
                    date=D,
                    distance_m=10000,
                    equipment=[shoe],
                    device_id=watch.id,
                )
            ],
            equipment=[shoe],
            devices=[watch],
        )

        report = equipment_report(source, today=D)

        self.assertIn(
            "| Device | Activities | First used | Last used | Status |",
            report,
        )
        self.assertIn("| Garmin Enduro | 1 |", report)
        self.assertNotIn("| Product |", report)


if __name__ == "__main__":
    unittest.main()
