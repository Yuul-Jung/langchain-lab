"""자동 모드: 질문마다 문서 · 부품 라이브러리 · 일반 대화 중 하나로 처리 (서버·모델 없이 실행)."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import app
import kicad_parts
import routing

CATALOG = [{"lib_id": "Timer:NE555D", "library": "Timer", "name": "NE555D", "description": "",
            "footprint": "", "datasheet": "", "pin_count": 1,
            "pins": [{"number": "1", "name": "GND", "type": "power_in"}]}]


def hit(score=0.9, terms=("가점",), source="documents"):
    return {"id": "c1", "score": score, "text": "가점은 최대 8점", "source": source, "document_id": "d1",
            "filename": "문서.pdf", "title": "t", "page": 3, "matched_terms": list(terms)}


class AutoRoutingTest(unittest.TestCase):
    def ask(self, question, sources=None, search_error=None, mode="auto", provider="local"):
        llm = mock.Mock()
        llm.invoke.side_effect = lambda m: mock.Mock(content="모델이 만든 답변입니다. " * 3)
        self.llm = llm
        search = mock.Mock(return_value=sources or [], side_effect=search_error)
        self.search = search
        self.resolve_modes = []
        real_resolve = app.resolve

        def spy_resolve(pid, m, *a, **k):
            self.resolve_modes.append(m)
            return real_resolve(pid, m, *a, **k)

        with mock.patch.object(app, "search_for_chat", search), \
             mock.patch.object(app, "available_models", return_value=[app.CHAT_MODEL]), \
             mock.patch.object(app, "resolve", spy_resolve), \
             mock.patch.object(app, "make_chat", return_value=llm), \
             mock.patch.object(kicad_parts, "default_catalog", return_value=CATALOG):
            r = TestClient(app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)).post(
                "/api/chat", json={"mode": mode, "provider": provider,
                                   "messages": [{"role": "user", "content": question}]})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_strong_document_evidence_goes_to_documents_with_one_search(self):
        d = self.ask("가점이 얼마야?", [hit()])
        self.assertEqual((d["mode"], d["route"]), ("auto", "documents"))
        self.assertEqual(self.search.call_count, 1)
        self.assertEqual(len(d["sources"]), 1)
        self.assertEqual(self.resolve_modes, ["rag"])           # 외부 API 제한은 문서 경로로 적용된다
        self.assertIn("가점은 최대 8점", str(self.llm.invoke.call_args))   # 문서가 모델에 전달됨

    def test_part_question_without_document_evidence_goes_to_the_library(self):
        d = self.ask("NE555 단자 정보", [hit(score=0.8, terms=())])     # 점수가 높아도 낱말 일치 0 → 문서 근거 아님
        self.assertEqual((d["route"], d["model"]), ("library", "kicad-library"))
        self.assertEqual(self.llm.invoke.call_count, 0)

    def test_document_evidence_wins_over_a_part_name_in_the_question(self):
        d = self.ask("NE555 가점 규정이 뭐야?", [hit()])       # 핀 질문이 아니므로 라이브러리 대상이 아니다
        self.assertEqual(d["route"], "documents")

    def test_part_in_the_question_but_only_generic_words_match_goes_to_the_library(self):
        # 문서에 '핀'·'정보' 같은 흔한 낱말은 있어도 부품 번호 NE555 는 없다 → 라이브러리
        src = hit(score=0.82, terms=("핀", "정보"))
        src["text"] = "핀 정보 표 ... 다른 부품 설명"
        d = self.ask("NE555 핀 정보", [src])
        self.assertEqual(d["route"], "library")

    def test_part_named_in_the_documents_keeps_the_documents_route(self):
        src = hit(score=0.9, terms=("핀", "ne555"))
        src["text"] = "과제에서는 NE555 타이머의 핀을 연결한다"
        d = self.ask("NE555 핀 정보", [src])
        self.assertEqual(d["route"], "documents")

    def test_unrelated_question_is_general_chat_without_documents(self):
        d = self.ask("안녕하세요", [hit(score=0.7, terms=("안녕",))])
        self.assertEqual(d["route"], "general")
        self.assertEqual(d["sources"], [])
        self.assertEqual(self.resolve_modes, ["chat"])
        self.assertNotIn("가점은 최대 8점", str(self.llm.invoke.call_args))

    def test_weak_score_is_not_document_evidence_even_with_a_matched_word(self):
        self.assertEqual(self.ask("아무 질문", [hit(score=0.7)])["route"], "general")

    def test_search_failure_falls_back_to_general_with_a_note(self):
        d = self.ask("안녕하세요", search_error=RuntimeError("ES 꺼짐"))
        self.assertEqual(d["route"], "general")
        self.assertIn("문서 검색을 쓸 수 없어", d["route_note"])

    def test_lab_sentences_are_not_user_documents(self):
        self.assertEqual(self.ask("모터 과열?", [hit(source="lab")])["route"], "general")

    def test_clock_question_is_answered_without_search(self):
        d = self.ask("오늘 날짜 알려줘")
        self.assertEqual(d["model"], "system-clock")
        self.assertEqual(self.search.call_count, 0)

    def test_document_only_mode_never_uses_the_library_or_general_route(self):
        d = self.ask("NE555 단자 정보", [hit(score=0.5, terms=())], mode="rag")
        self.assertEqual((d["route"], d["mode"]), ("documents", "rag"))

    def test_general_mode_does_not_search_documents(self):
        d = self.ask("안녕하세요", mode="chat")
        self.assertEqual((d["route"], self.search.call_count), ("general", 0))

    def test_part_lookup_can_be_switched_off(self):
        with mock.patch.object(app.settings, "CHAT_PARTS_LOOKUP", False):
            d = self.ask("NE555 단자 정보", [hit(score=0.8, terms=())])
        self.assertEqual(d["route"], "general")


class StrengthTest(unittest.TestCase):
    def test_strong_needs_high_score_and_two_terms(self):
        self.assertEqual(routing.evidence_strength([hit(0.9, terms=("a", "b"))], 0.85), "strong")
        self.assertEqual(routing.evidence_strength([hit(0.84, terms=("a", "b"))], 0.85), "weak")
        self.assertEqual(routing.evidence_strength([hit(0.95, terms=("a",))], 0.85), "weak")
        self.assertEqual(routing.evidence_strength([], 0.85), "weak")

    def test_endpoint_reports_strength_for_the_documents_route(self):
        t = AutoRoutingTest("test_strong_document_evidence_goes_to_documents_with_one_search")
        d = t.ask("가점이 얼마야?", [hit(0.8, terms=("가점",))])
        self.assertEqual((d["route"], d["route_strength"]), ("documents", "weak"))
        d = t.ask("가점이 얼마야?", [hit(0.9, terms=("가점", "얼마"))])
        self.assertEqual(d["route_strength"], "strong")


class EvidenceRuleTest(unittest.TestCase):
    def test_thresholds(self):
        self.assertTrue(routing.has_document_evidence([hit(0.78)], 0.78))
        self.assertFalse(routing.has_document_evidence([hit(0.779)], 0.78))
        self.assertFalse(routing.has_document_evidence([hit(0.9, terms=())], 0.78))
        self.assertFalse(routing.has_document_evidence([], 0.78))
        self.assertFalse(routing.has_document_evidence([{"score": 0.9, "matched_terms": None}], 0.78))


if __name__ == "__main__":
    unittest.main()


class CitePromptSettingTest(unittest.TestCase):
    def test_old_module_constant_still_exists_for_other_scripts(self):
        self.assertTrue(app.RAG_CITE_INSTRUCTION)
    def test_default_and_env_file_value(self):
        self.assertEqual(app.rag_cite_instruction(), app.DEFAULT_CITE_INSTRUCTION)
        with mock.patch.dict(app.settings._VALUES, {"RAG_CITE_PROMPT": "문장마다 번호를 붙이세요."}):
            self.assertEqual(app.rag_cite_instruction(), "문장마다 번호를 붙이세요.")     # .env 값이 실제로 쓰인다


class FollowupRoutingTest(unittest.TestCase):
    """직전 질문이 문서 대화였을 때의 후속 질문 처리 (검색은 모의)."""

    def route(self, question, previous, searches):
        """searches: 검색어에 그 낱말이 들어 있으면 해당 결과를 돌려주는 사전 {낱말: 결과 목록}."""
        def fake_search(query, *a, **k):
            for key, result in searches.items():
                if key in query:
                    return result
            return []
        with mock.patch.object(app, "search_for_chat", side_effect=fake_search), \
             mock.patch.object(kicad_parts, "default_catalog", return_value=[]):
            return app.decide_route(question, previous)

    def test_short_followup_with_a_marker_inherits_the_documents_route(self):
        d = self.route("그럼 그건 얼마야?", "가점이 얼마야?", {"가점": [hit(0.9, terms=("가점",))]})
        self.assertEqual((d["route"], d["strength"]), ("documents", "weak"))
        self.assertEqual(len(d["sources"]), 1)                       # 직전 질문을 붙여 다시 검색한 결과를 쓴다

    def route_fn(self, question, previous, fn):
        """fn(검색어) → 결과 목록. 검색어에 따라 점수가 달라지는 상황을 흉내 낸다."""
        with mock.patch.object(app, "search_for_chat", side_effect=lambda q, *a, **k: fn(q)), \
             mock.patch.object(kicad_parts, "default_catalog", return_value=[]):
            return app.decide_route(question, previous)

    def test_short_new_topic_without_a_marker_loses_score_when_merged_and_is_judged_alone(self):
        def fn(q):
            if q == "가점이 얼마야?":
                return [hit(0.90, terms=("가점",))]
            if q.startswith("가점이 얼마야? "):
                return [hit(0.80, terms=("가점",))]          # 새 주제가 섞이면 점수가 크게 떨어진다 (0.10)
            return []
        self.assertEqual(self.route_fn("원의 넓이 공식", "가점이 얼마야?", fn)["route"], "general")

    def test_elliptical_followup_keeps_its_score_when_merged_and_inherits(self):
        def fn(q):
            if q == "가점이 얼마야?":
                return [hit(0.90, terms=("가점",))]
            if q.startswith("가점이 얼마야? "):
                return [hit(0.89, terms=("가점",))]          # 거의 안 떨어진다 (0.01)
            return []
        d = self.route_fn("비용은?", "가점이 얼마야?", fn)
        self.assertEqual((d["route"], d["strength"]), ("documents", "weak"))

    def test_elliptical_rule_can_be_switched_off(self):
        def fn(q):
            return [hit(0.90, terms=("가점",))] if q.startswith("가점이 얼마야?") else []
        with mock.patch.object(app.settings, "ROUTE_ELLIPSIS_MAX_DROP", 0):
            self.assertEqual(self.route_fn("비용은?", "가점이 얼마야?", fn)["route"], "general")

    def test_long_question_is_judged_alone_even_with_a_marker(self):
        q = "그럼 이 문서와는 전혀 상관없는 아주 긴 새 질문을 하나 더 해도 될까요 부탁합니다"
        self.assertEqual(self.route(q, "가점이 얼마야?", {"가점": [hit(0.9, terms=("가점",))]})["route"], "general")

    def test_weak_document_evidence_after_a_general_turn_goes_to_general(self):
        d = self.route("그거 자세히", "안녕하세요", {"그거": [hit(0.8, terms=("그거",))]})
        self.assertEqual(d["route"], "general")

    def test_strong_standalone_evidence_is_kept_after_a_general_turn(self):
        d = self.route("가점 기준은?", "안녕하세요", {"가점": [hit(0.95, terms=("가점", "기준"))]})
        self.assertEqual(d["route"], "documents")

    def test_can_be_switched_off(self):
        with mock.patch.object(app.settings, "ROUTE_FOLLOWUP_MAX_CHARS", 0):
            d = self.route("그럼 그건 얼마야?", "가점이 얼마야?", {"가점": [hit(0.9, terms=("가점",))]})
        self.assertEqual(d["route"], "general")

    def test_no_previous_question_behaves_as_before(self):
        self.assertEqual(self.route("그럼 그건 얼마야?", None, {"가점": [hit()]})["route"], "general")


class FollowupMarkerTest(unittest.TestCase):
    def test_markers(self):
        for yes in ("그러면 두 번째 항목은?", "방금 말한 것 다시 정리해줘", "자세히 알려줘", "또 다른 방법은?"):
            self.assertTrue(routing.looks_like_followup(yes), yes)
        for no in ("원의 넓이 공식", "고마워요", "비용은?", "그림을 그려줘"):    # 마지막: '그'가 낱말 안에 있어도 단서가 아님
            self.assertFalse(routing.looks_like_followup(no), no)
