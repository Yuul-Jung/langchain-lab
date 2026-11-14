import json
import tempfile
import unittest
from pathlib import Path

import bridge_terms as bt


class BridgeTermsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.ph, self.ap = d / "p.jsonl", d / "a.jsonl"
        rows = [{"en": "rise time", "ko": "상승 시간"}, {"en": "time", "ko": "시간"}, {"en": "supply voltage", "ko": "공급전압"},
                {"en": "duty cycle", "ko": "듀티 사이클"}, {"en": "data", "ko": "데이터"}]
        self.ph.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
        ok = [{"en": r["en"], "ko": r["ko"], "decision": "approved"} for r in rows if r["en"] != "duty cycle"]
        ok.append({"en": "data", "ko": "데이터", "decision": "rejected"})          # 마지막 줄이 이긴다
        self.ap.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in ok), encoding="utf-8")
        bt._cache.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        return bt.load(self.ph, self.ap)

    def test_only_approved_and_longest_first(self):
        self.assertEqual(bt.english_for("I2C 상승 시간은?", self.rows()), ["rise time"])     # '시간'은 겹쳐서 빠짐
        self.assertEqual(bt.english_for("듀티 사이클 데이터", self.rows()), [])               # 미승인·반려

    def test_spacing_ignored_and_existing_english_skipped(self):
        self.assertEqual(bt.english_for("공급 전압 범위", self.rows()), ["supply voltage"])
        self.assertEqual(bt.english_for("supply voltage 공급전압", self.rows()), [])

    def test_missing_files_mean_no_terms(self):
        bt._cache.clear()
        self.assertEqual(bt.english_for("상승 시간", bt.load(Path("/nope/a"), Path("/nope/b"))), [])


if __name__ == "__main__":
    unittest.main()
