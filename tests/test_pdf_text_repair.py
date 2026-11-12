"""PDF 추출 텍스트의 깨진 공백 한자 복원 테스트 (외부 서버 불필요)."""
import unittest

from document_pipeline import broken_space_glyphs, repair_broken_spaces

# 2026-11-12 실측: 한글 PDF 제목에서 공백이 '堺'로 추출됨
# (변경) 깨진 공백은 띄어쓰기만큼 자주 나오므로(실측 1,487회) 판별 기준이 20회 이상이다.
# 그래서 예시도 본문 줄을 붙여 실제에 가까운 빈도로 만든다.
_BODY = "\n오늘은堺날씨가堺맑아서堺산책하기堺좋습니다" * 4
BROKEN = [
    "1. 과정개요\n2. 수업별堺내용堺소개\n3. 준비물堺확인堺및堺순서" + _BODY,
    "1. 실습堺환경과堺도구\n2. 평가堺방법堺안내\n4. 참고堺자료堺목록" + _BODY,
]


class BrokenSpaceRepairTests(unittest.TestCase):
    def test_repeated_glyph_between_hangul_becomes_space(self):
        fixed, glyphs = repair_broken_spaces(BROKEN)
        self.assertEqual(glyphs, {"堺"})
        self.assertIn("2. 수업별 내용 소개", fixed[0])
        self.assertIn("3. 준비물 확인 및 순서", fixed[0])
        self.assertNotIn("堺", "".join(fixed))

    def test_page_count_and_order_are_kept(self):
        fixed, _ = repair_broken_spaces(BROKEN)
        self.assertEqual(len(fixed), len(BROKEN))
        self.assertTrue(fixed[1].startswith("1. 실습 환경과 도구"))

    def test_real_hanja_is_untouched(self):
        texts = ["(株)한국 (株)대한 (株)서울 (株)부산 (株)광주 (株)대전", "研究開發 계획과 研究 결과"]
        fixed, glyphs = repair_broken_spaces(texts)
        self.assertEqual(glyphs, set())
        self.assertEqual(fixed, texts)

    def test_rare_glyph_below_threshold_is_untouched(self):
        self.assertEqual(broken_space_glyphs("가堺나 다堺라"), set())

    def test_clean_text_is_unchanged(self):
        texts = ["1. 과정개요\n2. 수업별 내용 소개"]
        self.assertEqual(repair_broken_spaces(texts), (texts, set()))


if __name__ == "__main__":
    unittest.main()
