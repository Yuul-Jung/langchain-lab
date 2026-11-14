import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

import ontology_wikidata as ow

# 지어낸 가짜 Wikidata: 네트워크 없이 판정 규칙만 시험한다.
FAKE = {
    "Q1": {"labels": {"ko": {"value": "연산 증폭기"}, "en": {"value": "operational amplifier"}},
           "aliases": {"en": [{"value": "op-amp"}]}, "descriptions": {"en": {"value": "amplifier"}},
           "sitelinks": {"kowiki": {}}},
    "Q2": {"labels": {"ko": {"value": "증폭기 글꼴"}, "en": {"value": "Amplifier Typeface"}},
           "aliases": {}, "descriptions": {}, "sitelinks": {}},
    "Q3": {"labels": {"en": {"value": "widget"}}, "aliases": {}, "descriptions": {}, "sitelinks": {}},
}
SEARCH = {("연산 증폭기", "ko"): ["Q2", "Q1"], ("글꼴", "ko"): ["Q2"],
          ("operational amplifier", "en"): ["Q1"], ("widget", "en"): ["Q3"]}


def fake_fetch(url):
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    if q["action"] == "wbsearchentities":
        return {"search": [{"id": i} for i in SEARCH.get((q["search"], q["language"]), [])]}
    return {"entities": {i: FAKE.get(i, {"missing": ""}) for i in q["ids"].split("|")}}


class SeedCheck(unittest.TestCase):
    def setUp(self):
        self.f = ow.Fetcher(fetch=fake_fetch, delay=0)

    def test_match_skips_unrelated_first_result(self):
        r = ow.check_seed_entry(self.f, {"ko": ["연산 증폭기"], "kw": ["opamp", "operational"]})
        self.assertEqual(r[0]["verdict"], "match")
        self.assertEqual(r[0]["qid"], "Q1")
        self.assertEqual(r[0]["overlap"], ["operational"])
        self.assertEqual(r[0]["review_status"], "proposed")
        self.assertIn("wikidata.org/wiki/Q1", r[0]["url"])

    def test_mismatch_and_not_found(self):
        r = ow.check_seed_entry(self.f, {"ko": ["글꼴", "없는말"], "kw": ["regulator"]})
        self.assertEqual([x["verdict"] for x in r], ["mismatch", "not_found"])
        self.assertEqual(r[0]["qid"], "Q2")
        self.assertNotIn("qid", r[1])

    def test_ascii_terms_are_skipped(self):
        self.assertEqual(ow.check_seed_entry(self.f, {"ko": ["LDO"], "kw": ["ldo"]}), [])

    def test_library_name_counts_as_english_side(self):
        r = ow.check_seed_entry(self.f, {"ko": ["연산 증폭기"], "kw": [], "lib": ["Amplifier_Operational"]})
        self.assertEqual(r[0]["verdict"], "match")


class EnglishToKorean(unittest.TestCase):
    def setUp(self):
        self.f = ow.Fetcher(fetch=fake_fetch, delay=0)

    def test_exact_name_with_korean_label(self):
        r = ow.korean_for_english(self.f, "Operational Amplifier")
        self.assertIsNone(r)          # 검색어 대소문자가 달라 가짜 검색에서 못 찾음 → 없음
        r = ow.korean_for_english(self.f, "operational amplifier")
        self.assertEqual(r["ko_label"], "연산 증폭기")
        self.assertTrue(r["kowiki"])

    def test_no_korean_label_returns_none(self):
        self.assertIsNone(ow.korean_for_english(self.f, "widget"))


class Cache(unittest.TestCase):
    def test_second_run_uses_cache_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cache.json"
            f1 = ow.Fetcher(path, fetch=fake_fetch, delay=0)
            ow.korean_for_english(f1, "operational amplifier")
            f1.save()
            self.assertEqual(f1.calls, 2)

            def no_network(url):
                raise AssertionError("캐시에 있는데 네트워크를 불렀음")
            f2 = ow.Fetcher(path, fetch=no_network, delay=0)
            self.assertEqual(ow.korean_for_english(f2, "operational amplifier")["qid"], "Q1")
            self.assertEqual(f2.calls, 0)
            self.assertTrue(json.loads(path.read_text(encoding="utf-8")))


class Domain(unittest.TestCase):
    """지어낸 분류 사슬: 부품 → 반도체 → 전자 부품(기준) / 음반 → 작품(기준 아님)."""
    CLAIMS = {"A": {"P31": [], "P279": ["SEMI"]}, "SEMI": {"P31": [], "P279": ["ROOT"]},
              "ALBUM": {"P31": ["WORK"], "P279": []}, "WORK": {"P31": [], "P279": ["THING"]},
              "THING": {"P31": [], "P279": []}, "ROOT": {"P31": [], "P279": []},
              "INST": {"P31": ["SEMI"], "P279": []}, "LOOP": {"P31": [], "P279": ["LOOP2"]},
              "LOOP2": {"P31": [], "P279": ["LOOP"]}}

    def fetch(self, url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        claim = lambda ids: [{"mainsnak": {"datavalue": {"value": {"id": i}}}} for i in ids]
        return {"entities": {i: {"claims": {k: claim(v) for k, v in self.CLAIMS[i].items()}}
                             for i in q["ids"].split("|")}}

    def test_paths(self):
        f = ow.Fetcher(fetch=self.fetch, delay=0)
        got = ow.domain_paths(f, ["A", "ALBUM", "INST", "LOOP", "ROOT"], roots={"ROOT": "root"})
        self.assertEqual(got, {"A": "ROOT", "ALBUM": None, "INST": "ROOT", "LOOP": None, "ROOT": "ROOT"})

    def test_instance_only_on_first_step(self):
        # 둘째 걸음부터는 P31 을 따라가지 않는다: WORK 의 사례 관계가 기준에 닿아도 무시
        self.CLAIMS = {**self.CLAIMS, "WORK": {"P31": ["ROOT"], "P279": ["THING"]}}
        f = ow.Fetcher(fetch=self.fetch, delay=0)
        self.assertIsNone(ow.domain_paths(f, ["ALBUM"], roots={"ROOT": "root"})["ALBUM"])


if __name__ == "__main__":
    unittest.main()
