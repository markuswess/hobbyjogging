import unittest
from datetime import date, timedelta

from hobbyjogging_import.ods import Sheet
from hobbyjogging_import.performance_tests import (
    PerformanceTest,
    is_race,
    parse_payload,
    parse_performance_tests,
)

HEADER = ["Datum", "Startzeit", "Distanz", "Zielzeit", "CP Nr", "Name"]


def _row(**cells):
    row = [None] * 20
    for key, value in cells.items():
        row[int(key)] = value
    return row


def _block_rows(
    day,
    *,
    distance=10000.0,
    start=timedelta(hours=10),
    title="Race",
    result="",
    splits=((1000.0, 300.0),),
    total=None,
):
    rows = [
        _row(**{"0": day, "1": start, "2": distance, "4": "Start"}),
        _row(**{"0": title, "4": 1.0}),
    ]
    for index, (split_distance, seconds) in enumerate(splits, start=1):
        rows.append(
            _row(
                **{
                    "4": float(index),
                    "6": split_distance,
                    "7": split_distance * index,
                    "11": timedelta(seconds=seconds),
                    "14": 150.0,
                    "18": timedelta(
                        seconds=sum(part[1] for part in splits[:index])
                    ),
                }
            )
        )
    if result:
        rows.append(_row(**{"0": result}))
    return rows


class PerformanceTestParserTests(unittest.TestCase):

    def _parse(self, rows):
        return parse_performance_tests(Sheet("Leistungstests", [HEADER, *rows]))

    def test_reads_a_date_block_and_its_placement(self):
        rows = _block_rows(
            date(2016, 4, 10),
            distance=42195.0,
            title="Vienna City Marathon",
            result="Ergebnis: Gesamt 173., M-30: 34.",
            splits=((1000.0, 300.0), (1000.0, 310.0)),
        )

        blocks = self._parse(rows)

        self.assertEqual(1, len(blocks))
        block = blocks[0]
        self.assertEqual(date(2016, 4, 10), block.date)
        self.assertEqual("cell", block.date_source)
        self.assertEqual("10:00:00", block.start_time)
        self.assertEqual(42195.0, block.official_distance_m)
        self.assertEqual(610.0, block.official_time_s)
        self.assertEqual(173, block.place_total)
        self.assertEqual(34, block.place_ageclass)
        self.assertEqual("complete", block.status)
        self.assertEqual(2, len(block.splits))

    def test_parses_a_text_date_and_an_inferred_year(self):
        rows = _block_rows(date(2018, 9, 22), distance=6015.0)
        rows += _block_rows("29.9.", distance=10000.0)

        blocks = self._parse(rows)

        self.assertEqual(2, len(blocks))
        self.assertEqual(date(2018, 9, 29), blocks[1].date)
        self.assertEqual("inferred-year", blocks[1].date_source)

    def test_a_second_block_on_the_same_day_inherits_the_date(self):
        rows = _block_rows(date(2016, 10, 29), distance=10000.0)
        rows.append(_row(**{"1": timedelta(hours=16, minutes=30),
                            "2": 10000.0, "4": "Start"}))
        rows.append(_row(**{"0": "Mödlinger Altstadtlauf", "4": 1.0}))
        rows.append(
            _row(
                **{
                    "4": 1.0,
                    "6": 1000.0,
                    "7": 1000.0,
                    "11": timedelta(seconds=200),
                    "18": timedelta(seconds=200),
                }
            )
        )

        blocks = self._parse(rows)

        self.assertEqual(2, len(blocks))
        self.assertEqual(date(2016, 10, 29), blocks[1].date)
        self.assertEqual("inherited", blocks[1].date_source)
        self.assertEqual("Mödlinger Altstadtlauf", blocks[1].title)

    def test_reads_the_hr_step_layout(self):
        rows = [
            _row(**{"0": date(2016, 3, 18)}),
            _row(**{"0": "Geschw/Puls Test", "6": "Strecke"}),
            _row(**{"6": 1250.0, "7": 130.0,
                    "11": timedelta(seconds=395)}),
            _row(**{"6": 1250.0, "7": 140.0,
                    "11": timedelta(seconds=356)}),
        ]

        blocks = self._parse(rows)

        block = blocks[0]
        self.assertEqual("hr_steps", block.layout)
        self.assertEqual(2500.0, block.official_distance_m)
        self.assertEqual(751.0, block.official_time_s)
        self.assertEqual([130.0, 140.0], [split.avg_hr for split in block.splits])

    def test_broken_and_empty_blocks_are_flagged(self):
        rows = _block_rows(
            date(2021, 9, 11),
            title="VCM 10K",
            splits=(),
        )
        rows += [_row(**{"0": "17.10.2021"}), _row(**{"0": "Paris Marathon"})]

        blocks = self._parse(rows)

        self.assertEqual("broken", blocks[0].status)
        self.assertIn("no splits", blocks[0].problems)
        self.assertIn("no time", blocks[0].problems)
        self.assertEqual("broken", blocks[1].status)
        self.assertIn("no distance", blocks[1].problems)

    def test_reads_sieg_and_the_relay_placement(self):
        win = _block_rows(date(2021, 2, 16), title="LCC",
                          result="Ergebnis: Sieg")
        relay = _block_rows(date(2019, 4, 7), distance=15900.0,
                            title="Vienna City Marathon Staffel",
                            result="Gesamtstaffel 8., Klasse 7.")
        blocks = self._parse(win + relay)

        self.assertEqual(1, blocks[0].place_total)
        self.assertEqual(8, blocks[1].place_total)
        self.assertEqual(7, blocks[1].place_ageclass)

    def test_payload_round_trip(self):
        block = self._parse(_block_rows(
            date(2018, 4, 22),
            distance=42195.0,
            result="Gesamt 132., M-30: 34.",
        ))[0]

        restored = parse_payload(block.payload())

        self.assertIsNotNone(restored)
        self.assertEqual(block.date, restored.date)
        self.assertEqual(block.place_total, restored.place_total)
        self.assertEqual(block.place_ageclass, restored.place_ageclass)
        self.assertEqual(block.official_time_s, restored.official_time_s)
        self.assertEqual(len(block.splits), len(restored.splits))

    def test_race_classification(self):
        race = PerformanceTest(
            row=1,
            date=date(2016, 4, 10),
            title="VCM",
            result_text="",
        )
        test = PerformanceTest(
            row=1,
            date=date(2016, 3, 18),
            title="Geschw/Puls Test",
        )
        unnamed = PerformanceTest(row=1, date=date(2012, 11, 13))

        self.assertTrue(is_race(race))
        self.assertFalse(is_race(test))
        self.assertFalse(is_race(unnamed))
        self.assertTrue(is_race(unnamed, workout_methods={"race"}))
        self.assertTrue(is_race(unnamed, has_result=True))


if __name__ == "__main__":
    unittest.main()
