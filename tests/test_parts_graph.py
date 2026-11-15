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

    def test_learned_veto_turns_part_question_into_not_handled(self):
        seen = []
        d = deps(ontology=onto("approved"), veto=lambda q: seen.append(q) or True)
        r = self.run_graph(d, "가젯 알파 부품 추천")
        self.assertFalse(r["answered"])
        self.assertEqual(d.calls, [])                       # 검색하지 않음
        self.assertEqual(seen, ["가젯 알파 부품 추천"])
        self.assertTrue(any("학습 관문" in t for t in r["trace"]))

    def test_veto_is_asked_only_after_rules_accept(self):
        seen = []
        d = deps(ontology=onto("approved"), veto=lambda q: seen.append(q) or False)
        self.assertTrue(self.run_graph(d, "가젯 알파 부품 추천")["answered"])
        self.assertFalse(self.run_graph(deps(ontology=onto("approved"), veto=lambda q: seen.append(q) or False),
                                        "오늘 점심 뭐 먹지")["answered"])
        self.assertEqual(seen, ["가젯 알파 부품 추천"])     # 규칙이 거른 질문에는 모델을 부르지 않음

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

    def test_short_part_noun_question_without_concept_is_searched_as_is(self):
        d = deps(ontology=onto("approved"))
        r = self.run_graph(d, "베타 측정용 칩")
        self.assertTrue(r["answered"])
        self.assertEqual(d.calls[0][0], "베타 측정용 칩")
        for q in ["베타 측정용 칩 있어?", "감자칩 추천", "베타 칩 고장 났어", "베타 칩 중고로 사도 될까", "베타 칩 고르는 요령"]:
            self.assertFalse(self.run_graph(deps(ontology=onto("approved")), q)["answered"], q)

    def test_fallback_does_not_bypass_unapproved_concept(self):
        self.assertFalse(self.run_graph(deps(ontology=onto("proposed")), "가젯 알파 칩")["answered"])

    def test_results_in_concept_library_come_first(self):
        rows = [{"lib_id": "Other:Q1", "name": "Q1", "description": "x"}, {"lib_id": "Zeta:ZX100", "name": "ZX100", "description": "y"}]
        r = self.run_graph(deps(rows=rows, ontology=onto("approved")), "가젯 알파 부품 추천")
        self.assertEqual([p["lib_id"] for p in r["parts"]], ["Zeta:ZX100", "Other:Q1"])

    def test_part_number_followed_by_gatchi_is_similar_request(self):
        self.assertTrue(pg.SIMILAR.search("ZX100 같은 측정 칩"))
        self.assertFalse(pg.SIMILAR.search("같은 값으로 바꿔줘"))

    def test_how_to_and_troubleshooting_are_not_part_requests(self):
        for q in ["가젯 알파 구별법 알려줘", "가젯 알파에서 냄새가 나", "가젯 알파가 안 켜져"]:
            self.assertEqual(pg.parts_concepts(q, onto("approved")), [], q)
        self.assertEqual(len(pg.parts_concepts("옴의 법칙 가젯 알파 부품 추천", onto("approved"))), 1)


class AnchorLockTest(unittest.TestCase):
    """기준 부품 고정(anchor_lock, 기본 꺼짐). 값·이름은 지어낸 것."""

    class Tax:   # 분류 체계 대역: 라이브러리 → 기능. Mix 는 혼합(근거 없이 대표 기능), Gen 은 일반 라이브러리(기능 없음)
        F = {"Zeta_Linear": "alpha", "Zeta_Other": "alpha", "Yota": "beta"}

        def classify(self, lib, name, text=""):
            if lib == "Gen":
                return None
            if lib == "Mix":
                return {"function": "alpha", "domain": "d", "kind": "ic", "mixed": True, "by": "대표 기능"}
            return {"function": self.F[lib], "domain": "d", "kind": "ic", "mixed": False, "by": "대표 기능"}

        def label(self, info):
            return f"기능 {info['function']}"

        def index(self, catalog):
            by = {}
            for p in catalog:
                i = self.classify(p["library"], p["name"])
                if i:
                    by.setdefault(i["function"], []).append(p)
            return by

    @staticmethod
    def part(lib, name, desc="gadget", pins=3):
        return {"lib_id": f"{lib}:{name}", "name": name, "library": lib, "description": desc, "keywords": "", "pins": [{"number": "1"}],
                "pin_count": pins}

    def setUp(self):
        P = self.part
        self.catalog = [P("Zeta_Linear", "ZX100"), P("Zeta_Linear", "QW200"), P("Zeta_Other", "QW300", pins=8), P("Yota", "UART900", "uart bridge"),
                        P("Mix", "MX500"), P("Mix", "MX600"), P("Gen", "GN700")]
        self.rows = [self.catalog[3], self.catalog[1]]       # 검색은 다른 기능(Yota) 부품을 먼저 돌려준다

    def graph(self, lock, rows=None, **kw):
        rows = self.rows if rows is None else rows
        d = pg.PartsDeps(find=lambda q, n: (rows, "es-semantic"), catalog=self.catalog, taxonomy=self.Tax(), anchor_lock=lock, **kw)
        return lambda q: pg.ask_parts(pg.build_parts_graph(d), q)

    def test_candidates_stay_inside_anchor_function(self):
        r = self.graph(True)("ZX100 대체품")
        self.assertTrue(r["answered"])
        self.assertEqual([p["lib_id"] for p in r["parts"]], ["Zeta_Linear:QW200", "Zeta_Other:QW300"])   # Yota 는 빠지고, 모자란 자리는 같은 기능으로 채움
        self.assertEqual([bool(p.get("filled")) for p in r["parts"]], [False, True])
        self.assertIn("기능 alpha", r["answer"])
        off = self.graph(False)("ZX100 대체품")
        self.assertEqual([p["lib_id"] for p in off["parts"]], ["Yota:UART900", "Zeta_Linear:QW200"])     # 꺼져 있으면 원래 동작 그대로

    def test_condition_words_do_not_change_function(self):
        r = self.graph(True, conditions=True)("ZX100 구하기 어려워서 UART 지원 다른 걸로 바꾸고 싶은데 추천해 주세요.")
        self.assertTrue(r["answered"])
        self.assertTrue(all(p["library"].startswith("Zeta") for p in r["parts"]))
        self.assertEqual(r["conditions"], ["UART"])
        self.assertFalse(self.graph(False, conditions=True)("ZX100 구하기 어려워서 UART 지원 다른 걸로 바꾸고 싶은데 추천해 주세요.")["answered"])

    def test_english_replacement_words_only_with_lock(self):
        for q in ("ZX100 drop-in replacement 추천", "ZX100 alternative part 찾아줘", "ZX100 교체할 부품 추천"):
            self.assertTrue(self.graph(True)(q)["answered"], q)
            self.assertFalse(self.graph(False)(q)["answered"], q)

    def test_unknown_part_number_is_not_guessed(self):
        r = self.graph(True)("QQ9999 대체품 UART 지원 추천")
        self.assertFalse(r["answered"])
        self.assertIn("QQ9999", r["abstain"])
        self.assertFalse(self.graph(True)("QQ9999 설명해줘").get("abstain"))          # 대체를 묻지 않으면 이 규칙이 끼어들지 않는다
        self.assertEqual(pg.unknown_part_tokens("3.3V SOT-23 I2C RS485 24V 100mA TSSOP-16 QQ9999", self.catalog), ["QQ9999"])

    def test_generic_and_ambiguous_anchor_abstains_and_mixed_uses_library(self):
        r = self.graph(True)("GN700 대체품")
        self.assertFalse(r["answered"])
        self.assertIn("일반 라이브러리", r["abstain"])
        r = self.graph(True, rows=[self.catalog[1], self.catalog[5]])("MX500 대체품")      # 혼합 라이브러리: 같은 라이브러리의 검색 결과만, 채우지 않음
        self.assertEqual([p["lib_id"] for p in r["parts"]], ["Mix:MX600"])
        self.assertFalse(self.graph(True, rows=[self.catalog[1]])("MX500 대체품")["answered"])
        self.catalog.append(self.part("Yota", "ZX100"))                                     # 같은 번호가 두 기능에 걸침
        r = self.graph(True)("ZX100 대체품")
        self.assertFalse(r["answered"])
        self.assertIn("여러 기능", r["abstain"])

    def test_condition_token_is_not_an_anchor(self):
        self.catalog.append(self.part("Yota", "24V-RELAY"))
        self.catalog.append(self.part("Yota", "0603USB-142"))                              # 칩 크기 코드로 시작하는 부품 이름
        r = self.graph(True)("0603 100nF 대체품")
        self.assertFalse(r.get("anchor"))
        self.assertFalse(r.get("abstain"))                                                   # 부품 번호가 없으니 '없는 번호' 기권도 아니다
        r = self.graph(True)("QQ9999 대체품 24V 추천")
        self.assertFalse(r["answered"])
        self.assertIn("QQ9999", r["abstain"])


class UnknownNoticeTest(unittest.TestCase):
    """'카탈로그에 없음' 안내(unknown_notice, 기본 꺼짐). 값·이름은 지어낸 것."""

    def setUp(self):
        self.catalog = [AnchorLockTest.part("Zeta_Linear", "ZX100"), AnchorLockTest.part("Zeta_Linear", "QW200")]

    def graph(self, **kw):
        d = pg.PartsDeps(find=lambda q, n: (self.catalog, "es-semantic"), catalog=self.catalog, **kw)
        return lambda q: pg.ask_parts(pg.build_parts_graph(d), q)

    def test_unknown_number_gets_fixed_notice_instead_of_parts(self):
        r = self.graph(unknown_notice=True)("QQ9999 대체품 UART 지원 추천")
        self.assertTrue(r["answered"])
        self.assertEqual(r["parts"], [])
        self.assertEqual(r["backend"], "catalog-miss")
        self.assertIn("`QQ9999`", r["answer"])
        self.assertIn("찾지 못해 대체품을 추천하지 않습니다", r["answer"])
        self.assertIn("QQ9999", r["abstain"])

    def test_off_by_default_and_known_number_unchanged(self):
        self.assertFalse(self.graph()("QQ9999 대체품 추천")["answered"])                         # 꺼져 있으면 원래 동작(기존 흐름으로)
        r = self.graph(unknown_notice=True)("ZX100 대체품")
        self.assertEqual([p["lib_id"] for p in r["parts"]], ["Zeta_Linear:QW200"])                # 카탈로그에 있는 번호는 그대로 답함
        self.assertFalse(r.get("notice"))

    def test_no_notice_without_substitute_words_or_part_number(self):
        ask = self.graph(unknown_notice=True)
        for q in ("QQ9999 핀 배열 알려줘", "QQ9999이 뭐 하는 부품이야?", "QQ9999 대체품 가격", "3.3V SOT-23 대체품 추천", "대체 공휴일이 언제야?"):
            self.assertFalse(ask(q).get("notice"), q)

    def test_broadened_words_alone_never_show_the_notice(self):
        # 넓힌 표현(영어 replacement 등)은 수리·사양 문장도 잡으므로 안내문을 내지 않는다(기준 부품 고정이 켜져 있으면 조용히 답하지 않음)
        for lock in (False, True):
            r = self.graph(unknown_notice=True, anchor_lock=lock, taxonomy=AnchorLockTest.Tax())("QQ9999 replacement 하다가 패드가 떨어졌어요")
            self.assertFalse(r["answered"], lock)
            self.assertFalse(r.get("notice"), lock)

    def test_part_without_pin_data_is_not_called_missing(self):
        self.catalog.append({**AnchorLockTest.part("Zeta_Linear", "NP300"), "pins": []})          # 카탈로그에는 있지만 핀 정보가 없는 부품
        r = self.graph(unknown_notice=True)("NP300 대체품 추천")
        self.assertFalse(r.get("notice"))
        self.assertEqual(pg.unknown_part_tokens("NP300 대체품", self.catalog), [])

    def test_learned_gate_can_veto_the_notice(self):
        r = self.graph(unknown_notice=True, veto=lambda q: True)("QQ9999 대체품 추천")
        self.assertFalse(r["answered"])
        self.assertFalse(r.get("notice"))


if __name__ == "__main__":
    unittest.main()
