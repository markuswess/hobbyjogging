import unittest
from datetime import date, timedelta

from hobbyjogging_import.sheet import (
    alternativtraining_values,
    as_clock,
    as_date,
    as_float,
    as_seconds,
    clean_text,
    equipment_id,
    equipment_values,
    german_date,
    is_missing,
    local_start,
    rohdaten_values,
    row_record,
)


def _rohdaten(**overrides):
    record = {
        "Datum": date(2019, 1, 23),
        "Startzeit": timedelta(hours=17),
        "Strecke": "Liesingbachrunde",
        "Distanz in m": 13710.0,
        "Zeit": timedelta(minutes=65, seconds=29),
        "d. Hf": 142.0,
        "Trainigstyp": "ll",
        "Trainingsgebiet": "w",
        "Schuhe": 7.0,
        "Beschreibung": "Locker",
    }
    record.update(overrides)
    return record


class MissingValueTests(unittest.TestCase):

    def test_markers_and_empty_cells_are_missing(self):
        for value in (None, "", " ", "/", "N/A", "n/a", "#REF!", "#N/A", "-"):
            with self.subTest(value=value):
                self.assertTrue(is_missing(value))
        self.assertFalse(is_missing("0"))
        self.assertFalse(is_missing(0.0))

    def test_clean_text_strips_and_drops_markers(self):
        self.assertEqual("Halle", clean_text("  Halle "))
        self.assertEqual("", clean_text("/"))

    def test_numbers_accept_comma_and_text(self):
        self.assertEqual(42.5, as_float("42,5"))
        self.assertEqual(42.5, as_float(42.5))
        self.assertIsNone(as_float("/"))
        self.assertIsNone(as_float("abc"))

    def test_seconds_from_durations_and_text(self):
        self.assertEqual(3900, as_seconds(timedelta(hours=1, minutes=5)))
        self.assertEqual(3900, as_seconds("1:05:00"))
        self.assertIsNone(as_seconds(None))

    def test_dates(self):
        self.assertEqual(date(2011, 2, 3), as_date(date(2011, 2, 3)))
        self.assertEqual(date(2011, 2, 3), as_date("2011-02-03"))
        self.assertIsNone(as_date("/"))
        self.assertEqual(date(2008, 1, 1), german_date("1.1.2008"))
        self.assertEqual(date(2018, 4, 9), german_date("9.4.2018"))
        self.assertIsNone(german_date("2008-01-01"))
        self.assertIsNone(german_date("31.2.2008"))

    def test_clock_cells_and_hand_typed_times(self):
        self.assertEqual(
            as_clock(timedelta(hours=11, minutes=30)).hour,
            11,
        )
        self.assertEqual(as_clock("06:43").minute, 43)
        self.assertEqual(as_clock("8;19").minute, 19)
        self.assertIsNone(as_clock("/"))
        self.assertIsNone(as_clock("25:00"))


class RowRecordTests(unittest.TestCase):

    def test_keys_by_header_and_keeps_positions(self):
        headers = ["Datum", None, "Wert", None]
        row = [date(2019, 1, 1), "ignored", 42.0, "ignored"]

        self.assertEqual(
            {"Datum": date(2019, 1, 1), "Wert": 42.0},
            row_record(headers, row),
        )

    def test_blank_headers_can_be_named(self):
        headers = ["Id", "Typ", None, "Größe"]
        row = [1.0, "GT-2000", "weiß/rot", 42.5]

        self.assertEqual(
            {"Id": 1.0, "Typ": "GT-2000", "Farbe": "weiß/rot", "Größe": 42.5},
            row_record(headers, row, blank_names={2: "Farbe"}),
        )


class RohdatenMappingTests(unittest.TestCase):

    def test_maps_run_values_in_vienna_summer_time(self):
        values, tags, shoe = rohdaten_values(
            _rohdaten(Datum=date(2019, 7, 23))
        )

        self.assertEqual("2019-07-23", values["local_date"])
        self.assertEqual("run", values["sport"])
        self.assertEqual(3929.0, values["duration_s"])
        self.assertEqual(3929.0, values["elapsed_s"])
        self.assertEqual(13710.0, values["distance_m"])
        self.assertEqual(142.0, values["avg_hr"])
        self.assertEqual("Liesingbachrunde", values["name"])
        self.assertEqual("Locker", values["description"])
        # 17:00 CEST is 15:00 UTC.
        self.assertEqual("2019-07-23T15:00:00Z", values["started_at_utc"])
        self.assertEqual(120, values["tz_offset_min"])
        self.assertEqual(["ll", "w"], tags)
        self.assertEqual(7.0, shoe)

    def test_winter_time_uses_one_hour_offset(self):
        values, _, _ = rohdaten_values(_rohdaten())

        self.assertEqual("2019-01-23T16:00:00Z", values["started_at_utc"])
        self.assertEqual(60, values["tz_offset_min"])

    def test_missing_optional_cells_are_omitted(self):
        values, tags, shoe = rohdaten_values(
            _rohdaten(
                Startzeit=None,
                Strecke="/",
                Trainigstyp="/",
                Trainingsgebiet=None,
                Schuhe="/",
                **{"d. Hf": None, "Zeit": None},
            )
        )

        self.assertNotIn("started_at_utc", values)
        self.assertNotIn("name", values)
        self.assertNotIn("avg_hr", values)
        self.assertEqual(0.0, values["duration_s"])
        self.assertEqual([], tags)
        self.assertIsNone(shoe)

    def test_hand_typed_start_time_is_parsed(self):
        values, _, _ = rohdaten_values(_rohdaten(Startzeit="06:43"))

        self.assertEqual("2019-01-23T05:43:00Z", values["started_at_utc"])

    def test_row_without_date_is_rejected(self):
        with self.assertRaises(ValueError):
            rohdaten_values(_rohdaten(Datum=None))


class AlternativtrainingMappingTests(unittest.TestCase):

    def _record(self, was, **overrides):
        record = {
            "Datum": date(2020, 8, 1),
            "Uhrzeit": timedelta(hours=18),
            "Was": was,
            "Zeit": timedelta(hours=2),
            "Beschreibung": "Halle",
            "Puls Durchschnitt": 120.0,
        }
        record.update(overrides)
        return record

    def test_known_sports_keep_their_specific_name(self):
        self.assertEqual(
            "soccer",
            alternativtraining_values(self._record("Kicken"))["sport"],
        )
        self.assertEqual(
            "racket",
            alternativtraining_values(self._record("Badminton"))["sport"],
        )
        self.assertEqual(
            "ride",
            alternativtraining_values(self._record("Radfahren"))["sport"],
        )
        self.assertEqual(
            "other",
            alternativtraining_values(self._record("Einrad"))["sport"],
        )

    def test_distance_is_km_and_time_is_local(self):
        values = alternativtraining_values(
            self._record("Kicken", Distanz=15.68)
        )

        self.assertEqual(15680.0, values["distance_m"])
        self.assertEqual(7200.0, values["duration_s"])
        self.assertEqual(120.0, values["avg_hr"])
        self.assertEqual("2020-08-01T16:00:00Z", values["started_at_utc"])
        self.assertEqual("Kicken", values["name"])


class MarginTests(unittest.TestCase):

    def test_local_start_handles_dst(self):
        self.assertEqual(
            ("2020-01-15T10:00:00Z", 60),
            local_start(date(2020, 1, 15), as_clock("11:00")),
        )
        self.assertEqual(
            ("2020-07-15T09:00:00Z", 120),
            local_start(date(2020, 7, 15), as_clock("11:00")),
        )

    def test_equipment_id_normalizes_integral_floats(self):
        self.assertEqual("sheet:equipment:7", equipment_id(7.0))
        self.assertEqual("sheet:equipment:7", equipment_id("7"))
        self.assertIsNone(equipment_id("/"))


class EquipmentMappingTests(unittest.TestCase):

    def test_maps_brand_model_dates_and_notes(self):
        equipment = equipment_values(
            {
                "Id": 1.0,
                "Kaufdatum": "1.1.2008",
                "Marke": "Asics",
                "Typ": "GT-2000 1",
                "Farbe": "weiß/rot",
                "Größe": 42.5,
                "Kaufpreis": 140.0,
                "gesamt km": 1197.8656,
                "Entsorgungsdatum": "9.4.2018",
                "Bemerkungen": "Kaufdatum geschätzt",
            }
        )

        self.assertEqual("sheet:equipment:1", equipment.equipment_id)
        self.assertEqual("shoe", equipment.type)
        self.assertEqual("Asics GT-2000 1", equipment.name)
        self.assertEqual(date(2008, 1, 1), equipment.acquired_on)
        self.assertEqual(date(2018, 4, 9), equipment.retired_on)
        self.assertEqual(
            "Größe 42.5; Preis 140; gesamt 1197.87 km; "
            "Farbe weiß/rot; Kaufdatum geschätzt",
            equipment.notes,
        )

    def test_missing_model_falls_back_to_brand(self):
        equipment = equipment_values({"Id": 8.0, "Marke": "Skinners"})

        self.assertEqual("Skinners", equipment.name)
        self.assertEqual("", equipment.notes)


if __name__ == "__main__":
    unittest.main()
