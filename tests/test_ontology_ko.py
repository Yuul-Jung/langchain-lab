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


class CaseSensitiveAcronymTest(unittest.TestCase):
    def names(self, text):
        g = og.build_graph(PARTS, min_cooccurrence=1)
        og.add_korean_bridge(g, [{"ko": ["캔 통신", "CAN 통신", "CAN"], "kw": ["regulator"]},
                                 {"ko": ["발광 다이오드", "LED"], "kw": ["led"]}])
        return [g.nodes[c]["label"] for c in og.translate_query(g, text, True)]

    def test_bare_acronym_needs_uppercase(self):
        self.assertEqual(self.names("can you recommend a part"), [])
        self.assertEqual(self.names("CAN 되는 칩 추천"), ["캔 통신"])

    def test_mixed_term_and_led_stay_case_insensitive(self):
        self.assertEqual(self.names("can 통신 칩 추천"), ["캔 통신"])
        self.assertEqual(self.names("led 추천"), ["발광 다이오드"])


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


class WikidataAuxTest(unittest.TestCase):
    def setUp(self):
        self.g = og.build_graph(PARTS, min_cooccurrence=1)
        og.add_korean_bridge(self.g, [{"ko": ["가젯 알파", "가젯 베타"], "kw": ["regulator"]}])

    def test_adds_support_but_never_changes_approval(self):
        rows = [{"term": "가젯 알파", "direction": "ko->en", "verdict": "match", "domain": "electronics", "qid": "Q1", "url": "u", "en_label": "gadget alpha"},
                {"term": "가젯 베타", "direction": "ko->en", "verdict": "match", "domain": "other", "qid": "Q2", "url": "u2", "en_label": "gadget beta"},
                {"term": "없는 말", "direction": "ko->en", "verdict": "match", "domain": "electronics", "qid": "Q3"},
                {"term": "가젯 알파", "direction": "en->ko", "verdict": "match", "domain": "electronics", "qid": "Q9"}]
        counts = og.attach_wikidata(self.g, rows)
        self.assertEqual(counts, {"electronics_match": 1, "other_domain": 1, "mismatch": 0})
        self.assertEqual(self.g.nodes["term:가젯 알파"]["wikidata_support"], "electronics_match")
        self.assertEqual(self.g.nodes["term:가젯 베타"]["wikidata_support"], "other_domain")
        c = self.g.nodes["concept:0"]
        self.assertEqual(c["wikidata_qids"], ["Q1"])                      # 분야 다른 것은 근거로 세지 않는다
        self.assertEqual(c["review_status"], "proposed")                 # 승인 대용이 아님
        self.assertIn("승인 대용이 아님", c["wikidata_note"])

    def test_not_found_rows_add_nothing(self):
        og.attach_wikidata(self.g, [{"term": "가젯 알파", "direction": "ko->en", "verdict": "not_found"}])
        self.assertNotIn("wikidata_qid", self.g.nodes["term:가젯 알파"])
        self.assertNotIn("wikidata_qids", self.g.nodes["concept:0"])


class ApprovalTest(unittest.TestCase):
    def setUp(self):
        self.g = og.build_graph(PARTS, min_cooccurrence=1)
        og.add_korean_bridge(self.g, [{"ko": ["가젯 알파"], "kw": ["regulator"]}, {"ko": ["가젯 베타", "베타칩"], "kw": ["regulator"]}])

    def names(self, text, include=False, skip=False):
        return [self.g.nodes[c]["label"] for c in og.translate_query(self.g, text, include, skip_risky=skip)]

    def test_approved_concepts_work_without_proposed_flag(self):
        counts = og.apply_approvals(self.g, [{"index": 0, "ko": "가젯 알파", "decision": "approved", "approver": "delegated: test"}])
        self.assertEqual(counts["approved"], 1)
        self.assertEqual(self.names("가젯 알파 추천"), ["가젯 알파"])
        self.assertEqual(self.g.nodes["concept:0"]["review_by"], "delegated: test")

    def test_rejected_is_never_used_even_with_proposed_flag(self):
        og.apply_approvals(self.g, [{"index": 1, "ko": "가젯 베타", "decision": "rejected"}])
        self.assertEqual(self.names("가젯 베타 추천", include=True), [])

    def test_index_and_label_mismatch_is_not_applied(self):
        counts = og.apply_approvals(self.g, [{"index": 0, "ko": "다른 이름", "decision": "approved"}])
        self.assertEqual(counts["mismatch"], 1)
        self.assertEqual(self.g.nodes["concept:0"]["review_status"], "proposed")

    def test_risky_terms_skipped_only_when_asked(self):
        og.apply_approvals(self.g, [{"index": 1, "ko": "가젯 베타", "decision": "approved", "risky_terms": ["베타칩"]}])
        self.assertEqual(self.names("베타칩 추천"), ["가젯 베타"])
        self.assertEqual(self.names("베타칩", skip=True), [])
        self.assertEqual(self.names("가젯 베타", skip=True), ["가젯 베타"])


if __name__ == "__main__":
    unittest.main()
