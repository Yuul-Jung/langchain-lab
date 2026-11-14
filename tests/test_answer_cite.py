"""출처 자동 표시 (서버·모델 없이 실행)."""
import unittest

import answer_cite as ac

SRC = [{"text": "시험용 사업 예산은 2025년 88,123억 원이다", "filename": "a.pdf", "page": 3},
       {"text": "완전히 다른 주제인 모터 과열 방지 설명", "filename": "a.pdf", "page": 8}]


class AnswerCiteTest(unittest.TestCase):
    def test_attribute_picks_overlapping_source(self):
        picked = ac.attribute("시험용 사업 예산은 2025년 88,123억 원입니다", SRC)
        self.assertEqual([i for i, _ in picked], [1])

    def test_no_overlap_means_no_citation(self):
        answer, info = ac.add_citations("xyz qwerty", SRC)
        self.assertEqual((answer, info["added"]), ("xyz qwerty", []))

    def test_valid_model_citation_is_kept_untouched(self):
        answer, info = ac.add_citations("예산 [자료 1]", SRC)
        self.assertEqual((answer, info["kept"]), ("예산 [자료 1]", True))

    def test_out_of_range_citation_is_removed_then_attributed(self):
        answer, info = ac.add_citations("시험용 사업 예산은 88,123억 원 [자료 7]", SRC)
        self.assertEqual(info["removed_bad"], 1)
        self.assertNotIn("[자료 7]", answer)
        self.assertIn("근거: [자료 1] (a.pdf · p.3)", answer)

    def test_no_sources_is_noop(self):
        self.assertEqual(ac.add_citations("답 [자료 1]", [])[0], "답 [자료 1]")

    def test_at_most_two_sources(self):
        many = [{"text": "같은 글 같은 글 같은 글", "filename": f"{i}.pdf", "page": 1} for i in range(5)]
        self.assertEqual(len(ac.attribute("같은 글 같은 글 같은 글", many)), 2)


if __name__ == "__main__":
    unittest.main()
