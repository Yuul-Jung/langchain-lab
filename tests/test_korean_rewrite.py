"""채팅 답변의 가벼운 외국 문자 혼입 처리 (서버·모델 없이 실행).

원칙: 모델이 다시 쓴 글 전체를 받지 않고, 외국 문자가 있던 자리의 수정만 원래 답에 옮긴다.
"""
import importlib.util
import unittest
from unittest import mock

NEEDS = unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"),
                            "fastapi/httpx 미설치")


@NEEDS
class LeakDetectionTest(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app

    def test_foreign_characters_are_counted_unless_they_are_quoted_from_the_sources(self):
        leaks = self.app.foreign_leaks
        self.assertEqual(leaks("답案: 3대입니다"), 1)
        self.assertEqual(leaks("모듈に関わる 파일"), 4)
        self.assertEqual(leaks("프로토ไท프"), 2)
        self.assertEqual(leaks("XK7 핀에 연결합니다 (Sample Folder)"), 0)
        self.assertEqual(leaks("(株)한국 규정에 따릅니다", allowed="참고 문서: (株)한국"), 0)

    def test_stray_characters_are_listed_once_in_order(self):
        stray = self.app.stray_characters
        self.assertEqual(stray("結과와 方법, 그리고 結과"), ["結", "方"])
        self.assertEqual(stray("結과와 方법", allowed="方"), ["結"])
        self.assertEqual(stray("깨끗한 한국어 답변 ABC 123"), [])

    def test_facts_preserved_requires_numbers_identifiers_and_length(self):
        keep = self.app.facts_preserved
        original = "가점은 최대 8 점입니다. XK7 핀과 sum_bits 절차, 12,340억 [자료 1]"
        self.assertTrue(keep(original, "가점은 최대 8점이며 XK7 핀, sum_bits 절차, 12,340억입니다 [자료 1]"))
        self.assertFalse(keep(original, "가점은 최대 8점이며 XK7 핀, sum_bits 절차입니다 [자료 1]"))      # 숫자 빠짐
        self.assertFalse(keep(original, "가점은 최대 8점이며 엑스케이7 핀, sum_bits 절차, 12,340억 [자료 1]"))  # 식별자 번역됨
        self.assertFalse(keep("아주 긴 설명이 이어지는 원래 답변입니다. 8점입니다.", "8점"))                    # 너무 짧아짐

    def test_facts_preserved_requires_the_citation_marks(self):
        keep = self.app.facts_preserved
        original = "가점은 최대 8점입니다 [자료 1]. 신청 기간은 3주입니다 [자료 3]."
        self.assertTrue(keep(original, "가점은 최대 8점입니다 [자료1]. 신청 기간은 3주입니다 [자료 3]."))
        self.assertFalse(keep(original, "가점은 최대 8점입니다 [자료 1]. 신청 기간은 3주입니다."))             # 숫자 3은 남았지만 표시가 빠짐
        self.assertFalse(keep(original, "가점은 최대 8점이고 신청 기간은 3주입니다. 자료 1과 3 참고"))

    def test_questions_that_ask_for_foreign_text_are_recognised(self):
        asks = self.app.asks_foreign_text
        for question in ("'안녕하세요'를 일본어로 알려 줘", "학교를 한자로 써 줘", "이 문장을 영어로 번역해 줘",
                         "Translate this into Korean", "중국어 인사말 세 가지"):
            with self.subTest(question):
                self.assertTrue(asks(question))
        for question in ("가점은 최대 몇 점인가요?", "XK7 핀은 어디에 연결하나요?", "신청 기간을 알려 줘"):
            with self.subTest(question):
                self.assertFalse(asks(question))


@NEEDS
class MergeLeakFixesTest(unittest.TestCase):
    """다시 쓴 글에서 외국 문자가 있던 자리의 수정만 옮겨지는지."""

    def merge(self, original, rewrite, allowed=""):
        import app
        return app.merge_leak_fixes(original, rewrite, allowed)

    def test_a_stray_character_is_replaced_and_nothing_else_changes(self):
        self.assertEqual(self.merge("가점은 8점입니다. 답案: 8점", "가점은 8점입니다. 답안: 8점"), "가점은 8점입니다. 답안: 8점")
        self.assertEqual(self.merge("받을 수 있습니다よ. 끝", "받을 수 있습니다. 끝"), "받을 수 있습니다. 끝")
        self.assertEqual(self.merge("모듈に関わる 파일입니다", "모듈과 관련된 파일입니다"), "모듈과 관련된 파일입니다")

    def test_changes_away_from_the_stray_characters_are_discarded(self):
        original = "절차는 結과를 [자료 1]에 따라 sum_bits 로 냅니다."
        rewrite = "작업은 결과를 자료 1에 따라 비트합 로 냅니다."      # 용어·출처 표시·영문 이름까지 바꾼 글
        self.assertEqual(self.merge(original, rewrite), "절차는 결과를 [자료 1]에 따라 sum_bits 로 냅니다.")

    def test_sentences_the_model_dropped_or_added_are_ignored(self):
        original = "첫 문장은 그대로 둡니다. 둘째 문장의 方법도 그대로입니다."
        self.assertEqual(self.merge(original, "둘째 문장의 방법도 그대로입니다."), "첫 문장은 그대로 둡니다. 둘째 문장의 방법도 그대로입니다.")
        wrapped = "수정한 결과입니다:\n\n```\n첫 문장은 그대로 둡니다. 둘째 문장의 방법도 그대로입니다.\n```"
        self.assertEqual(self.merge(original, wrapped), "첫 문장은 그대로 둡니다. 둘째 문장의 방법도 그대로입니다.")

    def test_a_fix_is_refused_when_it_changes_a_number_or_an_english_name(self):
        self.assertEqual(self.merge("제3案을 고릅니다", "제4안을 고릅니다"), "제3案을 고릅니다")
        self.assertEqual(self.merge("JB案 핀입니다", "JA안 핀입니다"), "JB案 핀입니다")
        # 숫자가 그 자리 밖에 있으면 외국 문자만 고치고 숫자 변경은 버린다
        self.assertEqual(self.merge("方법은 7묶음입니다", "방법은 5묶음입니다"), "방법은 7묶음입니다")

    def test_a_fix_is_refused_when_it_drops_or_changes_a_symbol(self):
        # 굵게 표시(**)·대괄호·붙임표 같은 기호가 그 자리에서 사라지면 화면 표시나 출처 표시가 깨진다
        self.assertEqual(self.merge("**結과**는 같습니다", "결과**는 같습니다"), "**結과**는 같습니다")
        self.assertEqual(self.merge("수요-技술 연결", "수요 기술 연결"), "수요-技술 연결")
        self.assertEqual(self.merge("보세요に[자료 1]", "보세요 자료 1"), "보세요に[자료 1]")
        # 기호를 그대로 둔 수정은 받는다
        self.assertEqual(self.merge("**結과**는 같습니다", "**결과**는 같습니다"), "**결과**는 같습니다")
        self.assertEqual(self.merge("수요-技술 연결", "수요-기술 연결"), "수요-기술 연결")

    def test_broken_characters_next_to_a_stray_one_may_be_replaced(self):
        self.assertEqual(self.merge("프로토\ufffdไท프 개발", "프로토타입 개발"), "프로토타입 개발")

    def test_a_fix_is_refused_when_it_swaps_in_another_foreign_character(self):
        self.assertEqual(self.merge("답案: 8점", "답答: 8점"), "답案: 8점")
        self.assertEqual(self.merge("프로토ไท프 개발", "프로토タイプ 개발"), "프로토ไท프 개발")

    def test_a_fix_is_refused_when_it_adds_words_or_deletes_korean_text(self):
        self.assertEqual(self.merge("연습용으로 使용됩니다", "연습용으로 아주 유용하게 사용됩니다"), "연습용으로 使용됩니다")
        self.assertEqual(self.merge("표시 모듈に関わる 파일입니다", "표시 모듈입니다"), "표시 모듈に関わる 파일입니다")

    def test_a_fix_is_refused_when_the_changed_stretch_is_long(self):
        original = "설명: これはとても長い日本語の文章です 끝"
        self.assertEqual(self.merge(original, "설명: 이것은 아주 긴 일본어 문장입니다 끝"), original)

    def test_characters_quoted_from_the_sources_are_not_touched(self):
        merged = self.merge("(株)한국의 답案입니다", "(주)한국의 답안입니다", allowed="참고 문서: (株)한국")
        self.assertEqual(merged, "(株)한국의 답안입니다")


@NEEDS
class FixLightLeakTest(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app

    def test_clean_answer_is_not_rewritten(self):
        rewrite = mock.Mock()
        self.assertEqual(self.app.fix_light_leak("가점은 8점입니다.", "", rewrite), ("가점은 8점입니다.", "none"))
        rewrite.assert_not_called()

    def test_the_model_gets_the_minimal_edit_instruction_and_the_whole_answer(self):
        seen = {}

        def rewrite(prompt, draft):
            seen.update(prompt=prompt, draft=draft)
            return "가점은 최대 8점입니다. 답안: 8점"
        answer, state = self.app.fix_light_leak("가점은 최대 8점입니다. 답案: 8점", "", rewrite)
        self.assertEqual((answer, state), ("가점은 최대 8점입니다. 답안: 8점", "light"))
        self.assertEqual(seen["prompt"], self.app.LIGHT_REWRITE_PROMPT)
        self.assertIn("한 글자도 바꾸지 말고", seen["prompt"])
        self.assertEqual(seen["draft"], "가점은 최대 8점입니다. 답案: 8점")

    def test_a_partial_fix_is_still_an_improvement(self):
        answer, state = self.app.fix_light_leak("方법과 結과", "", lambda prompt, draft: "방법과 結과")
        self.assertEqual((answer, state), ("방법과 結과", "light"))

    def test_original_is_kept_when_nothing_was_fixed(self):
        original = "XK7 핀에 연결합니다. 답案: XK7"
        cases = {
            "외국 문자를 그대로 둠": "XK7 핀에 연결합니다. 답案: XK7",
            "다른 한자로 바꿈": "XK7 핀에 연결합니다. 답答: XK7",
            "외국 문자는 두고 영문 이름만 바꿈": "첫째 핀에 연결합니다. 답案: 첫째 핀",
            "빈 답": "   ",
            "전혀 다른 글": "모르겠습니다.",
        }
        for name, rewritten in cases.items():
            with self.subTest(name):
                self.assertEqual(self.app.fix_light_leak(original, "", lambda prompt, draft, r=rewritten: r), (original, "kept"))

    def test_only_the_stray_character_changes_even_if_the_model_rewrote_everything(self):
        original = "절차는 結과를 [자료 1]에 따라 sum_bits 로 냅니다."
        answer, state = self.app.fix_light_leak(original, "", lambda prompt, draft: "작업은 결과를 자료 1에 따라 비트합 로 냅니다.")
        self.assertEqual((answer, state), ("절차는 결과를 [자료 1]에 따라 sum_bits 로 냅니다.", "light"))

    def test_a_fix_that_breaks_a_citation_mark_is_refused(self):
        # 외국 문자 바로 옆의 대괄호까지 지운 수정은 받지 않는다 (출처 표시가 깨진다)
        original = "자세한 내용은 보세요に[자료 1]"
        self.assertEqual(self.app.fix_light_leak(original, "", lambda prompt, draft: "자세한 내용은 보세요 자료 1"), (original, "kept"))

    def test_original_is_kept_when_the_rewrite_call_fails(self):
        def broken(prompt, draft):
            raise RuntimeError("모델 응답 실패")
        self.assertEqual(self.app.fix_light_leak("답案: 8점", "", broken), ("답案: 8점", "kept"))

    def test_very_long_answers_are_left_alone_without_a_model_call(self):
        rewrite = mock.Mock()
        long_answer = "답案 " + "가" * self.app.LIGHT_FIX_MAX_CHARS
        self.assertEqual(self.app.fix_light_leak(long_answer, "", rewrite), (long_answer, "kept"))
        rewrite.assert_not_called()


@NEEDS
class ChatRewriteEndpointTest(unittest.TestCase):
    def ask(self, replies, messages=None):
        from fastapi.testclient import TestClient
        import app
        messages = messages or [{"role": "user", "content": "가점은?"}]
        llm = mock.Mock()
        llm.invoke.side_effect = [mock.Mock(content=text) for text in replies]
        hits = [{"document_id": "d1", "chunk_id": "c1", "filename": "문서.pdf", "title": "t", "page": 3,
                 "text": "가점은 최대 8 점까지 가능", "score": 0.9}]
        with mock.patch.object(app, "available_models", return_value=[app.CHAT_MODEL]), \
             mock.patch.object(app, "search_uploaded", return_value=hits), \
             mock.patch.object(app.settings, "CHAT_RAG_SOURCE", "documents"), \
             mock.patch.object(app, "make_chat", return_value=llm):
            r = TestClient(app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)).post(
                "/api/chat", json={"mode": "rag", "provider": "local", "messages": messages})
        self.assertEqual(r.status_code, 200, r.text)
        self.llm = llm
        return r.json(), llm.invoke.call_count

    def test_clean_answer_needs_one_model_call(self):
        data, calls = self.ask(["가점은 최대 8점입니다 [자료 1]"])
        self.assertEqual((data["rewrite"], calls), ("none", 1))

    def test_light_leak_is_fixed_with_one_extra_call(self):
        data, calls = self.ask(["가점은 최대 8점입니다 [자료 1]. 답案: 8점", "가점은 최대 8점입니다 [자료 1]. 답안: 8점"])
        self.assertEqual((data["rewrite"], calls), ("light", 2))
        self.assertEqual(data["answer"], "가점은 최대 8점입니다 [자료 1]. 답안: 8점")
        import app
        self.assertEqual(self.llm.invoke.call_args_list[1].args[0][0], ("system", app.LIGHT_REWRITE_PROMPT))

    def test_rewrite_that_changes_the_facts_cannot_change_them_in_the_answer(self):
        # 모델이 숫자와 출처 표시를 바꿔 다시 썼어도, 답에는 외국 문자 자리의 수정만 들어간다
        data, calls = self.ask(["가점은 최대 8점입니다 [자료 1]. 답案: 8점", "가점은 최대 5점입니다. 답안: 5점"])
        self.assertEqual((data["rewrite"], calls), ("light", 2))
        self.assertEqual(data["answer"], "가점은 최대 8점입니다 [자료 1]. 답안: 8점")

    def test_useless_rewrite_leaves_the_original_answer(self):
        data, calls = self.ask(["가점은 최대 8점입니다 [자료 1]. 답案: 8점", "가점이 있습니다."])
        self.assertEqual((data["rewrite"], calls), ("kept", 2))
        self.assertEqual(data["answer"], "가점은 최대 8점입니다 [자료 1]. 답案: 8점")

    def test_requested_foreign_text_is_left_alone(self):
        # 사용자가 일본어를 요청했으면 가나는 혼입이 아니다. 뒤따르는 짧은 질문에서도 마찬가지다.
        talk = [{"role": "user", "content": "문서의 인사말을 일본어로 알려 줘"},
                {"role": "assistant", "content": "こんにちは 입니다."},
                {"role": "user", "content": "하나 더"}]
        data, calls = self.ask(["おはよう 도 있습니다 [자료 1]"], messages=talk)
        self.assertEqual((data["rewrite"], calls), ("none", 1))
        self.assertIn("おはよう", data["answer"])

    def test_characters_the_user_typed_earlier_are_not_leaks(self):
        talk = [{"role": "user", "content": "案 이라는 글자가 문서에 있나요?"},
                {"role": "assistant", "content": "확인해 보겠습니다."},
                {"role": "user", "content": "가점은?"}]
        data, calls = self.ask(["案 은 없습니다. 가점은 최대 8점입니다 [자료 1]"], messages=talk)
        self.assertEqual((data["rewrite"], calls), ("none", 1))

    def test_heavy_mixing_still_falls_back_as_before(self):
        data, calls = self.ask(["这是中文回答没有韩文", "还是中文回答"])
        self.assertEqual((data["rewrite"], calls), ("fallback", 2))
        self.assertIn("다른 언어가 혼용", data["answer"])


if __name__ == "__main__":
    unittest.main()
