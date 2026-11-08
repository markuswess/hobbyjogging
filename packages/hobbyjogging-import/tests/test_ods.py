import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hobbyjogging_import.ods import (
    OdsError,
    parse_duration,
    read_sheet,
    read_sheets,
    sheet_names,
)

from ods_fixture import COVERED, ColumnRepeat, RawCell, RowRepeat, write_ods


class OdsReaderTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "test.ods"

    def _write(self, sheets):
        return write_ods(self.path, sheets)

    def test_typed_cells_and_positions(self):
        self._write(
            [
                (
                    "Typed",
                    [
                        [
                            "text",
                            42.5,
                            date(2011, 2, 3),
                            timedelta(hours=11, minutes=30),
                            True,
                            None,
                            COVERED,
                            RawCell(
                                '<table:table-cell office:value-type="percentage" '
                                'office:value="0.25"/>'
                            ),
                            RawCell(
                                '<table:table-cell office:value-type="currency" '
                                'office:value="19.99"/>'
                            ),
                        ]
                    ],
                )
            ]
        )

        sheet = read_sheet(self.path, "Typed")

        self.assertEqual(
            [
                "text",
                42.5,
                date(2011, 2, 3),
                timedelta(hours=11, minutes=30),
                True,
                None,
                None,
                0.25,
                19.99,
            ],
            sheet.rows[0],
        )

    def test_repeated_columns_and_rows_are_expanded(self):
        self._write(
            [
                (
                    "Repeats",
                    [
                        [ColumnRepeat("x", 3), "y"],
                        RowRepeat(["a", 1], 2),
                    ],
                )
            ]
        )

        rows = read_sheet(self.path, "Repeats").rows

        self.assertEqual([["x", "x", "x", "y"], ["a", 1], ["a", 1]], rows)

    def test_trailing_padding_is_skipped(self):
        self._write(
            [
                (
                    "Padded",
                    [
                        ["value", ColumnRepeat(None, 1_000_000)],
                        RowRepeat([], 1_000_000),
                    ],
                )
            ]
        )

        rows = read_sheet(self.path, "Padded").rows

        self.assertEqual([["value"]], rows)

    def test_cached_formula_value_is_used(self):
        self._write(
            [
                (
                    "Formula",
                    [
                        [
                            RawCell(
                                '<table:table-cell table:formula="of:=1+1" '
                                'office:value-type="float" office:value="2"/>'
                            ),
                            RawCell(
                                '<table:table-cell table:formula="of:=&quot;a&quot;" '
                                'office:value-type="string"><text:p>a</text:p>'
                                "</table:table-cell>"
                            ),
                        ]
                    ],
                )
            ]
        )

        self.assertEqual(
            [2.0, "a"],
            read_sheet(self.path, "Formula").rows[0],
        )

    def test_multiple_sheets_keep_order_and_names(self):
        self._write(
            [
                ("First", [["a"]]),
                ("Zweite", [["b"], ["c"]]),
            ]
        )

        self.assertEqual(["First", "Zweite"], sheet_names(self.path))
        self.assertEqual(
            [["b"], ["c"]],
            read_sheet(self.path, "Zweite").rows,
        )

    def test_header_index_skips_title_rows(self):
        self._write(
            [
                (
                    "Material",
                    [
                        ["Schuhe"],
                        ["Id", "Kaufdatum", "Marke"],
                        [1, "1.1.2008", "Asics"],
                    ],
                )
            ]
        )

        sheet = read_sheet(self.path, "Material")

        self.assertEqual(1, sheet.header_index(("Id", "Marke")))
        with self.assertRaises(OdsError):
            sheet.header_index(("Missing",))

    def test_missing_sheet_and_file_errors(self):
        self._write([("Only", [["x"]])])

        with self.assertRaises(OdsError):
            read_sheet(self.path, "Nope")

        missing = Path(self.directory.name) / "missing.ods"
        with self.assertRaises(OdsError):
            read_sheets(missing)

    def test_rows_inside_groups_are_read(self):
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-content '
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            "<office:body><office:spreadsheet>"
            '<table:table table:name="Grouped">'
            "<table:table-row-group>"
            '<table:table-row><table:table-cell office:value-type="string">'
            "<text:p>inside</text:p></table:table-cell></table:table-row>"
            "</table:table-row-group>"
            "</table:table></office:spreadsheet></office:body>"
            "</office:document-content>"
        )
        import zipfile

        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("content.xml", content)

        self.assertEqual(
            [["inside"]],
            read_sheet(self.path, "Grouped").rows,
        )


class DurationParsingTests(unittest.TestCase):

    def test_parses_hours_minutes_and_fractional_seconds(self):
        self.assertEqual(
            timedelta(hours=11, minutes=30),
            parse_duration("PT11H30M00S"),
        )
        self.assertEqual(
            timedelta(minutes=5, seconds=9.1349374),
            parse_duration("PT00H05M09.1349374S"),
        )
        self.assertEqual(
            timedelta(days=1, hours=2),
            parse_duration("P1DT2H"),
        )

    def test_rejects_invalid_durations(self):
        for value in ("", "11:30", "PT", "P"):
            with self.subTest(value=value):
                with self.assertRaises(OdsError):
                    parse_duration(value)


if __name__ == "__main__":
    unittest.main()
