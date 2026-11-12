"""이미 색인된 문서의 원본 재추출·재색인 테스트 (Elasticsearch·LM Studio 불필요)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import document_pipeline as dp


class ReextractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        for name, value in (("UPLOAD_DIR", base / "uploads"), ("CATALOG_DIR", base / "catalog")):
            p = patch.object(dp, name, value)
            p.start()
            self.addCleanup(p.stop)
        doc = dp.ingest_file("uart.md", "# UART\n수신 회로 설명.".encode(), use_ai=False, index=False)
        self.doc_id = doc["document"]["document_id"]
        # 사람이 분류를 승인했고 색인도 된 상태라고 가정
        meta = dp.get_document(self.doc_id)
        meta["classification"]["review_status"] = "approved"
        meta["index_status"] = "indexed"
        dp._write_catalog(meta)
        # 추출 방식이 개선되어 원본에서 절이 하나 더 나오는 상황을 원본 파일로 흉내 낸다
        stored = dp.UPLOAD_DIR / f"{self.doc_id}.md"
        self.original = "# UART\n수신 회로 설명.\n## 오버샘플링\n16배로 샘플링한다."
        stored.write_text(self.original, encoding="utf-8")

    def test_reextract_rebuilds_chunks_and_resets_review(self):
        with patch.object(dp, "delete_document_chunks") as delete, \
             patch.object(dp, "_index_chunks") as index:
            result = dp.reextract_document(self.doc_id)
        delete.assert_called_once_with(self.doc_id)
        index.assert_called_once()
        doc = result["document"]
        self.assertEqual(result["previous"]["section_count"], 1)
        self.assertEqual(doc["section_count"], 2)
        self.assertEqual(doc["index_status"], "indexed")
        self.assertEqual(doc["classification"]["review_status"], "proposed")
        self.assertIn("reextracted_at", doc)
        saved = dp.get_document(self.doc_id)
        self.assertEqual([s["title"] for s in saved["sections"]], ["UART", "오버샘플링"])

    def test_index_failure_is_recorded_and_source_kept(self):
        with patch.object(dp, "delete_document_chunks"), \
             patch.object(dp, "_index_chunks", side_effect=dp.IndexingFailure(
                 "LM_CONNECTION", "embedding", "LM Studio 연결 확인")):
            with self.assertRaises(dp.IndexingFailure):
                dp.reextract_document(self.doc_id)
        saved = dp.get_document(self.doc_id)
        self.assertEqual(saved["index_status"], "failed")
        self.assertEqual(saved["index_error"]["code"], "LM_CONNECTION")
        stored = dp.UPLOAD_DIR / f"{self.doc_id}.md"
        self.assertEqual(stored.read_text(encoding="utf-8"), self.original)

    def test_delete_failure_becomes_diagnostic(self):
        with patch.object(dp, "delete_document_chunks", side_effect=RuntimeError("ES_PASSWORD가 설정되지 않았습니다.")), \
             patch.object(dp, "_index_chunks") as index:
            with self.assertRaises(dp.IndexingFailure) as ctx:
                dp.reextract_document(self.doc_id)
        index.assert_not_called()
        self.assertEqual(ctx.exception.code, "ES_PASSWORD_MISSING")
        self.assertEqual(dp.get_document(self.doc_id)["index_status"], "failed")

    def test_missing_source_file(self):
        (dp.UPLOAD_DIR / f"{self.doc_id}.md").unlink()
        with self.assertRaises(FileNotFoundError):
            dp.reextract_document(self.doc_id)


if __name__ == "__main__":
    unittest.main()
