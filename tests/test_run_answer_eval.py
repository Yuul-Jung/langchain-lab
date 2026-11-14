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


class CitationTest(unittest.TestCase):
    def test_citation_beyond_the_source_count_is_flagged(self):
        ok = answer_eval.score_answer(ITEM, response("장비 3대 [자료 1]"), 1)
        bad = answer_eval.score_answer(ITEM, response("장비 3대 [자료 2]"), 1)   # 근거는 1개뿐
        self.assertEqual((ok["cited"], ok["bad_cite"]), (True, False))
        self.assertEqual((bad["cited"], bad["bad_cite"]), (True, True))

    def test_answer_without_citation_is_not_bad(self):
        self.assertFalse(answer_eval.score_answer(ITEM, response("장비 3대"), 1)["bad_cite"])


class GroundingWiringTest(unittest.TestCase):
    def test_score_counts_items_missing_from_sources_and_keeps_the_list_apart(self):
        item = dict(ITEM, question="장비는 몇 대?")
        resp = {"answer": "장비 3대와 Zebra 99개 [자료 1]",
                "sources": [{"document_id": DOC, "page": 3, "score": 1, "text": "장비는 3 대"}]}
        row = answer_eval.score_answer(item, resp, 1)
        self.assertEqual(row["ungrounded"], 2)      # 못 찾은 것: 99, zebra (3 은 근거에 있다)
        self.assertEqual(sorted(row["ungrounded_items"]), ["99", "zebra"])


    def test_answer_without_sources_is_not_checked(self):
        row = answer_eval.score_answer(dict(ITEM, question="q"), {"answer": "핀 21번, VCC", "sources": []}, 1)
        self.assertIsNone(row["ungrounded"])


class SearchFailureTest(unittest.TestCase):
    def test_note_from_a_failed_search_is_flagged_so_the_run_can_be_discarded(self):
        resp = dict(response("답"), route="general", route_note="문서 검색을 쓸 수 없어 문서를 보지 않고 답했습니다.")
        row = answer_eval.score_answer(ITEM, resp, 1)
        self.assertTrue(row["search_failed"])
        self.assertEqual(answer_eval.summarize([row])["search_failed"], 1)
        self.assertFalse(answer_eval.score_answer(ITEM, response("답"), 1)["search_failed"])


class AggregateTest(unittest.TestCase):
    def test_mean_min_max_across_runs(self):
        runs = [{"evidence": 1.0, "facts": 0.5, "cited": 0.4, "fallback": 2, "foreign_answers": 1, "rewritten": 0},
                {"evidence": 0.9, "facts": 0.7, "cited": 0.6, "fallback": 0, "foreign_answers": 3, "rewritten": 0}]
        agg = answer_eval.aggregate(runs)
        self.assertEqual(agg["runs"], 2)
        self.assertEqual(agg["facts"], {"mean": 0.6, "min": 0.5, "max": 0.7})
        self.assertEqual(agg["fallback"], {"mean": 1, "min": 0, "max": 2})

    def test_runs_without_a_value_are_left_out_not_counted_as_zero(self):
        agg = answer_eval.aggregate([{"facts": None, "evidence": 1.0}, {"facts": 0.8, "evidence": 1.0}])
        self.assertEqual(agg["facts"], {"mean": 0.8, "min": 0.8, "max": 0.8})

    def test_all_missing_value_is_omitted(self):
        self.assertNotIn("facts", answer_eval.aggregate([{"facts": None}, {"facts": None}]))
