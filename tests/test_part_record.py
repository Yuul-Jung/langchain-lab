import unittest

import part_record as pr


class ParseTest(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(pr.parse_range("1.8V ~ 5.5V", "V"), (1.8, 5.5))
        self.assertEqual(pr.parse_range("-40°C ~ 85°C (TA)", "°C"), (-40.0, 85.0))
        self.assertEqual(pr.parse_range("3.3V", "V"), (3.3, 3.3))
        self.assertEqual(pr.parse_range("-", "V"), (None, None))

    def test_package_family_and_pins(self):
        self.assertEqual(pr.package_family("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"), "SOIC")
        self.assertEqual(pr.package_family('8-SOIC (0.154", 3.90mm Width)'), "SOIC")
        self.assertEqual(pr.package_family("SOT-23-5"), "SOT-23")
        self.assertEqual(pr.package_family("16-TSSOP"), "TSSOP")      # SOP 로 잘못 잡지 않음
        self.assertEqual(pr.pins_from_package('8-SOIC (0.154", 3.90mm Width)'), 8)
        self.assertEqual(pr.pins_from_package("SOT-23-5"), 5)


class ResolveTest(unittest.TestCase):
    def ev(self, src, lo, hi):
        return pr.evidence(src, f"{lo}~{hi}V", "ref", "2026-11-14", unit="V", lo=lo, hi=hi)

    def test_agreed_picks_highest_basis(self):
        r = pr.resolve([self.ev("digikey", 1.8, 5.5), self.ev("datasheet", 1.8, 5.5)])
        self.assertEqual(r["status"], "agreed")
        self.assertEqual(r["chosen"]["source"], "datasheet")

    def test_conflict_is_never_auto_chosen(self):
        r = pr.resolve([self.ev("digikey", 2.7, 5.5), self.ev("datasheet", 1.8, 5.5)])
        self.assertEqual(r["status"], "conflict")
        self.assertIsNone(r["chosen"])

    def test_single_and_unknown(self):
        self.assertEqual(pr.resolve([self.ev("kicad", 3.0, 3.6)])["status"], "single")
        self.assertEqual(pr.resolve([None])["status"], "unknown")

    def test_pins_compare_exact(self):
        a = pr.evidence("kicad", 8, "k", "d", unit="pins", typ=8)
        b = pr.evidence("digikey", 14, "m", "d", unit="pins", typ=14)
        self.assertEqual(pr.resolve([a, b])["status"], "conflict")


if __name__ == "__main__":
    unittest.main()


class ConverterTest(unittest.TestCase):
    def test_passes_all_evidence_with_source(self):
        a = pr.evidence("digikey", "2.7V ~ 5.5V", "MPN1", "d", unit="V", lo=2.7, hi=5.5)
        b = pr.evidence("datasheet", "1.8 to 5.5 V", "p3", "d", unit="V", lo=1.8, hi=5.5)
        t = pr.evidence("digikey", "-40°C ~ 85°C", "MPN1", "d", unit="°C", lo=-40, hi=85)
        rec = {"lib_id": "Zeta:X1", "fields": {"supply_voltage": pr.resolve([a, b]), "operating_temperature": pr.resolve([t])}}
        out = pr.to_constraint_record(rec)
        self.assertEqual(out["values"]["supply_min_v"], [{"value": 2.7, "source": "distributor", "ref": "MPN1"},
                                                         {"value": 1.8, "source": "datasheet", "ref": "p3"}])
        self.assertEqual(out["values"]["temp_max_c"], [{"value": 85, "source": "distributor", "ref": "MPN1"}])
        self.assertNotIn("abs_max_supply_v", out["values"])


class PinParseTest(unittest.TestCase):
    def test_diode_outline_numbers_are_not_pins(self):
        self.assertIsNone(pr.pins_from_package("DO-35"))
        self.assertIsNone(pr.pins_from_package("SOD-80"))
        self.assertEqual(pr.pins_from_package("TO-220-3"), 3)


class VariantAndSingleTest(unittest.TestCase):
    def test_single_supply_value_is_not_a_range(self):
        e = pr.evidence("digikey", "2.7 V", "M", "d", unit="V", conditions="단일 값(범위 아님)")
        r = pr.resolve([e])
        self.assertEqual(r["status"], "unknown")
        self.assertEqual(pr.to_constraint_record({"fields": {"supply_voltage": r}})["values"], {})

    def test_variants_with_different_grades_conflict(self):
        a = pr.evidence("digikey", "-40°C ~ 85°C", "SN74X", "d", unit="°C", lo=-40, hi=85)
        b = pr.evidence("digikey", "-40°C ~ 125°C", "74XBQ", "d", unit="°C", lo=-40, hi=125)
        r = pr.resolve([a, b])
        self.assertEqual(r["status"], "conflict")
        self.assertEqual(len(pr.to_constraint_record({"fields": {"operating_temperature": r}})["values"]["temp_max_c"]), 2)
