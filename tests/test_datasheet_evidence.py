import unittest

import datasheet_evidence as de

# 지어낸 데이터시트 글(실제 부품 아님)
ABS = "ABSOLUTE MAXIMUM RATINGS Rating Symbol Value Unit Supply voltage VCC -0.5 7 V Input voltage VI -0.5 7 V"
REC = ("Recommended Operating Conditions MIN MAX UNIT VCC Supply voltage 4.5 5.5 V "
       "TA Operating free-air temperature -40 85 °C")


def cands(text, page=3):
    return de.candidates_from_pages({page: text})


def vals(cs, field):
    return sorted({c["value"] for c in cs if c["field"] == field})


class Extract(unittest.TestCase):
    def test_abs_max_takes_upper_value_not_lower(self):
        self.assertEqual(vals(cands(ABS), "abs_max_supply_v"), [7.0])      # 0.5 로 읽으면 안 됨

    def test_recommended_range_and_temperature(self):
        c = cands(REC)
        self.assertEqual(vals(c, "supply_min_v"), [4.5])
        self.assertEqual(vals(c, "supply_max_v"), [5.5])
        self.assertEqual(vals(c, "temp_min_c"), [-40.0])
        self.assertEqual(vals(c, "temp_max_c"), [85.0])

    def test_every_candidate_has_quote_and_page(self):
        for c in cands(ABS + " " + REC, page=5):
            self.assertEqual(c["page"], 5)
            self.assertTrue(c["quote"])

    def test_abs_max_row_is_not_taken_as_recommended(self):
        self.assertEqual(vals(cands(ABS), "supply_max_v"), [])

    def test_no_number_no_value(self):
        self.assertEqual(cands("Supply voltage is applied to pin 3."), [])

    def test_pages_after_limit_are_ignored(self):
        self.assertEqual(de.candidates_from_pages({40: REC}, max_page=12), [])
        self.assertTrue(de.candidates_from_pages({40: REC}))   # 기본은 모든 쪽

    def test_evidence_uses_extracted_source(self):
        # 추출값은 사람이 확인한 데이터시트 값이 아니다
        import tempfile, unittest.mock as m
        with m.patch.object(de, "page_texts", return_value={2: REC}):
            ev = de.evidence("x.pdf", ref="x")
        self.assertTrue(all(e["source"] == "extracted" for v in ev["values"].values() for e in v))


if __name__ == "__main__":
    unittest.main()
