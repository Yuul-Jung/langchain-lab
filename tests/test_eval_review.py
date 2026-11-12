"""평가 질문 검토 도구 (서버·실제 문서 없이 실행)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "eval_review", Path(__file__).resolve().parent.parent / "scripts" / "eval-review.py")
review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review)

DOC = {"document_id": "abc123" + "0" * 26, "filename": "실습 <안내>.pdf"}
SECTIONS = [{"page": 3, "text": "머리말\n실습 장비는 모두 3대가 필요하다. " + "설명 " * 200},
            {"page": 4, "text": "다른 내용만 있는 쪽이다."}]


def q(qid, **extra):
    item = {"id": qid, "question": "실습 장비는 몇 대 필요해?", "document_id": "abc123", "pages": [3],
            "answer": "3대", "keywords": ["장비"], "status": "draft"}
    item.update(extra)
    return item


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "questions.jsonl"
        self.original = "# 주석은 그대로 둔다\n" + "\n".join(json.dumps(q(i), ensure_ascii=False) for i in ("q01", "q02", "q03")) + "\n"
        self.path.write_text(self.original, encoding="utf-8")

    def statuses(self):
        return {item["id"]: item["status"] for _, item in review.read_lines(self.path) if item}

    def test_approve_changes_only_the_listed_questions_and_keeps_a_backup(self):
        self.assertEqual(review.set_status(self.path, ["q01", "q03"], "approved"), ["q01", "q03"])
        self.assertEqual(self.statuses(), {"q01": "approved", "q02": "draft", "q03": "approved"})
        self.assertTrue(self.path.read_text(encoding="utf-8").startswith("# 주석은 그대로 둔다\n"))
        self.assertEqual(Path(str(self.path) + ".bak").read_text(encoding="utf-8"), self.original)

    def test_unknown_id_changes_nothing(self):
        with self.assertRaises(ValueError):
            review.set_status(self.path, ["q01", "q99"], "approved")
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.original)
        self.assertFalse(Path(str(self.path) + ".bak").exists())

    def test_all_and_back_to_draft(self):
        self.assertEqual(len(review.set_status(self.path, [], "approved", everything=True)), 3)
        self.assertEqual(review.set_status(self.path, ["q02"], "draft"), ["q02"])
        self.assertEqual(self.statuses()["q02"], "draft")
        self.assertEqual(review.set_status(self.path, ["q02"], "draft"), [])     # 이미 그 상태면 바꾸지 않음


class SheetTest(unittest.TestCase):
    def sheet(self, items):
        return review.build_sheet(items, [DOC], lambda doc: SECTIONS)

    def test_sheet_shows_question_answer_and_evidence_excerpt(self):
        page = self.sheet([q("q01")])
        self.assertIn("실습 장비는 몇 대 필요해?", page)
        self.assertIn("실습 장비는 모두 3대가 필요하다.", page)
        self.assertIn("핵심어 있음", page)
        self.assertLess(len(page), 6000)          # 쪽 전체가 아니라 발췌만 들어간다

    def test_evidence_page_without_the_keyword_is_flagged(self):
        page = self.sheet([q("q01", pages=[4])])
        self.assertIn("핵심어 없음 — 확인 필요", page)

    def test_missing_page_and_unknown_document_are_reported_not_hidden(self):
        self.assertIn("이 쪽에서 추출된 본문이 없습니다.", self.sheet([q("q01", pages=[9])]))
        self.assertIn("문서를 찾지 못했습니다", self.sheet([q("q01", document_id="zzz999")]))

    def test_text_from_documents_is_escaped(self):
        page = self.sheet([q("q01", question="<script>alert(1)</script>")])
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("실습 &lt;안내&gt;.pdf", page)

    def test_sheet_counts_approved_questions(self):
        self.assertIn("2문항, 검토 완료 1", self.sheet([q("q01", status="approved"), q("q02")]))


if __name__ == "__main__":
    unittest.main()
