"""채팅 답변 확인 계산 (서버·모델 없이 실행)."""
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "answer_eval", Path(__file__).resolve().parent.parent / "scripts" / "run-answer-eval.py")
answer_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(answer_eval)

DOC = "aaaa1111" + "0" * 24
ITEM = {"id": "q1", "document_id": DOC, "pages": [3, 4], "answer_keys": [["3대", "세 대"], ["장비"]]}


def response(answer, sources=((DOC, 3),)):
    return {"answer": answer, "sources": [{"document_id": d, "page": p, "score": 0.9} for d, p in sources]}


class FactsTest(unittest.TestCase):
    def test_every_group_must_match_and_any_alternative_is_enough(self):
        keys = [["3대", "세 대"], ["장비"]]
        self.assertTrue(answer_eval.facts_present("실습 장비는 3 대가 필요합니다.", keys))
        self.assertTrue(answer_eval.facts_present("장비는 세 대 필요합니다.", keys))
        self.assertFalse(answer_eval.facts_present("장비가 필요합니다.", keys))
        self.assertFalse(answer_eval.facts_present("3대", keys))

    def test_spacing_and_case_are_ignored(self):
        self.assertTrue(answer_eval.facts_present("sample  folder 에만 넣습니다", [["Sample Folder"]]))

    def test_questions_without_keys_are_not_judged(self):
        self.assertIsNone(answer_eval.facts_present("아무 답", None))
        self.assertIsNone(answer_eval.facts_present("아무 답", []))


class ScoreTest(unittest.TestCase):
    def test_good_answer(self):
        row = answer_eval.score_answer(ITEM, response("장비는 3대입니다 [자료 1]"), 12.34)
        self.assertEqual((row["evidence"], row["facts"], row["cited"], row["fallback"], row["seconds"]),
                         (True, True, True, False, 12.3))
        self.assertNotIn("answer", row)            # 답변 본문은 결과 표에 넣지 않는다

    def test_wrong_page_or_document_is_not_evidence(self):
        self.assertFalse(answer_eval.score_answer(ITEM, response("x", [(DOC, 9)]), 1)["evidence"])
        self.assertFalse(answer_eval.score_answer(ITEM, response("x", [("b" * 32, 3)]), 1)["evidence"])
        self.assertFalse(answer_eval.score_answer(ITEM, response("x", []), 1)["evidence"])

    def test_language_fallback_message_is_detected(self):
        text = "답변에서 다른 언어가 혼용되어 정확한 한국어 결과를 만들지 못했습니다."
        row = answer_eval.score_answer(ITEM, response(text), 1)
        self.assertEqual((row["fallback"], row["facts"], row["cited"]), (True, False, False))

    def test_foreign_script_characters_are_counted(self):
        row = answer_eval.score_answer(ITEM, response("장비는 3대입니다. 답案: 3대 に関わる ไท"), 1)
        self.assertEqual(row["foreign"], 7)
        self.assertEqual(answer_eval.score_answer(ITEM, response("장비는 3대입니다. XK7 Sample"), 1)["foreign"], 0)

    def test_summary(self):
        rows = [answer_eval.score_answer(ITEM, response("장비는 3대입니다 [자료 1]"), 10),
                answer_eval.score_answer(ITEM, response("모르겠습니다", []), 20),
                answer_eval.score_answer(dict(ITEM, answer_keys=None), response("답 [자료 2]"), 30)]
        s = answer_eval.summarize(rows)
        self.assertEqual((s["questions"], s["evidence"], s["facts"], s["facts_checked"]), (3, 0.667, 0.5, 2))
        self.assertEqual((s["cited"], s["fallback"], s["seconds_median"], s["seconds_max"]), (0.667, 0, 20, 30))
        self.assertEqual((s["foreign_answers"], s["rewritten"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
