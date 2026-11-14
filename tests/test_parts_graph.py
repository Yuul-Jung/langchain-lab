import unittest

import networkx as nx

import ontology_graph as og
import parts_graph as pg

ZET = [{"lib_id": "Zeta:ZX100", "name": "ZX100", "description": "fixed gadget alpha", "pin_count": 3}]


def onto(status="proposed"):
    g = nx.Graph()
    g.add_node("lib:Zeta", kind="library", label="Zeta")
    og.add_korean_bridge(g, [{"ko": ["가젯 알파"], "lib": ["Zeta"], "review_status": status}])
    return g


def deps(rows=None, backend="es-semantic", **kw):
    calls = []

    def find(q, n):
        calls.append((q, n))
        return (ZET if rows is None else rows), backend
    d = pg.PartsDeps(find=find, **kw)
    d.calls = calls
    return d


class PartsGraphTest(unittest.TestCase):
    def run_graph(self, d, q):
        return pg.ask_parts(pg.build_parts_graph(d), q)

    def test_answers_from_search_results_without_model(self):
        d = deps(ontology=onto(), include_proposed=True)
        r = self.run_graph(d, "가젯 알파 부품 추천해줘")
        self.assertTrue(r["answered"])
        self.assertIn("ZX100", r["answer"])
        self.assertIn("의미 검색", r["answer"])
        self.assertTrue(any("search[es-semantic]" in t for t in r["trace"]))

    def test_proposed_concepts_are_ignored_by_default(self):
        d = deps(ontology=onto("proposed"))
        r = self.run_graph(d, "가젯 알파 부품 추천해줘")
        self.assertFalse(r["answered"])
        self.assertEqual(d.calls, [])

    def test_approved_concepts_are_used(self):
        r = self.run_graph(deps(ontology=onto("approved")), "가젯 알파 부품 추천해줘")
        self.assertTrue(r["answered"])

    def test_no_intent_goes_to_existing_flow(self):
        d = deps(ontology=onto(), include_proposed=True)
        self.assertFalse(self.run_graph(d, "가젯 알파 동작 원리 설명해줘")["answered"])
        self.assertEqual(d.calls, [])

    def test_document_questions_are_not_hijacked(self):
        d = deps(ontology=onto(), include_proposed=True)
        self.assertFalse(self.run_graph(d, "올려 둔 문서에서 가젯 알파 부품 알려줘")["answered"])

    def test_no_results_falls_through(self):
        r = self.run_graph(deps(rows=[], ontology=onto(), include_proposed=True), "가젯 알파 부품 추천")
        self.assertFalse(r["answered"])
        self.assertNotIn("answer", r)

    def test_explain_words_block_but_do_not_match_inside_other_words(self):
        d = deps(ontology=onto(), include_proposed=True)
        # '가속도와' 안의 '도와'가 '도와줘'로 오인되던 버그 방지
        self.assertTrue(self.run_graph(d, "가속도와 가젯 알파 칩 추천")["answered"])
        self.assertFalse(self.run_graph(d, "가젯 알파 칩이 뭔지 알려줘")["answered"])
        self.assertFalse(self.run_graph(d, "가젯 알파 칩 사용 방법 알려줘")["answered"])

    def test_more_ways_of_asking_for_parts(self):
        d = deps(ontology=onto(), include_proposed=True)
        for q in ("가젯 알파 뭐 있어", "가젯 알파 찾아줘", "가젯 알파 쓸만한 거", "가젯 알파 어떤 거 써야 해"):
            self.assertTrue(self.run_graph(d, q)["answered"], q)

    def test_semantic_hook_used_only_when_exact_term_missing(self):
        g = onto()
        cid = [n for n, d in g.nodes(data=True) if d.get("kind") == "concept"][0]
        d = deps(ontology=g, include_proposed=True, semantic_concepts=lambda q: [cid])
        self.assertTrue(self.run_graph(d, "알파형 가젯 칩 찾아줘")["answered"])      # 사전에 없는 문구, 의미로 연결
        self.assertFalse(self.run_graph(d, "알파형 가젯 칩 사용 방법 알려줘")["answered"])  # 관문이 먼저 막는다

    def test_short_noun_phrase_with_concept_is_enough(self):
        d = deps(ontology=onto(), include_proposed=True)
        self.assertTrue(self.run_graph(d, "가젯 알파")["answered"])
        self.assertTrue(self.run_graph(d, "가젯 알파 16x2")["answered"])
        self.assertFalse(self.run_graph(d, "가젯 알파를 오늘 아침에 점검하고 나서 보고서를 쓰는 중입니다")["answered"])   # 긴 문장
        self.assertFalse(self.run_graph(d, "가젯 알파 뭐야")["answered"])                                             # 설명어

    def test_non_part_words_block_even_with_intent(self):
        d = deps(ontology=onto(), include_proposed=True)
        for q in ("가젯 알파 이어폰 추천", "가젯 알파 개발환경", "가젯 알파 가격", "가젯 알파 앱 추천"):
            self.assertFalse(self.run_graph(d, q)["answered"], q)

    def test_sentence_form_and_pin_questions_are_not_short_noun_phrases(self):
        d = deps(ontology=onto(), include_proposed=True)
        self.assertFalse(self.run_graph(d, "가젯 알파 순서가 바뀌나요?")["answered"])      # 물음표 문장
        self.assertFalse(self.run_graph(d, "가젯 알파 핀 배치")["answered"])               # 핀 질문은 핀 조회가 맡는다
        self.assertTrue(self.run_graph(d, "가젯 알파 뭐 있어?")["answered"])               # 의도어가 있으면 물음표여도 통과

    def test_similar_parts_for_an_english_part_name(self):
        catalog = [{"lib_id": "Zeta:ZX100", "name": "ZX100", "library": "Zeta_Linear", "description": "fixed gadget alpha",
                    "keywords": "gadget", "pins": [{"number": "1"}], "pin_count": 3},
                   {"lib_id": "Zeta:ZX100-SMD", "name": "ZX100-SMD", "library": "Zeta_Linear", "description": "fixed gadget alpha",
                    "keywords": "gadget", "pins": [{"number": "1"}], "pin_count": 3}]
        others = [{"lib_id": "Zeta:QW200", "name": "QW200", "library": "Zeta_Linear", "description": "adjustable gadget beta", "pin_count": 3}]
        seen = []

        def find(q, n):
            seen.append(q)
            return catalog + others, "es-semantic"
        d = pg.PartsDeps(find=find, catalog=catalog)
        r = self.run_graph(d, "ZX100 말고 다른 거 있어?")
        self.assertTrue(r["answered"])
        self.assertEqual([p["lib_id"] for p in r["parts"]], ["Zeta:QW200"])          # 기준 부품과 같은 이름 계열은 뺀다
        self.assertIn("ZX100", r["answer"])
        self.assertNotIn("ZX100", seen[0])                                              # 검색어에 부품 번호를 넣지 않는다
        self.assertIn("fixed gadget alpha", seen[0])
        self.assertFalse(self.run_graph(d, "ZX100 대체품 가격")["answered"])             # 비부품어(가격)
        self.assertFalse(self.run_graph(d, "ZX100 핀 배치 비슷한 거")["answered"])        # 핀 질문은 핀 조회가 맡는다
        self.assertFalse(self.run_graph(d, "ZX100 뭐야")["answered"])                    # 비슷한 부품을 찾는 말이 없음

    def test_consumer_install_cost_and_role_questions_are_not_parts(self):
        d = deps(ontology=onto(), include_proposed=True)
        for q in ("가젯 알파 공유기 추천", "가젯 알파 설치 비용 추천", "무선 충전 가젯 알파 추천", "가젯 알파가 뭐 하는 부품이야?",
                  "가젯 알파 역할이 뭐야"):
            self.assertFalse(self.run_graph(d, q)["answered"], q)

    def test_bare_tell_me_is_not_enough(self):
        self.assertFalse(self.run_graph(deps(ontology=onto(), include_proposed=True), "가젯 알파 알려줘")["answered"])

    def test_ontology_fallback_when_search_is_empty(self):
        g = nx.Graph()
        g.add_node("lib:Zeta", kind="library", label="Zeta")
        g.add_node("part:Zeta:ZX100", kind="part", label="ZX100", description="alpha", pin_count=3, has_datasheet=True)
        g.add_edge("part:Zeta:ZX100", "lib:Zeta", relation="in_library")
        og.add_korean_bridge(g, [{"ko": ["가젯 알파"], "lib": ["Zeta"], "review_status": "proposed"}])
        r = self.run_graph(deps(rows=[], ontology=g, include_proposed=True), "가젯 알파 부품 추천")
        self.assertTrue(r["answered"])
        self.assertEqual(r["backend"], "ontology")
        self.assertIn("ZX100", r["answer"])
        self.assertIn("온톨로지 키워드 검색", r["answer"])

    def test_no_ontology_goes_to_existing_flow(self):
        self.assertFalse(self.run_graph(deps(), "가젯 알파 부품 추천")["answered"])


if __name__ == "__main__":
    unittest.main()
