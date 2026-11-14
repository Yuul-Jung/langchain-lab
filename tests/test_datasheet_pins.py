"""데이터시트 핀 표 해석 (PDF 없이, 행 해석 규칙만)."""
import unittest

import datasheet_pins as dp


class DatasheetPinsTest(unittest.TestCase):
    def test_expand_spec(self):
        self.assertEqual(dp.expand_spec("7"), [7])
        self.assertEqual(dp.expand_spec("5–12"), list(range(5, 13)))
        self.assertEqual(dp.expand_spec("24,23, 22"), [24, 23, 22])
        self.assertEqual(dp.expand_spec("GND"), [])
        self.assertEqual(dp.expand_spec(""), [])

    def test_name_first_and_number_first_rows(self):
        self.assertEqual(dp.parse_row(["1A", "2", "I", "Gate 1 input"]), [(2, "1A")])
        self.assertEqual(dp.parse_row(["13", "GND", "Ground"]), [(13, "GND")])

    def test_bus_name_expands_over_number_list(self):
        rows = dp.parse_row(["24,23,22,21", "ADBUS[3:0]", "I/O", "data bus"])
        self.assertEqual(rows, [(24, "ADBUS3"), (23, "ADBUS2"), (22, "ADBUS1"), (21, "ADBUS0")])

    def test_row_without_primary_package_pin_is_skipped(self):
        self.assertEqual(dp.parse_row(["NC", "—", "1, 5, 7", "—", "No internal connection"]), [])

    def test_normalize_ignores_case_and_overbars(self):
        self.assertEqual(dp.normalize("~{INT}/SQW"), dp.normalize("int/sqw"))

    def test_tables_without_header_are_ignored(self):
        junk = [["12", "W16#H2"], ["13", "W16#H2"]]
        good = [["PIN", "NAME"], ["1", "VCC"]]
        self.assertEqual(dp.pins_from_tables([junk, good]), {1: "VCC"})

    def test_first_seen_name_wins(self):
        t = [["Pin", "Name"], ["1", "AAA"], ["1", "BBB"]]
        self.assertEqual(dp.pins_from_tables([t]), {1: "AAA"})

    def test_compare_ignores_unnamed_truth_pins(self):
        truth = [{"number": "1", "name": "VCC"}, {"number": "2", "name": ""}, {"number": "3", "name": "~"}]
        r = dp.compare({1: "vcc", 2: "X", 9: "Y"}, truth)
        self.assertEqual((r["truth"], r["matched"], r["recall"], r["spurious"]), (1, 1, 1.0, 1))


if __name__ == "__main__":
    unittest.main()
