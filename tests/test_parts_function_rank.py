import unittest

import networkx as nx

import ontology_graph as og
import parts_graph as pg
import parts_taxonomy as pt

TAX = {
    "domains": [{"id": "logic", "ko": "디지털 로직", "en": "Logic"}, {"id": "electromech", "ko": "전기기계", "en": "Electromech"}],
    "functions": [
        {"id": "gates", "domain": "logic", "ko": "게이트·인버터", "en": "Gates", "kind": "ic"},
        {"id": "logic_buffer", "domain": "logic", "ko": "로직 버퍼·트랜시버", "en": "Logic buffers", "kind": "ic"},
        {"id": "counters", "domain": "logic", "ko": "카운터·분주기", "en": "Counters", "kind": "ic"},
        {"id": "thermal", "domain": "electromech", "ko": "열 관리", "en": "Thermal management", "kind": "mechanical"},
        {"id": "motor", "domain": "electromech", "ko": "모터", "en": "Motors", "kind": "electromech"},
    ],
    "libraries": {
        "Logic74": {"function": "gates", "status": "confirmed", "mixed": True, "also_functions": ["logic_buffer", "counters"], "also_ok": []},
        "Motor": {"function": "motor", "status": "confirmed", "mixed": True, "also_functions": ["thermal"], "also_ok": [],
                  "part_rules": {"Fan": {"function": "thermal", "ko": "냉각 팬"}}},
    },
    "generic": {},
    "function_evidence": {"gates": r"nand|\bgate\b|inverter", "logic_buffer": r"buffer|line driver", "counters": r"counter|flip-?flop"},
}
CAT = [
    {"lib_id": "Logic74:7400", "library": "Logic74", "name": "7400", "description": "quad 2-input NAND gate", "keywords": "", "pin_count": 14},
    {"lib_id": "Logic74:74240", "library": "Logic74", "name": "74240", "description": "Octal buffer and line driver", "keywords": "", "pin_count": 20},
    {"lib_id": "Logic74:74192", "library": "Logic74", "name": "74192", "description": "4-bit up/down counter", "keywords": "", "pin_count": 16},
    {"lib_id": "Motor:Fan_3pin", "library": "Motor", "name": "Fan_3pin", "description": "Fan", "keywords": "", "pin_count": 3},
    {"lib_id": "Motor:Motor_DC", "library": "Motor", "name": "Motor_DC", "description": "DC motor", "keywords": "", "pin_count": 2},
]


def onto():
    g = nx.Graph()
    g.add_node("lib:Logic74", kind="library", label="Logic74")
    og.add_korean_bridge(g, [{"ko": ["로직 칩"], "lib": ["Logic74"], "review_status": "approved"}])
    return g


def run(q, rank=True, rows=None, tax=None, limit=5):
    d = pg.PartsDeps(find=lambda query, n: ((rows if rows is not None else CAT)[:n], "es-semantic"), ontology=onto(), catalog=CAT,
                     taxonomy=pt.Taxonomy(tax or TAX), function_rank=rank, limit=limit)
    return pg.ask_parts(pg.build_parts_graph(d), q)


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        self.t = pt.Taxonomy(TAX)

    def test_description_evidence_picks_function_inside_mixed_library(self):
        c = lambda n, d: self.t.classify("Logic74", n, d)["function"]
        self.assertEqual(c("7400", "quad 2-input nand gate"), "gates")
        self.assertEqual(c("74240", "octal buffer and line driver"), "logic_buffer")
        self.assertEqual(c("74192", "4-bit up/down counter"), "counters")
        self.assertEqual(c("7499", "mystery part"), "gates")                       # 증거가 없으면 대표 기능
        self.assertEqual(self.t.classify("Motor", "Fan_3pin", "")["function"], "thermal")   # 이름 규칙이 먼저
        self.assertIsNone(self.t.classify("Unknown", "x"))

    def test_question_functions_use_only_taxonomy_words(self):
        self.assertEqual(self.t.question_functions("냉각 팬 부품 추천"), ["thermal"])
        self.assertEqual(self.t.question_functions("카운터 칩"), ["counters"])
        self.assertEqual(self.t.question_functions("오늘 날씨"), [])
        self.assertEqual(self.t.targets("buffer 74xx", ["Logic74"]), {"logic_buffer"})

    def test_label_shows_domain_function_kind_and_mixed(self):
        i = self.t.classify("Logic74", "7400", "quad 2-input nand gate")
        self.assertEqual(self.t.label(i), "디지털 로직 › 게이트·인버터 · IC · 혼합 라이브러리")


class GraphTest(unittest.TestCase):
    def test_function_name_finds_parts_the_ontology_does_not_know(self):
        r = run("냉각 팬 있어")                                    # 부품 명사가 없어 원래는 답이 없던 질문: 기능 부품이 첫머리
        self.assertTrue(r["answered"])
        self.assertEqual([p["name"] for p in r["parts"]], ["Fan_3pin"])
        self.assertIn("분류: 전기기계 › 열 관리 · 기구 · 혼합 라이브러리", r["answer"])
        self.assertEqual(r["functions"], ["thermal"])

    def test_questions_the_baseline_already_answered_keep_their_top_results(self):
        r = run("냉각 팬 부품 추천")                               # 짧은 부품 질문이라 원래도 답이 나옴 → 원래 앞쪽 결과를 지키고 기능 부품을 뒤에 더한다
        names = [p["name"] for p in r["parts"]]
        self.assertEqual(names[:3], ["7400", "74240", "74192"])
        self.assertIn("Fan_3pin", names)

    def test_catalog_fills_in_when_search_misses_the_function(self):
        r = run("카운터 있어", rows=[CAT[0], CAT[3]])             # 검색 결과에 카운터가 없음
        self.assertEqual([p["name"] for p in r["parts"]], ["74192"])

    def test_known_concepts_keep_their_order_and_only_gain_labels(self):
        # 개념 사전 길의 순서는 바꾸지 않는다(상위 결과에 기능 부품을 끼워 넣는 시도는 이미 본 세트에서 정답을 깎아 뺐다)
        rows = [CAT[0], CAT[2], CAT[1]]
        r = run("로직 칩 buffer 부품 추천", rows=rows, limit=2)
        self.assertEqual([p["name"] for p in r["parts"]], ["7400", "74192"])
        self.assertIn("분류:", r["answer"])

    def test_bare_phrase_needs_every_content_word_covered(self):
        t = pt.Taxonomy(TAX)
        self.assertTrue(t.phrase_covered("냉각 팬"))                  # 규칙의 한국어 이름 통째로
        self.assertTrue(t.phrase_covered("카운터 칩"))                 # 칩은 중립어
        self.assertFalse(t.phrase_covered("전기 자전거 카운터"))         # 덮이지 않는 낱말('전기', '자전거')
        self.assertFalse(t.phrase_covered("카운터 직원 월급 얼마나 받아"))  # 4낱말을 넘음
        self.assertFalse(t.phrase_covered("오늘 날씨"))
        self.assertTrue(pg.function_gate("냉각 팬", t))
        self.assertFalse(pg.function_gate("냉각 팬 소음", t))             # 소음 이 덮이지 않음
        self.assertFalse(pg.function_gate("냉각 팬", None))               # 분류 체계가 없으면 INTENT 만

    def test_bare_phrase_is_answered_only_with_the_flag(self):
        self.assertTrue(run("냉각 팬")["answered"])
        self.assertFalse(run("냉각 팬", rank=False)["answered"])
        self.assertFalse(run("냉각 팬 소음")["answered"])

    def test_cross_domain_word_is_resolved_by_the_other_words(self):
        tax = {**TAX, "domains": TAX["domains"] + [{"id": "power", "ko": "전원", "en": "Power"}],
               "functions": TAX["functions"] + [{"id": "gate_driver", "domain": "power", "ko": "게이트 드라이버", "en": "Gate drivers", "kind": "ic"}]}
        t = pt.Taxonomy(tax)
        self.assertEqual(t.question_functions("게이트"), [])                       # 로직 게이트와 전원 게이트 드라이버 사이 모호
        self.assertEqual(t.question_functions("게이트 인버터"), ["gates"])         # 인버터가 로직 도메인을 가리켜 풀린다
        self.assertTrue(t.phrase_covered("게이트 인버터"))
        self.assertEqual(t.question_functions("게이트 드라이버"), ["gate_driver"])

    def test_alias_rules_block_compound_and_cross_domain_words(self):
        t = pt.Taxonomy(TAX)
        self.assertEqual(t.question_functions("색카운터 칩"), [])                  # 앞에 다른 한글이 붙은 낱말
        self.assertEqual(t.question_functions("카운터 모터 있어"), [])             # 서로 다른 도메인의 기능이 함께 걸림
        self.assertEqual(t.question_functions("카운터 칩"), ["counters"])

    def test_flag_off_or_missing_taxonomy_changes_nothing(self):
        self.assertTrue(run("냉각 팬 있어", rank=True)["answered"])
        self.assertFalse(run("냉각 팬 있어", rank=False)["answered"])               # 부품 명사가 없어 기존 보조 관문도 안 탄다
        r = run("로직 칩 부품 추천", rank=False)
        self.assertNotIn("분류:", r["answer"])
        d = pg.PartsDeps(find=lambda q, n: (CAT, "es-semantic"), ontology=onto(), catalog=CAT, taxonomy=None, function_rank=True)
        self.assertNotIn("분류:", pg.ask_parts(pg.build_parts_graph(d), "로직 칩 부품 추천")["answer"])

    def test_gate_keeps_explanations_and_documents_out(self):
        for q in ["카운터 원리 설명해줘", "카운터 구현 방법", "올린 문서에서 카운터 알려줘"]:
            self.assertFalse(run(q)["answered"], q)


if __name__ == "__main__":
    unittest.main()
