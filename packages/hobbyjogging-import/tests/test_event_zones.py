import unittest

from hobbyjogging_import.event_zones import (
    UNKNOWN,
    event_zone_data,
    infer_zone_kind,
    parse_zone_times,
)


def _pace(duration=600):
    return {"duration": duration, "pace": {"units": "%pace", "value": 70}}


def _hr(duration=600):
    return {"duration": duration, "hr": {"units": "%lthr", "value": 70}}


def _power(duration=600):
    return {"duration": duration, "power": {"units": "%ftp", "value": 70}}


def _workout(steps, zone_times):
    return {"steps": steps, "zoneTimes": zone_times}


class ZoneParsingTests(unittest.TestCase):

    def test_keeps_zero_seconds_and_known_labels(self):
        zones = parse_zone_times(
            {
                "zoneTimes": [
                    {"id": "Z1", "secs": 0},
                    {"id": "Z2", "secs": 600},
                    {"id": "Z7", "secs": 30},
                    {"id": "SS", "secs": 900},
                ]
            }
        )

        self.assertEqual(
            ["Z1", "Z2", "Z7", "SS"],
            [zone.zone_label for zone in zones],
        )
        self.assertEqual([0, 600, 30, 900], [zone.seconds for zone in zones])
        self.assertEqual([1, 2, 7, None], [zone.zone_index for zone in zones])

    def test_normalizes_lowercase_and_last_duplicate_wins(self):
        zones = parse_zone_times(
            {
                "zoneTimes": [
                    {"id": "z3", "secs": 60},
                    {"id": "Z3", "secs": 90},
                ]
            }
        )

        self.assertEqual(["Z3"], [zone.zone_label for zone in zones])
        self.assertEqual(90, zones[0].seconds)

    def test_ignores_unknown_labels_and_bad_durations(self):
        zones = parse_zone_times(
            {
                "zoneTimes": [
                    {"id": "Z8", "secs": 10},
                    {"id": "Z4", "secs": None},
                    {"id": "Z5", "secs": -1},
                    {"nope": 1},
                    "not a row",
                ]
            }
        )

        self.assertEqual([], zones)

    def test_missing_or_malformed_document_is_empty(self):
        self.assertEqual([], parse_zone_times(None))
        self.assertEqual([], parse_zone_times({}))
        self.assertEqual([], parse_zone_times({"zoneTimes": {}}))


class ZoneKindTests(unittest.TestCase):

    def test_dominant_step_target_wins(self):
        self.assertEqual(
            "pace",
            infer_zone_kind(_workout([_pace()], []), "run"),
        )
        self.assertEqual(
            "hr",
            infer_zone_kind(_workout([_hr()], []), "run"),
        )
        self.assertEqual(
            "power",
            infer_zone_kind(_workout([_power()], []), "ride"),
        )

    def test_dominant_target_uses_planned_seconds(self):
        document = _workout(
            [_hr(900), _pace(300)],
            [],
        )

        self.assertEqual("hr", infer_zone_kind(document, "run"))

    def test_nested_repeats_are_weighted(self):
        document = _workout(
            [
                {
                    "reps": 3,
                    "steps": [_hr(100), _pace(300)],
                }
            ],
            [],
        )

        self.assertEqual("pace", infer_zone_kind(document, "run"))

    def test_ties_follow_the_sport(self):
        run = _workout([{**_pace(), **_hr()}], [])
        ride = _workout([{**_power(), **_hr()}], [])

        self.assertEqual("pace", infer_zone_kind(run, "run"))
        self.assertEqual("power", infer_zone_kind(ride, "ride"))

    def test_without_targets_the_sport_decides(self):
        for sport in ("run", "trail_run", "treadmill_run"):
            with self.subTest(sport=sport):
                self.assertEqual(
                    "pace",
                    infer_zone_kind(_workout([], []), sport),
                )

        for sport in ("ride", "gravel_ride", "virtual_ride"):
            with self.subTest(sport=sport):
                self.assertEqual(
                    "power",
                    infer_zone_kind(_workout([], []), sport),
                )

        self.assertEqual(UNKNOWN, infer_zone_kind(_workout([], []), "soccer"))
        self.assertEqual(UNKNOWN, infer_zone_kind(_workout([], []), ""))

    def test_event_without_a_workout_document_clears_everything(self):
        kind, zones = event_zone_data({"id": 1}, "run")

        self.assertEqual("", kind)
        self.assertEqual([], zones)

    def test_event_data_combines_kind_and_zones(self):
        raw = {
            "workout_doc": {
                "steps": [_hr()],
                "zoneTimes": [{"id": "Z2", "secs": 600}],
            }
        }

        kind, zones = event_zone_data(raw, "run")

        self.assertEqual("hr", kind)
        self.assertEqual(["Z2"], [zone.zone_label for zone in zones])
