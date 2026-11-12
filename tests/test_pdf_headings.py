"""PDF 번호 제목 판별: 목차·번호 목록 줄을 제목으로 쓰지 않는지 (서버·PDF 파일 없이 실행)."""
import unittest

from document_pipeline import is_page_number_only, pdf_heading_lines


class PageNumberOnlyTest(unittest.TestCase):
    def test_page_number_fragment(self):
        self.assertTrue(is_page_number_only("21"))
        self.assertTrue(is_page_number_only("\n 21 \n"))

    def test_text_fragment_is_kept(self):
        self.assertFalse(is_page_number_only("21\n본문 문장"))
        self.assertFalse(is_page_number_only("2024년 계획"))
        self.assertFalse(is_page_number_only(""))


class PdfHeadingLinesTest(unittest.TestCase):
    def test_real_headings_with_body_are_kept(self):
        lines = ["1. 개요", "이 문서는 실습 절차를 설명한다.", "2. 준비", "필요한 장비를 확인한다."]
        headings, listed = pdf_heading_lines(lines)
        self.assertEqual(headings, [0, 2])
        self.assertEqual(listed, set())

    def test_table_of_contents_page_is_not_headings(self):
        lines = ["표지 문구", "Ⅰ. 개요", "1. 배경", "2. 구성", "3. 일정",
                 "Ⅱ. 실습", "1. 준비", "2. 측정", "2", "3. 정리"]
        headings, listed = pdf_heading_lines(lines)
        self.assertEqual(headings, [])
        self.assertEqual(listed, {2, 3, 4, 6, 7, 9})

    def test_numbered_list_in_body_is_not_headings(self):
        lines = ["2. 실습 목표", "목표는 다음과 같다.", "1. 회로를 이해한다.",
                 "2. 값을 측정한다.", "3. 결과를 비교한다.", "설명 문단이 이어진다."]
        headings, listed = pdf_heading_lines(lines)
        self.assertEqual(headings, [0])
        self.assertEqual(listed, {2, 3, 4})

    def test_heading_directly_followed_by_list_keeps_heading(self):
        lines = ["3. 확인 항목", "1. 입력을 확인한다.", "2. 출력을 확인한다.", "본문"]
        headings, listed = pdf_heading_lines(lines)
        self.assertEqual(headings, [0])
        self.assertEqual(listed, {1, 2})

    def test_single_numbered_line_stays_heading(self):
        headings, listed = pdf_heading_lines(["앞 본문", "12. 테스트 기준", "기준 설명"])
        self.assertEqual(headings, [1])
        self.assertEqual(listed, set())

    def test_too_many_separate_headings_are_dropped(self):
        lines = []
        for n in range(1, 15):
            lines += [f"{n}. 항목 제목", "본문 문장이 있다."]
        headings, _ = pdf_heading_lines(lines)
        self.assertEqual(headings, [])


if __name__ == "__main__":
    unittest.main()
