"""평가 세트 채점 계산 (서버·실제 문서 없이 실행)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "run_eval", Path(__file__).resolve().parent.parent / "scripts" / "run-eval.py")
run_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_eval)

DOC_A = "aaaa1111-0000-0000-0000-000000000000"
DOC_B = "bbbb2222-0000-0000-0000-000000000000"


def hit(doc, page, text="본문"):
    return {"document_id": doc, "page": page, "text": text}


class LoadQuestionsTest(unittest.TestCase):
    def write(self, lines):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
        f.write("\n".join(lines))
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return f.name

    def test_prefix_document_id_is_expanded_and_status_defaults(self):
        path = self.write(["# 주석 줄", json.dumps({"id": "q1", "question": "질문", "document_id": "aaaa11", "pages": [3]})])
        items = run_eval.load_questions(path, [DOC_A, DOC_B])
        self.assertEqual(items[0]["document_id"], DOC_A)
        self.assertEqual(items[0]["status"], "draft")

    def test_bad_lines_are_reported_with_line_number(self):
        cases = [
            ("{잘못된", "1번째 줄"),
            (json.dumps({"id": "q1", "question": "", "document_id": "aaaa", "pages": [1]}), "question"),
            (json.dumps({"id": "q1", "question": "질문", "document_id": "aaaa", "pages": [0]}), "pages"),
            (json.dumps({"id": "q1", "question": "질문", "document_id": "zzzz", "pages": [1]}), "0개"),
            (json.dumps({"id": "q1", "question": "질문", "document_id": "aaaa", "pages": [1], "status": "ok"}), "status"),
        ]
        for line, message in cases:
            with self.subTest(message=message), self.assertRaises(ValueError) as ctx:
                run_eval.load_questions(self.write([line]), [DOC_A, DOC_B])
            self.assertIn(message, str(ctx.exception))

    def test_duplicate_id_is_rejected(self):
        line = json.dumps({"id": "q1", "question": "질문", "document_id": "aaaa", "pages": [1]})
        with self.assertRaises(ValueError):
            run_eval.load_questions(self.write([line, line]), [DOC_A])


class ScoreTest(unittest.TestCase):
    item = {"id": "q1", "status": "draft", "document_id": DOC_A, "pages": [3, 4], "keywords": ["UART"]}

    def test_rank_is_first_matching_document_and_page(self):
        hits = [hit(DOC_B, 3), hit(DOC_A, 9), hit(DOC_A, 4, "uart 설정")]
        r = run_eval.score_question(self.item, hits, k=5)
        self.assertEqual((r["rank"], r["doc_rank"], r["top1_same_doc"], r["keyword_hit"]), (3, 2, False, True))

    def test_hits_beyond_k_do_not_count(self):
        hits = [hit(DOC_B, 1), hit(DOC_A, 3)]
        r = run_eval.score_question(self.item, hits, k=1)
        self.assertIsNone(r["rank"])

    def test_summary_metrics(self):
        results = [
            run_eval.score_question(self.item, [hit(DOC_A, 3, "UART")], 5),           # 1위
            run_eval.score_question(self.item, [hit(DOC_B, 1), hit(DOC_A, 4)], 5),     # 2위
            run_eval.score_question(self.item, [hit(DOC_B, 1)], 5),                    # 없음
        ]
        s = run_eval.summarize(results, 5)
        self.assertEqual(s["hit@1"], 0.333)
        self.assertEqual(s["hit@5"], 0.667)
        self.assertEqual(s["mrr"], 0.5)
        self.assertEqual(s["keyword@5"], 0.333)
        # 결과 수 1·2·1개, 그중 정답 1·1·0개 → 평균 1.33개, 정밀도 (1 + 0.5 + 0) / 3
        self.assertEqual(s["avg_results"], 1.33)
        self.assertEqual(s["precision"], 0.5)

    def test_keyword_search_scoring(self):
        rows = [
            run_eval.score_keyword("산업안전", [hit(DOC_A, 8, "지역 산업 안전 교육"), hit(DOC_B, 15, "안전 표시")]),
            run_eval.score_keyword("XADC", [hit(DOC_B, 2, "gpio 입력 설정")]),
        ]
        self.assertEqual((rows[0]["containing"], rows[0]["top1_contains"]), (1, True))
        s = run_eval.summarize_keywords(rows)
        self.assertEqual((s["avg_results"], s["containing_rate"], s["top1_contains"]), (1.5, 0.75, 1.0))

    def test_compare_lists_changed_ranks(self):
        prev = {"results": [{"id": "q1", "rank": 3}, {"id": "q2", "rank": 1}]}
        now = [{"id": "q1", "rank": 1}, {"id": "q2", "rank": 1}, {"id": "q3", "rank": None}]
        self.assertEqual(run_eval.compare(prev, now), [("q1", 3, 1)])


if __name__ == "__main__":
    unittest.main()
