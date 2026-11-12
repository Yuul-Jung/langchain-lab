"""PDF 번호 제목 판별: 목차·번호 목록 줄을 제목으로 쓰지 않는지 (서버·PDF 파일 없이 실행)."""
import unittest

from document_pipeline import pdf_heading_lines


class PdfHeadingLinesTest(unittest.TestCase):
    def test_real_headings_with_body_are_kept(self):
        lines = ["1. 개요", "이 문서는 실습 절차를 설명한다.", "2. 준비", "필요한 장비를 확인한다."]
        headings, listed = pdf_heading_lines(lines)
        self.assertEqual(headings, [0, 2])
        self.assertEqual(listed, set())

    def test_table_of_contents_page_is_not_headings(self):
        lines = ["표지 기관명", "Ⅰ. 사업 소개", "1. 개요", "2. 세부 내용", "3. 신청 절차",
                 "Ⅱ. 평가 체계", "1. 평가 절차", "2. 사전 검토", "2", "3. 선정 평가"]
        headings, listed = pdf_heading_lines(lines)
        self.assertEqual(headings, [])
        self.assertEqual(listed, {2, 3, 4, 6, 7, 9})

    def test_numbered_list_in_body_is_not_headings(self):
        lines = ["2. 과제 목적", "목적은 다음과 같다.", "1. 구조를 이해한다.",
                 "2. 값을 판단한다.", "3. 표시를 결합한다.", "설명 문단이 이어진다."]
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
