"""낱말 포함 재순위와 발췌 (서버·모델 없이 실행)."""
import unittest

from document_pipeline import (cosine_score, lexical_candidates_query, make_snippet,
                               matched_terms, merge_candidates, query_terms, rerank_by_terms,
                               term_credits)


class LexicalCandidatesTest(unittest.TestCase):
    def test_query_has_one_clause_per_word_with_stripped_forms(self):
        body = lexical_candidates_query("수수료는 QRS")
        clauses = body["bool"]["should"]
        self.assertEqual(len(clauses), 2)
        forms = [w["wildcard"]["text"]["value"] for w in clauses[0]["constant_score"]["filter"]["bool"]["should"]]
        self.assertEqual(forms, ["*수수료는*", "*수수료*", "*수수*"])
        self.assertEqual(body["bool"]["minimum_should_match"], 1)

    def test_no_usable_words_means_no_lexical_search(self):
        self.assertIsNone(lexical_candidates_query("? ! 가"))

    def test_wildcard_characters_cannot_be_injected(self):
        body = lexical_candidates_query("a*b?c\\d 가나*다")
        values = [w["wildcard"]["text"]["value"] for c in body["bool"]["should"]
                  for w in c["constant_score"]["filter"]["bool"]["should"]]
        for value in values:
            self.assertNotRegex(value[1:-1], r"[*?\\]")

    def test_document_filter_and_word_limit(self):
        body = lexical_candidates_query(" ".join(f"낱말{n}번" for n in range(40)), document_id="doc1")
        self.assertEqual(body["bool"]["filter"], [{"term": {"document_id": "doc1"}}])
        self.assertEqual(len(body["bool"]["should"]), 12)

    def test_cosine_score_matches_elasticsearch_formula(self):
        self.assertEqual(cosine_score([1, 0], [2, 0]), 1.0)
        self.assertEqual(cosine_score([1, 0], [0, 3]), 0.5)
        self.assertEqual(cosine_score([1, 0], [-1, 0]), 0.0)
        self.assertEqual(cosine_score([0, 0], [1, 0]), 0.0)

    def test_merge_keeps_vector_hits_and_adds_only_new_chunks(self):
        vector = [{"document_id": "a", "chunk_id": "s0001_c001", "score": 0.9}]
        lexical = [{"document_id": "a", "chunk_id": "s0001_c001", "score": 0.1},
                   {"document_id": "b", "chunk_id": "s0001_c001", "score": 0.6}]
        merged = merge_candidates(vector, lexical)
        # 청크 ID는 문서마다 같은 값이 반복되므로 문서 ID와 함께 비교해야 한다
        self.assertEqual([(h["document_id"], h["score"]) for h in merged], [("a", 0.9), ("b", 0.6)])

    def test_lexical_only_chunk_can_win_after_rerank(self):
        vector = [{"document_id": "a", "chunk_id": "c1", "score": 0.76, "text": "모델 생태계 설명"}]
        lexical = [{"document_id": "b", "chunk_id": "c1", "score": 0.66, "text": "정규분포: 평균과 표준편차"}]
        ranked = rerank_by_terms(merge_candidates(vector, lexical), "정규분포", 0.15)
        self.assertEqual(ranked[0]["document_id"], "b")


class QueryTermsTest(unittest.TestCase):
    def test_drops_short_words_question_words_and_duplicates(self):
        self.assertEqual(query_terms("QRS는 몇 묶음으로 어떻게 나뉘어? QRS는"), ["QRS", "묶음으로", "나뉘어"])

    def test_latin_and_hangul_are_split(self):
        self.assertEqual(query_terms("K700의 KEY, IN9"), ["K700", "KEY", "IN9"])

    def test_single_keyword(self):
        self.assertEqual(query_terms("산업안전"), ["산업안전"])


class MatchedTermsTest(unittest.TestCase):
    def test_ignores_spaces_and_case_in_text(self):
        self.assertEqual(matched_terms("sample folder", "Stub 은 Sample  Folder 에만"),
                         ["sample", "folder"])
        self.assertEqual(matched_terms("산업안전", "산업 안전 분야는"), ["산업안전"])

    def test_korean_particles_are_stripped(self):
        self.assertEqual(matched_terms("수수료는 보증료의", "수수료 비율은 보증료 10%"), ["수수료는", "보증료의"])

    def test_exact_word_scores_higher_than_stripped_match(self):
        self.assertEqual(term_credits("산업안전", "지역 산업 안전 교육"), {"산업안전": 1.0})
        self.assertEqual(term_credits("산업안전", "전통산업 및 첨단산업"), {"산업안전": 0.5})
        self.assertEqual(term_credits("수수료는", "수수료 비율"), {"수수료는": 0.5})

    def test_unrelated_text_matches_nothing(self):
        self.assertEqual(matched_terms("산업안전", "버튼 안전 표시 켜짐 꺼짐"), [])


class RerankTest(unittest.TestCase):
    hits = [
        {"page": 7, "score": 0.75, "text": "분야 예시 설비 점검 대응"},
        {"page": 15, "score": 0.71, "text": "버튼 안전 표시 켜짐"},
        {"page": 8, "score": 0.68, "text": "지역 산업안전 교육 일정"},
    ]

    def test_chunk_containing_the_keyword_moves_to_the_top(self):
        ranked = rerank_by_terms(self.hits, "산업안전", 0.10)
        self.assertEqual([h["page"] for h in ranked], [8, 7, 15])
        self.assertEqual((ranked[0]["vector_score"], ranked[0]["score"]), (0.68, 0.78))
        self.assertEqual(ranked[0]["matched_terms"], ["산업안전"])
        self.assertEqual(ranked[2]["term_coverage"], 0.0)

    def test_exact_keyword_beats_partial_match_with_higher_vector_score(self):
        hits = [{"page": 7, "score": 0.75, "text": "전통산업 및 첨단산업 지원"},
                {"page": 8, "score": 0.68, "text": "지역 산업안전 교육 일정"}]
        ranked = rerank_by_terms(hits, "산업안전", 0.15)
        self.assertEqual([(h["page"], h["score"]) for h in ranked], [(8, 0.83), (7, 0.825)])
        self.assertEqual([h["partial_terms"] for h in ranked], [[], ["산업안전"]])

    def test_zero_weight_keeps_vector_order(self):
        ranked = rerank_by_terms(self.hits, "산업안전", 0)
        self.assertEqual([h["page"] for h in ranked], [7, 15, 8])
        self.assertEqual(ranked[0]["score"], 0.75)

    def test_partial_coverage_gives_partial_bonus(self):
        ranked = rerank_by_terms([{"page": 1, "score": 0.5, "text": "수수료 비율"}], "수수료 보증료", 0.10)
        self.assertEqual((ranked[0]["term_coverage"], ranked[0]["score"]), (0.5, 0.55))
        ranked = rerank_by_terms([{"page": 1, "score": 0.5, "text": "수수료 비율"}], "수수료는", 0.10)
        self.assertEqual((ranked[0]["term_coverage"], ranked[0]["score"]), (0.5, 0.55))


class SnippetTest(unittest.TestCase):
    def test_short_text_is_returned_whole(self):
        self.assertEqual(make_snippet("짧은 본문", ["본문"]), "짧은 본문")

    def test_window_is_centered_on_the_match(self):
        text = "가" * 600 + " 산업 안전 교육 " + "나" * 600
        snippet = make_snippet(text, ["산업안전"], size=100)
        self.assertIn("산업 안전", snippet)
        self.assertTrue(snippet.startswith("… ") and snippet.endswith(" …"))
        self.assertLessEqual(len(snippet), 104)

    def test_no_match_shows_the_beginning(self):
        snippet = make_snippet("가" * 500, ["없는낱말"], size=100)
        self.assertTrue(snippet.startswith("가") and snippet.endswith(" …"))


if __name__ == "__main__":
    unittest.main()
