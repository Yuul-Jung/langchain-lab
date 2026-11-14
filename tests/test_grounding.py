"""근거 대조 (서버·모델 없이 실행)."""
import unittest

import grounding


class GroundingTest(unittest.TestCase):
    def test_numbers_and_words_present_in_sources_pass(self):
        r = grounding.check("가점은 12,340점이고 Pass 기준입니다 [자료 1]", ["총 12340 점 ... pass 여부"])
        self.assertEqual((r["numbers"], r["words"]), ([], []))

    def test_missing_number_and_word_are_reported(self):
        r = grounding.check("가점은 99점이고 Kubernetes 를 씁니다", ["가점은 8점입니다", "docker"])
        self.assertEqual(r["numbers"], ["99"])
        self.assertEqual(r["words"], ["kubernetes"])

    def test_number_must_not_match_inside_a_longer_number(self):
        self.assertEqual(grounding.check("값은 8", ["값은 18, 3.85"])["numbers"], ["8"])
        self.assertEqual(grounding.check("값은 3.8", ["3.85"])["numbers"], ["3.8"])

    def test_number_after_a_dot_that_is_not_a_decimal_point(self):
        self.assertEqual(grounding.check("p.8 쪽", ["문서 p.8"])["numbers"], [])
        self.assertEqual(grounding.check("값은 5", ["값은 3.5"])["numbers"], ["5"])   # 3.5 의 5 는 다른 수

    def test_decimal_and_thousands_separator(self):
        r = grounding.check("3.5 와 1,200", ["x 3.5 y 1200 z"])
        self.assertEqual(r["numbers"], [])

    def test_citation_marks_and_list_numbers_are_ignored(self):
        r = grounding.check("1. 첫째 [자료 3]\n2) 둘째 [자료 12]", ["본문"])
        self.assertEqual(r["numbers"], [])

    def test_values_given_in_the_question_count_as_evidence(self):
        r = grounding.check("말씀하신 77 은", ["본문"], question="77 이 뭐야")
        self.assertEqual(r["numbers"], [])

    def test_empty_answer(self):
        self.assertEqual(grounding.check("", ["a"]), {"numbers": [], "words": [], "checked": 0})

    def test_a_wrong_use_of_a_number_that_exists_is_not_detected(self):
        # 알려진 한계: 근거에 있는 숫자면 엉뚱한 곳에 써도 통과한다
        self.assertEqual(grounding.check("가점은 5점", ["가점은 8점, 기본 5점"])["numbers"], [])


class SourceTextsTest(unittest.TestCase):
    def test_header_of_the_source_counts_as_evidence(self):
        src = [{"text": "본문", "filename": "교재_261103.pdf", "title": "사업", "page": 8}]
        r = grounding.check("[자료 1] (교재_261103.pdf · p.8)", grounding.source_texts(src))
        self.assertEqual((r["numbers"], r["words"]), ([], []))
        self.assertEqual(grounding.check("[자료 1] (교재_261103.pdf)", ["본문"])["numbers"], ["261103"])


if __name__ == "__main__":
    unittest.main()
