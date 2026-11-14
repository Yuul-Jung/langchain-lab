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


class ShortKoreanTermTest(unittest.TestCase):
    def names(self, text):
        g = og.build_graph(PARTS, min_cooccurrence=1)
        og.add_korean_bridge(g, [{"ko": ["램"], "kw": ["regulator"]}])
        return [g.nodes[c]["label"] for c in og.translate_query(g, text, True)]

    def test_one_syllable_term_not_inside_longer_word(self):
        self.assertEqual(self.names("프로그램 추천해줘"), [])
        self.assertEqual(self.names("램프 추천해줘"), [])

    def test_one_syllable_term_alone_or_with_particle(self):
        self.assertEqual(self.names("램 추천해줘"), ["램"])
        self.assertEqual(self.names("램을 추천해줘"), ["램"])
        self.assertEqual(self.names("메모리 램으로 추천해줘"), ["램"])


class SemanticConceptTest(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np
        self.g = og.build_graph(PARTS, min_cooccurrence=1)
        og.add_korean_bridge(self.g, [{"ko": ["가젯 알파"], "kw": ["regulator"]}])
        self.vecs = {"nodes": ["term:가젯 알파"], "mat": np.array([[1.0, 0.0]], dtype=np.float32)}

    def find(self, vec, **kw):
        return og.semantic_concepts(self.g, "아무 문구", lambda t: vec, self.vecs, include_proposed=True, **kw)

    def test_close_paraphrase_is_found(self):
        self.assertEqual([self.g.nodes[c]["label"] for c in self.find([0.8, 0.6])], ["가젯 알파"])

    def test_below_threshold_finds_nothing(self):
        self.assertEqual(self.find([0.6, 0.8]), [])

    def test_embedding_failure_finds_nothing(self):
        def boom(t):
            raise RuntimeError("down")
        self.assertEqual(og.semantic_concepts(self.g, "x", boom, self.vecs, include_proposed=True), [])

    def test_proposed_concepts_need_flag(self):
        self.assertEqual(og.semantic_concepts(self.g, "x", lambda t: [1.0, 0.0], self.vecs), [])

    def test_mismatched_vector_size_finds_nothing(self):
        self.assertEqual(og.semantic_concepts(self.g, "x", lambda t: [1.0], self.vecs, include_proposed=True), [])

    def test_missing_vecs_file_is_none(self):
        self.assertIsNone(og.load_term_vecs("/no/such/term_vecs.npz"))


if __name__ == "__main__":
    unittest.main()
