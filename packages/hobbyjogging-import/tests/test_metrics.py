import unittest

from hobbyjogging_import.metrics import derive_metrics


class DeriveMetricsTests(unittest.TestCase):

    def test_intervals_normalizes_run_cadence_and_units(self):
        values = derive_metrics(
            "intervals",
            {
                "average_cadence": 86.0,
                "average_stride": 1.31,
                "average_vertical_oscillation": 94.2,
                "average_stance_time": 238.6,
                "average_stance_time_percent": 34.6,
                "average_stance_time_balance": 48.2,
                "average_vertical_ratio": 7.36,
                "calories": 692,
                "AerobicEffect": 3.7,
                "gap": 3.08,
                "average_altitude": 191.2,
                "min_altitude": 184.8,
                "max_altitude": 213.8,
            },
            "run",
        )

        self.assertEqual(172.0, values["cadence"])
        self.assertEqual(1.31, values["stride_m"])
        self.assertEqual(94.2, values["vertical_oscillation_mm"])
        self.assertEqual(238.6, values["stance_time_ms"])
        self.assertEqual(34.6, values["stance_time_pct"])
        self.assertEqual(48.2, values["stance_balance_pct"])
        self.assertEqual(7.36, values["vertical_ratio_pct"])
        self.assertEqual(692.0, values["calories_kcal"])
        self.assertEqual(3.7, values["training_effect"])
        self.assertEqual(3.08, values["gap_mps"])
        self.assertEqual(191.2, values["altitude_avg_m"])

    def test_intervals_step_length_fallback_is_millimetres(self):
        values = derive_metrics(
            "intervals",
            {"average_step_length": 1247.4},
            "run",
        )

        self.assertAlmostEqual(1.2474, values["stride_m"])

    def test_runalyze_units_are_converted(self):
        values = derive_metrics(
            "runalyze",
            {
                "cadence": 86,
                "stride_length": 131,
                "vertical_oscillation": 95,
                "groundcontact": 239,
                "groundcontact_balance": 4821,
                "vertical_ratio": 73,
                "avg_respiratory_rate": 34,
                "power": 326,
                "kcal": 692,
                "fit_training_effect": 3.7,
                "gap": 13.62,
            },
            "run",
        )

        self.assertEqual(172.0, values["cadence"])
        self.assertEqual(1.31, values["stride_m"])
        self.assertEqual(95.0, values["vertical_oscillation_mm"])
        self.assertEqual(239.0, values["stance_time_ms"])
        self.assertEqual(48.21, values["stance_balance_pct"])
        self.assertEqual(7.3, values["vertical_ratio_pct"])
        self.assertEqual(34.0, values["respiration_bpm"])
        self.assertEqual(326.0, values["power_w"])
        self.assertEqual(692.0, values["calories_kcal"])
        self.assertEqual(3.7, values["training_effect"])
        self.assertAlmostEqual(3.7833, values["gap_mps"], places=4)

    def test_ride_cadence_is_not_doubled(self):
        values = derive_metrics("intervals", {"average_cadence": 86}, "ride")

        self.assertEqual(86.0, values["cadence"])

    def test_non_run_ride_cadence_is_not_stored(self):
        values = derive_metrics(
            "intervals", {"average_cadence": 60}, "swim"
        )

        self.assertEqual({}, values)

    def test_sheet_units(self):
        values = derive_metrics(
            "sheet",
            {
                "values": {
                    "Schrittfrequenz": 172,
                    "Vertikale Oszillation": 9.8,
                    "Bodenkontaktzeit": 250,
                    "Horizontal/Vertikal": 7.9,
                }
            },
            "run",
        )

        self.assertEqual(172.0, values["cadence"])
        self.assertEqual(98.0, values["vertical_oscillation_mm"])
        self.assertEqual(250.0, values["stance_time_ms"])
        self.assertEqual(7.9, values["vertical_ratio_pct"])

    def test_fit_payload_is_already_canonical(self):
        values = derive_metrics(
            "fit",
            {
                "session": {
                    "cadence": 172.0,
                    "stride_m": 1.29,
                    "calories": 692.0,
                    "training_effect": 3.7,
                }
            },
            "run",
        )

        self.assertEqual(172.0, values["cadence"])
        self.assertEqual(1.29, values["stride_m"])
        self.assertEqual(692.0, values["calories_kcal"])
        self.assertEqual(3.7, values["training_effect"])

    def test_missing_and_zero_values_are_dropped(self):
        values = derive_metrics(
            "runalyze",
            {"cadence": 0, "power": None, "gap": 0},
            "run",
        )

        self.assertEqual({}, values)


if __name__ == "__main__":
    unittest.main()
