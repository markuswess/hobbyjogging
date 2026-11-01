import unittest
from datetime import date

from hobbyjogging_core import Activity, ActivityEquipment, Equipment


class EquipmentModelTests(unittest.TestCase):

    def test_equipment_defaults(self):
        shoe = Equipment(id="shoe-1", type="shoe", name="Pegasus 40")

        self.assertEqual("", shoe.brand)
        self.assertEqual("", shoe.model)
        self.assertIsNone(shoe.acquired_on)
        self.assertIsNone(shoe.retired_on)
        self.assertIsNone(shoe.target_distance_m)

    def test_activity_equipment_defaults_to_empty_list(self):
        first = Activity(id="a1", date=date(2026, 10, 1))
        second = Activity(id="a2", date=date(2026, 10, 2))

        first.equipment.append(Equipment(id="shoe-1", type="shoe", name="Pegasus 40"))

        self.assertEqual(1, len(first.equipment))
        self.assertEqual([], second.equipment)

    def test_activity_equipment_link_defaults(self):
        link = ActivityEquipment(activity_id="a1", equipment_id="shoe-1")

        self.assertEqual("primary", link.role)
        self.assertEqual("manual", link.source)
        self.assertFalse(link.is_manual)


if __name__ == "__main__":
    unittest.main()
