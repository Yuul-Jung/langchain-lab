"""외국 문자 혼입 처리 순서 (서버·모델 없이 실행)."""
import unittest
from unittest import mock

import app
import settings

KOREAN = "이것은 한국어로 쓴 충분히 긴 설명 문장입니다. 회로의 동작 원리를 순서대로 풀어서 설명합니다. "


def no_model(prompt, draft):
    raise AssertionError("모델을 부르면 안 되는 경우")


class PolishTest(unittest.TestCase):
    def test_table_fixes_without_calling_the_model(self):
        r = app.polish_answer(KOREAN + "답案은 다음과 같습니다.", "질문", "질문", no_model)
        self.assertIn("답안은", r["answer"])
        self.assertEqual((r["state"], r["hanja_fixed"], r["draft"]), ("none", 1, None))

    def test_clean_answer_is_untouched(self):
        r = app.polish_answer(KOREAN, "질문", "질문", no_model)
        self.assertEqual((r["answer"], r["state"], r["hanja_fixed"]), (KOREAN, "none", 0))

    def test_unfixable_hanja_in_korean_answer_keeps_the_draft_not_the_notice(self):
        draft = KOREAN + "樂 說 切 같은 글자가 섞였습니다."          # 표에 없는 한자 3자 → 무거운 혼입
        r = app.polish_answer(draft, "질문", "질문", lambda p, d: d)   # 모델이 못 고침
        self.assertEqual(r["state"], "kept")
        self.assertEqual(r["answer"], draft)
        self.assertEqual(r["draft"], draft)

    def test_keep_can_be_switched_off(self):
        draft = KOREAN + "樂 說 切 같은 글자가 섞였습니다."
        with mock.patch.object(settings, "CHAT_KEEP_DRAFT_ON_FAIL", False):
            r = app.polish_answer(draft, "질문", "질문", lambda p, d: d)
        self.assertEqual((r["state"], r["answer"]), ("fallback", app.FALLBACK_NOTICE))

    def test_almost_entirely_foreign_answer_still_gets_the_notice(self):
        r = app.polish_answer("这是一个很长的中文回答完全不是韩国语" * 3, "질문", "질문", lambda p, d: d)
        self.assertEqual((r["state"], r["answer"]), ("fallback", app.FALLBACK_NOTICE))

    def test_table_is_not_applied_to_a_mostly_foreign_answer_and_log_keeps_the_original(self):
        draft = "这是一个很长的中文回答完全不是韩国语" * 3
        r = app.polish_answer(draft, "질문", "질문", lambda p, d: d)
        self.assertEqual((r["hanja_fixed"], r["draft"]), (0, draft))

    def test_log_draft_is_the_model_original_even_when_the_table_changed_it(self):
        draft = KOREAN * 2 + "答案 樂 說 切 이 섞였습니다."
        r = app.polish_answer(draft, "질문", "질문", lambda p, d: d)
        self.assertEqual(r["state"], "kept")
        self.assertIn("答", r["draft"])          # 기록에는 표로 고치기 전의 글
        self.assertNotIn("答", r["answer"])      # 보여 주는 답은 표로 고친 글

    def test_model_rewrite_is_used_when_it_works(self):
        draft = KOREAN + "樂 說 切 같은 글자가 섞였습니다."
        r = app.polish_answer(draft, "질문", "질문", lambda p, d: KOREAN + "악기 설명 절단 같은 글자가 섞였습니다.")
        self.assertEqual(r["state"], "heavy")

    def test_quotation_from_question_is_not_changed(self):
        r = app.polish_answer(KOREAN + "案이라는 글자입니다.", "案이 무슨 뜻이야", "案이 무슨 뜻이야", no_model)
        self.assertIn("案", r["answer"])

    def test_foreign_text_request_skips_table_and_light_fix(self):
        r = app.polish_answer(KOREAN + "한자로는 案이라고 씁니다.", "한자로 써줘", "한자로 써줘", no_model)
        self.assertIn("案", r["answer"])
        self.assertEqual(r["hanja_fixed"], 0)

    def test_table_can_be_switched_off(self):
        with mock.patch.object(settings, "CHAT_HANJA_TABLE", False), \
                mock.patch.object(settings, "CHAT_LIGHT_LEAK_FIX", False):
            r = app.polish_answer(KOREAN + "답案", "질문", "질문", no_model)
        self.assertIn("案", r["answer"])


class KoreanDominantTest(unittest.TestCase):
    def test_short_answers_are_allowed_but_foreign_ones_are_not(self):
        self.assertTrue(app.korean_dominant("답案: 8점"))
        self.assertFalse(app.korean_dominant("这是中文回答"))
        self.assertFalse(app.korean_dominant("가樂說切"))      # 한글 1 : 한자 3 → 표를 쓰지 않는다


class MostlyKoreanTest(unittest.TestCase):
    def test_boundaries(self):
        self.assertTrue(app.mostly_korean("가" * 20 + "樂" * 2))
        self.assertFalse(app.mostly_korean("가" * 19))
        self.assertFalse(app.mostly_korean("가" * 20 + "樂" * 3))


if __name__ == "__main__":
    unittest.main()
