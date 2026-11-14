"""한·영 다리 (카탈로그 없이 작은 가짜 그래프로)."""
import unittest

import ontology_graph as og

PARTS = [
    {"lib_id": "Regulator_Linear:A", "library": "Regulator_Linear", "name": "A", "description": "d",
     "keywords": "ldo regulator", "footprint": "", "datasheet": "http://x", "extends": "", "pin_count": 5},
    {"lib_id": "Regulator_Linear:B", "library": "Regulator_Linear", "name": "B", "description": "",
     "keywords": "linear regulator", "footprint": "", "datasheet": "", "extends": "", "pin_count": 3},
    {"lib_id": "LED:L1", "library": "LED", "name": "L1", "description": "", "keywords": "led",
     "footprint": "", "datasheet": "", "extends": "", "pin_count": 2},
]
ENTRIES = [
    {"ko": ["저전압 강하 레귤레이터", "LDO"], "kw": ["ldo", "regulator"], "lib": ["Regulator_Linear"]},
    {"ko": ["발광 다이오드", "LED"], "kw": ["led"], "lib": ["LED"]},
    {"ko": ["없는 부품"], "kw": ["nothing"], "lib": ["Nowhere"]},
]


def graph(status="proposed"):
    g = og.build_graph(PARTS, min_cooccurrence=1)
    og.add_korean_bridge(g, [dict(e, review_status=status) for e in ENTRIES])
    return g


class KoreanBridgeTest(unittest.TestCase):
    def test_proposed_concepts_are_hidden_by_default(self):
        self.assertEqual(og.translate_query(graph(), "저전압 강하 레귤레이터 찾아줘"), [])
        self.assertEqual(og.ask_ko(graph(), "저전압 강하 레귤레이터 찾아줘"), [])

    def test_approved_concepts_are_used(self):
        r = og.ask_ko(graph("approved"), "저전압 강하 레귤레이터 찾아줘")
        self.assertEqual(r[0]["concept"], "저전압 강하 레귤레이터")
        self.assertEqual([p["lib_id"] for p in r[0]["parts"]], ["Regulator_Linear:A"])  # ldo+regulator 를 모두 가진 부품만

    def test_spacing_and_particles_do_not_block_match(self):
        self.assertTrue(og.translate_query(graph(), "저전압강하레귤레이터는", include_proposed=True))

    def test_ascii_terms_need_word_boundaries(self):
        self.assertEqual(og.translate_query(graph(), "called", include_proposed=True), [])
        self.assertTrue(og.translate_query(graph(), "LED 켜기", include_proposed=True))

    def test_longest_term_wins_over_overlapping_shorter_one(self):
        g = og.build_graph(PARTS, min_cooccurrence=1)
        og.add_korean_bridge(g, [{"ko": ["레귤레이터"], "kw": ["regulator"]},
                                 {"ko": ["저전압 강하 레귤레이터"], "kw": ["ldo"]}])
        names = [g.nodes[c]["label"] for c in og.translate_query(g, "저전압 강하 레귤레이터", True)]
        self.assertEqual(names, ["저전압 강하 레귤레이터"])

    def test_unrelated_question_matches_nothing(self):
        self.assertEqual(og.ask_ko(graph("approved"), "시험용 사업 예산은 얼마야"), [])

    def test_entry_with_missing_targets_has_no_parts(self):
        r = og.ask_ko(graph("approved"), "없는 부품")
        self.assertEqual(r[0]["parts"], [])


if __name__ == "__main__":
    unittest.main()
