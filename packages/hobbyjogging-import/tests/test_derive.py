import unittest
from dataclasses import asdict


from hobbyjogging_import.derive import (
    FIELD_MAPS,
    Unmapped,
    derive_value,
    derive_values,
)
from hobbyjogging_import.fit import FitSession
from hobbyjogging_import.fit_import import _activity_values as fit_values
from hobbyjogging_import.intervals import _activity_values as intervals_values
from hobbyjogging_import.sheet import (
    alternativtraining_values,
    rohdaten_values,
)

INTERVALS_PAYLOAD = {
    "start_date": "2025-10-03T11:54:06Z",
    "start_date_local": "2025-10-03T13:54:06",
    "type": "Run",
    "name": "Easy",
    "description": "steady",
    "icu_recording_time": 5339,
    "moving_time": 5248,
    "elapsed_time": 5386,
    "distance": 16683.89,
    "average_heartrate": 133,
    "max_heartrate": 147,
    "total_elevation_gain": 123.0,
    "total_elevation_loss": 111.0,
    "icu_training_load": 69,
    "icu_rpe": 2,
    "feel": 1,
    "icu_intensity": 68.209656,
    "device_name": "GARMIN ENDURO",
}

ROHDATEN_ROW = {
    "Datum": "2026-10-01",
    "Zeit": "1:00:00",
    "Distanz in m": 10000,
    "Strecke": "Wienerberg",
    "Beschreibung": "easy",
    "d. Hf": 140,
    "max. Hf": 160,
    "m bergauf": 30,
    "Startzeit": "08:00",
}

ALTERNATIV_ROW = {
    "Datum": "2026-10-02",
    "Was": "Rad",
    "Distanz": 30.0,
    "Zeit": "1:30:00",
    "Puls Durchschnitt": 120,
    "Uhrzeit": "09:00",
    "Beschreibung": "commute",
}


def _assert_covers(test, derived, actual):
    """Every imported value is derived, and the rest is empty."""
    for field, value in actual.items():
        test.assertEqual(value, derived.get(field), field)
    for field, value in derived.items():
        if field not in actual:
            test.assertIn(value, (None, ""), field)


class IntervalsMapTests(unittest.TestCase):

    def test_map_reproduces_the_importer(self):
        derived = derive_values("intervals", INTERVALS_PAYLOAD)
        actual = intervals_values(INTERVALS_PAYLOAD)
        actual["device_id"] = "intervals:garmin-enduro"
        _assert_covers(self, derived, actual)

    def test_duration_falls_back_to_moving_time(self):
        payload = dict(INTERVALS_PAYLOAD, icu_recording_time=0)

        self.assertEqual(
            5248.0,
            derive_value("intervals", "duration_s", payload),
        )

    def test_tz_offset_is_derived_from_the_two_starts(self):
        self.assertEqual(
            120,
            derive_value("intervals", "tz_offset_min", INTERVALS_PAYLOAD),
        )


class FitMapTests(unittest.TestCase):

    def _session(self):
        return FitSession(
            index=0,
            start_time_utc="2026-11-01T09:35:08Z",
            local_start="2026-11-01T10:35:08+01:00",
            tz_offset_min=60,
            sport="running",
            sub_sport="generic",
            canonical_sport="run",
            name="Run",
            elapsed_s=2562.121,
            duration_s=2562.121,
            distance_m=10166.61,
            moving_s=2500.0,
            avg_hr=151,
            max_hr=169,
            ascent_m=41,
            descent_m=38,
            vo2max_garmin=62.98,
        )

    def test_map_reproduces_the_importer(self):
        session = self._session()
        payload = {
            "file": {
                "manufacturer": "garmin",
                "product": "enduro",
                "serial_number": "3386253273",
            },
            "session": asdict(session),
        }

        derived = derive_values("fit", payload)
        actual = fit_values(session)
        actual["device_id"] = "fit:garmin:enduro:3386253273"
        _assert_covers(self, derived, actual)

    def test_generic_sub_sport_is_empty(self):
        payload = {
            "session": {"sub_sport": "generic"},
            "file": {},
        }
        self.assertIsNone(derive_value("fit", "sub_sport", payload))


class SheetMapTests(unittest.TestCase):

    def test_rohdaten_map_reproduces_the_importer(self):
        values, _tags, _shoe = rohdaten_values(ROHDATEN_ROW)
        derived = derive_values(
            "sheet",
            {"sheet": "Rohdaten", "values": ROHDATEN_ROW},
        )
        _assert_covers(self, derived, values)

    def test_alternativtraining_map_reproduces_the_importer(self):
        values = alternativtraining_values(ALTERNATIV_ROW)
        derived = derive_values(
            "sheet",
            {"sheet": "Alternativtraining", "values": ALTERNATIV_ROW},
        )
        _assert_covers(self, derived, values)


class OtherSourceMapTests(unittest.TestCase):

    def test_runalyze_maps_the_note_and_vo2max(self):
        payload = {"note": "felt good", "vo2max": 56.16}

        self.assertEqual(
            "felt good",
            derive_value("runalyze", "description", payload),
        )
        self.assertEqual(
            56.16,
            derive_value("runalyze", "vo2max_runalyze", payload),
        )

    def test_strava_has_no_canonical_fields(self):
        self.assertEqual({}, FIELD_MAPS["strava"])
        self.assertEqual({}, derive_values("strava", {}))

    def test_an_unmapped_field_raises(self):
        with self.assertRaises(Unmapped):
            derive_value("strava", "distance_m", {})


if __name__ == "__main__":
    unittest.main()
