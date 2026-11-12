"""추출 적대적 검증: 추출을 깨뜨리려는 입력 모음 (서버·실제 문서 없이 실행, 2026-11-12).

각 테스트 이름과 주석에 '무엇을 깨뜨리려는 입력인지' 적는다.
- 버그였던 것: 고친 뒤 올바른 동작을 고정한다 (주석에 '수정 전' 동작 기록).
- 알려진 한계: 고치지 않은 동작을 그대로 기록한다. 이름이 test_limit_ 로 시작한다.
  한계를 고치면 이 테스트가 실패하므로, 그때 기대값을 바꾼다.
"""
import random
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import document_pipeline as dp
from document_pipeline import (_split_text, is_page_number_only, make_chunks,
                               pdf_heading_lines, repair_broken_spaces)


def parse_pages(*texts):
    """가짜 PDF 쪽 텍스트로 _parse_pdf 실행."""
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        is_encrypted = False
        pages = [Page(t) for t in texts]

    with patch.object(dp, "PdfReader", return_value=Reader()):
        return dp._parse_pdf(Path("input.pdf"))


def titles(sections):
    return [s["title"] for s in sections]


class HeadingAdversarialTest(unittest.TestCase):
    """A. 제목 판별을 속이려는 줄."""

    def headings(self, lines):
        return pdf_heading_lines(lines)[0]

    def test_a01_empty_and_blank_input(self):
        self.assertEqual(pdf_heading_lines([]), ([], set()))
        self.assertEqual(pdf_heading_lines(["", "  ", "\t"]), ([], set()))

    def test_a02_date_line_is_not_a_heading(self):
        # 수정 전: '11. 5.(목) 10:00 모임' 같은 날짜 줄이 제목으로 잡혔다
        self.assertEqual(self.headings(["11. 5.(목) 10:00 모임", "장소 안내"]), [])
        self.assertEqual(self.headings(["2026. 11. 3. 회의", "본문"]), [])

    def test_a03_number_then_digits_that_are_not_a_date_still_heading(self):
        self.assertEqual(self.headings(["3. 3상 전원 연결", "본문"]), [0])

    def test_a04_decimal_values_are_not_headings(self):
        self.assertEqual(self.headings(["3.3V 전원을 쓴다", "1.5 V 이하", "본문"]), [])

    def test_a05_heading_without_space_after_dot(self):
        # 수정 전: '1.개요'는 제목으로 보지 못했다
        self.assertEqual(self.headings(["1.개요", "본문", "2.준비", "본문"]), [0, 2])

    def test_a06_heading_numbered_one_followed_by_list_from_one(self):
        # 수정 전: 제목 '1. 개요'까지 목록으로 처리되어 제목이 사라졌다
        headings, listed = pdf_heading_lines(["1. 개요", "1. 첫째 항목", "2. 둘째 항목", "본문"])
        self.assertEqual((headings, listed), ([0], {1, 2}))

    def test_a07_table_of_contents_restart_is_not_mistaken_for_heading_plus_list(self):
        # 목차는 1,2,3 뒤에 다시 1,2 가 온다. 첫 줄을 제목으로 남기면 안 된다.
        headings, listed = pdf_heading_lines(["1. 배경", "2. 구성", "3. 일정", "1. 준비", "2. 측정"])
        self.assertEqual((headings, listed), ([], {0, 1, 2, 3, 4}))

    def test_a08_two_ones_in_a_row_without_a_two_is_a_list(self):
        self.assertEqual(self.headings(["1. 항목 가", "1. 항목 나", "본문"]), [])

    def test_a09_sentence_ending_with_period_is_not_a_heading(self):
        # 수정 전: 문장형 번호 줄 하나가 제목으로 잡혔다
        self.assertEqual(self.headings(["설명", "1. 이것은 목록의 유일한 항목이다.", "다음 문단"]), [])
        self.assertEqual(self.headings(["1. 구조를 이해한다 .", "2. 값을 판단한다 .", "본문"]), [])

    def test_a10_numbered_table_rows_are_not_headings(self):
        self.assertEqual(self.headings(["표", "1. 1 0x0A 0x011", "2. 1 0x0A 0x022", "3. 1 0x0A 0x033"]), [])

    def test_a11_length_boundary_65_and_66(self):
        self.assertEqual(self.headings(["1. " + "가" * 65, "본문"]), [0])
        self.assertEqual(self.headings(["1. " + "가" * 66, "본문"]), [])

    def test_a12_chapter_and_section_words(self):
        self.assertEqual(self.headings(["제 3 장 통신", "본문", "제2절 수신", "본문"]), [0, 2])

    def test_a13_fullwidth_space_tabs_and_trailing_space(self):
        self.assertEqual(self.headings(["1.　개요", "본문", "  2.   준비  \t", "본문"]), [0, 2])

    def test_a14_numbers_out_of_range(self):
        self.assertEqual(self.headings(["100. 항목", "본문", "0. 서론", "본문"]), [])

    def test_a15_other_numbering_styles_are_left_alone(self):
        self.assertEqual(self.headings(["1) 개요", "(1) 개요", "① 개요", "1.1 개요", "1-1. 배경", "본문"]), [])

    def test_a16_english_headings(self):
        self.assertEqual(self.headings(["1. Introduction", "body", "2. Method", "body"]), [0, 2])

    def test_limit_a17_heading_at_page_end_has_no_body(self):
        # 한계: 쪽 맨 끝의 제목은 본문이 다음 쪽에 있어도 제목만 있는 절이 된다
        self.assertEqual(self.headings(["앞 본문", "3. 마지막 제목"]), [1])

    def test_limit_a18_more_than_twelve_real_headings_are_all_dropped(self):
        # 한계(기존 설계): 한 쪽에 제목 후보가 13개 이상이면 표로 보고 전부 제외한다
        lines = sum(([f"{n}. 제목 {n}", "본문"] for n in range(1, 14)), [])
        self.assertEqual(self.headings(lines), [])

    def test_limit_a19_only_page_number_between_two_headings(self):
        # 한계: 제목 둘 사이에 쪽 번호만 있으면 목차로 본다 (첫 제목에 본문이 없는 경우)
        self.assertEqual(self.headings(["1. 개요", "3", "2. 내용", "본문"]), [])


class PageSplitAdversarialTest(unittest.TestCase):
    """B. 쪽 분할을 깨뜨리려는 쪽."""

    def test_b01_empty_whitespace_and_none_pages_are_skipped(self):
        sections = parse_pages("", "   ", None, "본문만 있는 쪽이다")
        self.assertEqual([(s["title"], s["page"]) for s in sections], [("PDF 4쪽 · 본문만 있는 쪽이다", 4)])

    def test_b02_page_with_only_a_page_number_yields_nothing(self):
        self.assertEqual(parse_pages("42"), [])

    def test_b03_page_number_plus_short_lead_is_attached_to_heading(self):
        sections = parse_pages("21\n쪽 제목\n1. 개요\n본문 내용")
        self.assertEqual([(s["title"], s["text"]) for s in sections],
                         [("1. 개요", "21\n쪽 제목\n1. 개요\n본문 내용")])

    def test_b04_lead_boundary_79_and_80_characters(self):
        self.assertEqual(titles(parse_pages("가" * 79 + "\n1. 개요\n본문")), ["1. 개요"])
        self.assertEqual(titles(parse_pages("가" * 80 + "\n1. 개요\n본문")), ["PDF 1쪽", "1. 개요"])

    def test_b05_short_lead_is_not_carried_to_the_next_page(self):
        # 머리 줄을 붙일 절이 같은 쪽에 없으면 그대로 한 절로 남고, 다음 쪽으로 넘어가지 않는다
        sections = parse_pages("짧은 쪽", "1. 개요\n본문")
        self.assertEqual([(s["title"], s["text"]) for s in sections],
                         [("PDF 1쪽 · 짧은 쪽", "짧은 쪽"), ("1. 개요", "1. 개요\n본문")])

    def test_b06_table_of_contents_page_is_one_section(self):
        sections = parse_pages("표지\nⅠ. 개요\n1. 배경\n2. 구성\n3. 일정\nⅡ. 실습\n1. 준비\n2. 측정")
        self.assertEqual(titles(sections), ["PDF 1쪽 (목차)"])

    def test_b07_too_many_sections_is_refused_not_truncated(self):
        with patch.object(dp, "MAX_SECTIONS", 150), self.assertRaises(ValueError):
            parse_pages(*[f"{(n % 9) + 1}. 제목\n본문 {n}" for n in range(151)])

    def test_b07b_slide_deck_of_183_pages_is_accepted_by_default(self):
        # 수정 전: 절 한도 150 때문에 183쪽 슬라이드형 PDF가 업로드 거절됐다
        sections = parse_pages(*[f"슬라이드 {n} 제목\n설명 문장" for n in range(183)])
        self.assertEqual(len(sections), 183)
        self.assertEqual(len(make_chunks(sections)), 183)

    def test_b08_crlf_line_endings(self):
        sections = parse_pages("머리\r\n1. 개요\r\n본문\r\n")
        self.assertEqual([(s["title"], s["text"]) for s in sections], [("1. 개요", "머리\n1. 개요\n본문")])

    def test_b09_control_characters_are_replaced_by_spaces(self):
        # 수정 전: NUL이 색인 본문에 그대로 남았다 (글꼴이 변환하지 못한 ':' '-' 자리, 예: 'data[7:0]' → '[7␀0]')
        sections = parse_pages("1. 개요\ndata[7\x000] 값\x0c다음 AB\x00CD")
        self.assertEqual(sections[0]["text"], "1. 개요\ndata[7 0] 값 다음 AB CD")
        self.assertFalse(re.search("[\x00-\x08\x0b\x0c\x0e-\x1f]", sections[0]["text"]))

    def test_b10_encrypted_pdf_is_refused(self):
        class Reader:
            is_encrypted = True
            pages = []

        with patch.object(dp, "PdfReader", return_value=Reader()), self.assertRaises(ValueError):
            dp._parse_pdf(Path("input.pdf"))

    def test_b11_page_numbers_and_order_are_kept(self):
        sections = parse_pages("1. 가\n본문 가", "", "2. 나\n본문 나")
        self.assertEqual([(s["page"], s["source_order"]) for s in sections], [(1, 1), (3, 2)])

    def test_limit_b12_a_bare_year_line_is_dropped_as_a_page_number(self):
        # 한계: 숫자만 있는 4자리 이하 줄은 쪽 번호로 본다. 연도만 적힌 머리 줄도 사라진다.
        self.assertTrue(is_page_number_only("2026"))
        self.assertEqual(parse_pages("2026\n1. 개요\n본문 내용")[0]["text"], "1. 개요\n본문 내용")

    def test_b13_five_digit_number_is_not_a_page_number(self):
        self.assertFalse(is_page_number_only("12345"))

    def test_b14_random_pages_never_lose_or_reorder_lines(self):
        # 무작위 쪽 400개: 쪽 번호만 있는 조각 말고는 원문 줄이 빠지거나 순서가 바뀌면 안 된다
        pool = ["본문 문장이다.", "1. 개요", "2. 준비", "3. 확인", "12. 긴 번호", "Ⅱ. 부 제목", "7", "", "  ",
                "표 1 2 3", "제 2 장 통신", "1.5 V", "→ n023", "가" * 90, "1.개요", "11. 5.(목) 모임",
                "1. 문장으로 끝난다."]
        rng = random.Random(20261112)
        for trial in range(400):
            lines = [rng.choice(pool) for _ in range(rng.randint(1, 16))]
            want = [l.strip() for l in "\n".join(lines).strip().splitlines() if l.strip()]
            got = [l.strip() for s in parse_pages("\n".join(lines)) for l in s["text"].splitlines() if l.strip()]
            index = 0
            for line in want:
                if index < len(got) and got[index] == line:
                    index += 1
                else:
                    self.assertRegex(line, r"^\d{1,4}$", f"시도 {trial}: 줄이 사라짐 {line!r} / 입력 {lines}")
            self.assertEqual(index, len(got), f"시도 {trial}: 없던 줄이 생김 / 입력 {lines}")


class PageTitleAdversarialTest(unittest.TestCase):
    """F. 번호형 제목이 없는 쪽(슬라이드)의 제목: 첫 줄을 제목으로 쓸지."""

    def test_f01_slide_pages_get_their_first_line_as_title(self):
        sections = parse_pages("실습 준비 순서\n도구를 점검하고 자리를 정한다", "측정값은 어떻게 읽을까?\n눈금과 단위를 함께 본다")
        self.assertEqual(titles(sections), ["PDF 1쪽 · 실습 준비 순서", "PDF 2쪽 · 측정값은 어떻게 읽을까?"])

    def test_f02_text_is_not_changed_by_the_title(self):
        sections = parse_pages("슬라이드 제목\n본문 첫 줄\n본문 둘째 줄")
        self.assertEqual(sections[0]["text"], "슬라이드 제목\n본문 첫 줄\n본문 둘째 줄")

    def test_f03_running_header_repeated_on_many_pages_is_not_a_title(self):
        pages = [f"실습 교재 2026 · {n}\n{n}번째 쪽의 본문이다" for n in range(1, 6)]
        self.assertEqual(titles(parse_pages(*pages)), [f"PDF {n}쪽" for n in range(1, 6)])

    def test_f04_header_repeated_on_only_two_pages_is_still_used(self):
        sections = parse_pages("같은 제목\n본문 가", "같은 제목\n본문 나", "다른 제목\n본문 다")
        self.assertEqual(titles(sections)[0], "PDF 1쪽 · 같은 제목")

    def test_f05_too_short_too_long_or_numeric_first_lines_are_not_titles(self):
        self.assertEqual(dp.page_title(3, "가나"), "PDF 3쪽")
        self.assertEqual(dp.page_title(3, "가" * 46), "PDF 3쪽")
        self.assertEqual(dp.page_title(3, "가" * 45), "PDF 3쪽 · " + "가" * 45)
        self.assertEqual(dp.page_title(3, "12 / 34"), "PDF 3쪽")
        self.assertEqual(dp.page_title(3, "  여백이   있는  제목 "), "PDF 3쪽 · 여백이 있는 제목")

    def test_f06_contents_page_and_numbered_headings_keep_their_titles(self):
        toc = parse_pages("표지\nⅠ. 개요\n1. 배경\n2. 구성\n3. 일정\nⅡ. 실습\n1. 준비\n2. 측정")
        self.assertEqual(titles(toc), ["PDF 1쪽 (목차)"])
        headed = parse_pages("1. 개요\n본문 내용이다")
        self.assertEqual(titles(headed), ["1. 개요"])

    def test_f07_long_lead_before_a_heading_gets_a_title_only_if_its_first_line_fits(self):
        lead = "첫 줄은 짧다\n" + "둘째 줄은 아주 길어서 머리 조각 전체가 80자를 넘는다. " * 3
        sections = parse_pages(lead.strip() + "\n1. 개요\n본문")
        self.assertEqual(titles(sections), ["PDF 1쪽 · 첫 줄은 짧다", "1. 개요"])

    def test_f08_repeated_header_detection_ignores_page_numbers_in_it(self):
        repeated = dp.repeated_first_lines([f"강의 자료 {n}쪽\n본문" for n in range(1, 5)] + ["표지\n본문"])
        self.assertEqual(repeated, {"강의 자료 #쪽"})


class BrokenSpaceAdversarialTest(unittest.TestCase):
    """D. 깨진 공백 복원이 정상 글자를 건드리게 하려는 입력."""

    def test_d01_real_broken_spaces_are_repaired(self):
        text = "개발堺환경堺설정堺방법堺안내堺문서堺입니다\n" * 5
        fixed, glyphs = repair_broken_spaces([text])
        self.assertEqual(glyphs, {"堺"})
        self.assertIn("개발 환경 설정 방법 안내 문서 입니다", fixed[0])

    def test_d02_real_hanja_between_hangul_in_a_long_document_is_kept(self):
        # 수정 전: '한美동맹'이 5회 나오면 '美'를 공백으로 지웠다 (원문 훼손)
        text = "한美동맹 " * 5 + "본문 문장입니다 " * 300
        fixed, glyphs = repair_broken_spaces([text])
        self.assertEqual((glyphs, fixed[0]), (set(), text))

    def test_d03_real_hanja_repeated_in_a_short_document_is_kept(self):
        # 수정 전: '서울大학교' 6회짜리 짧은 문서에서 '大'가 지워졌다
        text = "서울大학교 " * 6
        self.assertEqual(repair_broken_spaces([text]), ([text], set()))

    def test_d04_hanja_used_twenty_times_but_rarely_relative_to_text_is_kept(self):
        text = "한美동맹 " * 20 + "본문 문장입니다 " * 600
        self.assertEqual(repair_broken_spaces([text])[1], set())

    def test_d05_two_different_broken_glyphs(self):
        fixed, glyphs = repair_broken_spaces(["가堺나堺다堺라堺마堺바\n" * 5, "가碍나碍다碍라碍마碍바\n" * 5])
        self.assertEqual(glyphs, {"堺", "碍"})
        self.assertNotRegex("".join(fixed), "[堺碍]")

    def test_d06_hanja_at_line_edges_is_kept(self):
        text = "堺가나다\n라마바堺\n" * 12
        self.assertEqual(repair_broken_spaces([text])[1], set())

    def test_d07_empty_inputs(self):
        self.assertEqual(repair_broken_spaces([]), ([], set()))
        self.assertEqual(repair_broken_spaces(["", ""]), (["", ""], set()))

    def test_limit_d08_few_broken_spaces_in_a_tiny_document_are_not_repaired(self):
        # 한계: 진짜 한자를 지키는 대가로, 깨진 공백이 20회 미만인 아주 짧은 문서는 복원하지 않는다
        text = "개발堺환경堺설정"
        self.assertEqual(repair_broken_spaces([text]), ([text], set()))


class ChunkAdversarialTest(unittest.TestCase):
    """E. 청크 분할이 글자를 잃게 하려는 입력. 모든 글자가 고유해 위치를 정확히 확인한다."""

    @staticmethod
    def stream(count, base):
        return "".join(chr(base + i) for i in range(count))

    def assert_covers(self, text):
        chunks = _split_text(text)
        covered = [False] * len(text)
        for chunk in chunks:
            self.assertEqual(text.count(chunk), 1)
            self.assertLessEqual(len(chunk), 1150)
            start = text.index(chunk)
            for i in range(start, start + len(chunk)):
                covered[i] = True
        missing = [i for i, ok in enumerate(covered) if not ok and not text[i].isspace()]
        self.assertEqual(missing, [])
        return chunks

    def test_e01_empty_and_whitespace_only(self):
        self.assertEqual(_split_text(""), [])
        self.assertEqual(_split_text("\n\n\n"), [])

    def test_e02_no_boundaries_at_all(self):
        self.assertEqual([len(c) for c in self.assert_covers(self.stream(3000, 0x4E00))], [1150, 1150, 960])

    def test_e03_only_boundary_just_before_the_halfway_point(self):
        self.assert_covers(self.stream(570, 0xAC00) + ". " + self.stream(3000, 0x4E00))

    def test_e04_only_boundary_just_after_the_halfway_point(self):
        chunks = self.assert_covers(self.stream(580, 0xAC00) + ". " + self.stream(3000, 0x4E00))
        self.assertEqual(len(chunks[0]), 581)

    def test_e05_newline_at_the_last_position(self):
        self.assert_covers(self.stream(1149, 0xAC00) + "\n" + self.stream(2000, 0x4E00))

    def test_e06_words_separated_only_by_spaces(self):
        self.assert_covers(" ".join(self.stream(9, 0xAC00 + 9 * i) for i in range(400)))

    def test_e07_too_long_document_is_refused_not_truncated(self):
        section = {"id": "s0001", "source_order": 1, "title": "t", "page": 1, "text": "가" * 200000}
        with patch.object(dp, "MAX_CHUNKS", 160), self.assertRaises(ValueError):
            make_chunks([section])

    def test_e08_chunk_ids_repeat_across_documents(self):
        # 청크 ID는 문서 안에서만 고유하다. 문서를 넘나들 때는 document_id 와 함께 써야 한다.
        section = {"id": "s0001", "source_order": 1, "title": "t", "page": 1, "text": "본문 내용"}
        self.assertEqual(make_chunks([section])[0]["chunk_id"], make_chunks([dict(section)])[0]["chunk_id"])


if __name__ == "__main__":
    unittest.main()
