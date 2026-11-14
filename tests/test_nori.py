import tempfile
import unittest
from pathlib import Path
from unittest import mock

import document_pipeline as dp
import nori_dict


class Dictionary(unittest.TestCase):
    def test_candidates_only_electronics_and_hangul_words(self):
        wd = [{"domain": "electronics", "verdict": "match", "qid": "Q1", "term": "가나다라",
               "ko_label": "마바 사아", "ko_aliases": ["별칭어"]},
              {"domain": "electronics", "verdict": "mismatch", "qid": "Q3", "term": "어긋남"},
              {"domain": "other", "verdict": "match", "qid": "Q2", "term": "자차카", "ko_label": "타파하"}]
        seed = [{"ko": ["거너더 러", "머버서", "X"]}]
        got = nori_dict.candidate_terms(wd, seed)
        # 띄어 쓴 용어의 조각(마바·사아·거너더)·별칭·어긋남·다른 분야는 넣지 않는다
        self.assertEqual(set(got), {"가나다라", "머버서"})
        self.assertEqual(got["가나다라"], "Wikidata Q1")
        self.assertIn("승인 전", got["머버서"])

    def test_needs_entry_rule(self):
        t = lambda *ws, pos="NNG": [{"token": w, "pos": pos} for w in ws]
        self.assertTrue(nori_dict.needs_entry(t("가", "나다")))        # 한 글자 조각 → 깨짐
        self.assertFalse(nori_dict.needs_entry(t("가나", "다라")))     # 두 글자 이상 조각만 → 자연 분해
        self.assertFalse(nori_dict.needs_entry(t("가나다")))           # 안 나뉨
        self.assertFalse(nori_dict.needs_entry(t("가나", "다", pos="JKO")))  # 조사 → 넣지 않음

    def test_read_rules_skips_comments(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "dict.txt"
            p.write_text("# 주석\n가나다\n\n  # 또 주석\n라마바\n", encoding="utf-8")
            self.assertEqual(nori_dict.read_rules(p), ["가나다", "라마바"])
            self.assertEqual(nori_dict.read_rules(Path(d) / "없음.txt"), [])

    def test_analysis_carries_rules(self):
        a = nori_dict.index_analysis(["가나다"])
        self.assertEqual(a["tokenizer"]["ko_nori_tok"]["user_dictionary_rules"], ["가나다"])
        self.assertIn(nori_dict.ANALYZER, a["analyzer"])


class Pipeline(unittest.TestCase):
    def test_lexical_query_adds_nori_clause_only_when_on(self):
        with mock.patch.object(dp.settings, "DOCUMENT_NORI", False):
            off = dp.lexical_candidates_query("레귤레이터 추천")
        with mock.patch.object(dp.settings, "DOCUMENT_NORI", True):
            on = dp.lexical_candidates_query("레귤레이터 추천")
        self.assertEqual(len(on["bool"]["should"]), len(off["bool"]["should"]) + 1)
        self.assertEqual(on["bool"]["should"][-1]["constant_score"]["filter"], {"match": {"text.nori": "레귤레이터 추천"}})
        self.assertNotIn("text.nori", str(off))

    def _created(self, nori_on):
        es = mock.MagicMock()
        es.indices.exists.return_value = False
        with mock.patch.object(dp.settings, "DOCUMENT_NORI", nori_on):
            dp._ensure_index(es)
        return es.indices.create.call_args.kwargs

    def test_new_index_mapping(self):
        off, on = self._created(False), self._created(True)
        self.assertNotIn("settings", off)
        self.assertNotIn("fields", off["mappings"]["properties"]["text"])
        self.assertEqual(on["mappings"]["properties"]["text"]["fields"]["nori"]["analyzer"], nori_dict.ANALYZER)
        self.assertIn("analysis", on["settings"])
        self.assertEqual(on["mappings"]["properties"]["embedding"], off["mappings"]["properties"]["embedding"])


if __name__ == "__main__":
    unittest.main()
