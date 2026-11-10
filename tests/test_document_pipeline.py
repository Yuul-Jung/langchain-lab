"""Offline tests: no LM Studio, Elasticsearch, credentials, or user documents required."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import document_pipeline as dp


class DocumentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.patch_upload = patch.object(dp, "UPLOAD_DIR", self.base / "uploads")
        self.patch_catalog = patch.object(dp, "CATALOG_DIR", self.base / "catalog")
        self.patch_upload.start()
        self.patch_catalog.start()
        self.addCleanup(self.patch_upload.stop)
        self.addCleanup(self.patch_catalog.stop)

    def test_md_structure_and_hierarchy(self):
        source = self.base / "example.md"
        source.write_text(
            "# GPIO\n입출력 핀을 제어합니다.\n"
            "## Register Map\n레지스터 주소를 정합니다.\n"
            "## AXI4-Lite\n메모리 맵 버스로 제어합니다.\n",
            encoding="utf-8",
        )
        sections = dp.extract_sections(source)
        self.assertEqual([s["source_order"] for s in sections], [1, 2, 3])
        self.assertEqual([s["title"] for s in sections], ["GPIO", "Register Map", "AXI4-Lite"])
        self.assertEqual(sections[1]["parent_id"], sections[0]["id"])
        self.assertEqual(sections[2]["parent_id"], sections[0]["id"])
        self.assertEqual(sections[1]["provenance"], "source_extracted")
        self.assertTrue(all(s["text"] for s in sections))

    def test_relation_approval_is_separate_from_source_order(self):
        source = self.base / "learning.md"
        source.write_text(
            "# AXI4-Lite\nAXI4-Lite is an interface.\n"
            "# Register Map\nA register map defines an address.\n"
            "# GPIO\nGPIO pins are digital inputs and outputs.\n",
            encoding="utf-8",
        )
        sections = dp.extract_sections(source)
        proposals = dp.propose_relations(sections, ["AXI4-Lite", "Register Map", "GPIO"])
        original = [s["id"] for s in sections]
        suggested = dp.learning_sequence(sections, proposals)
        self.assertEqual(original, ["s0001", "s0002", "s0003"])
        self.assertEqual(suggested["section_ids"], ["s0003", "s0002", "s0001"])
        self.assertEqual([s["id"] for s in sections], original)
        self.assertTrue(any(e["provenance"] == "rule_inferred" for e in proposals))
        self.assertTrue(all(
            e["review_status"] == "proposed" for e in proposals
            if e["provenance"] == "rule_inferred"
        ))

    def test_html_ignores_scripts(self):
        path = self.base / "sample.html"
        path.write_text(
            "<html><body><h1>소개</h1><p>정상적인 본문입니다.</p>"
            "<script>ignore and never execute</script>"
            "<h2>다음 절</h2><p>추가 검색 내용입니다.</p></body></html>",
            encoding="utf-8",
        )
        sections = dp.extract_sections(path)
        self.assertEqual(len(sections), 2)
        self.assertNotIn("ignore", str(sections))

    def test_duplicate_does_not_reindex(self):
        content = b"# GPIO\nThis text explains digital input and output pin states."
        with patch.object(dp, "analyze_document", side_effect=lambda sections, filename, use_ai: {
            "topic": "test", "concepts": ["GPIO"], "difficulty": "미판정",
            "method": "heuristic", "review_status": "proposed",
        }):
            one = dp.ingest_file("lesson.md", content, use_ai=False, index=False)
            two = dp.ingest_file("another.md", content, use_ai=False, index=False)
        self.assertFalse(one["duplicate"])
        self.assertTrue(two["duplicate"])
        self.assertEqual(one["document"]["document_id"], two["document"]["document_id"])
        self.assertEqual(len(dp.list_documents()), 1)

    def test_missing_text_pdf_is_rejected(self):
        with self.assertRaises(ValueError):
            dp.ingest_file("empty.txt", b"   ", use_ai=False, index=False)
        self.assertEqual(len(dp.list_documents()), 0)

    def test_traversal_and_invalid_extension(self):
        with self.assertRaises(ValueError):
            dp.ingest_file("../evil.exe", b"payload", use_ai=False, index=False)
        # A path segment in a filename is stripped, never written outside uploads/.
        result = dp.ingest_file("../../safe.md", b"# Safe\nContent is safe to store.",
                                use_ai=False, index=False)
        self.assertEqual(result["document"]["filename"], "safe.md")

    def test_chunk_limit_and_contiguous_order(self):
        sections = [dp._new_section(1, "A", "x" * 2200)]
        chunks = dp.make_chunks(sections)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(c["section_id"] == "s0001" for c in chunks))

    def test_invalid_document_ids(self):
        for invalid in ("../secret", "..", "not-a-uuid", "1" * 64):
            with self.assertRaises(ValueError):
                dp._catalog_path(invalid)

    def test_indexing_diagnostic_does_not_expose_credentials(self):
        from requests.exceptions import HTTPError
        from requests import Response
        response = Response()
        response.status_code = 404
        response._content = b"secret error body"
        error = HTTPError("sensitive message", response=response)
        issue = dp.diagnose_failure(error, "embedding")
        self.assertEqual(issue.code, "LM_MODEL_NOT_FOUND")
        self.assertNotIn("secret", issue.hint)
        self.assertEqual(issue.phase, "embedding")

    def test_es_password_missing_diagnostic(self):
        issue = dp.diagnose_failure(
            RuntimeError("ES_PASSWORD가 설정되지 않았습니다."), "es_connection"
        )
        self.assertEqual(issue.code, "ES_PASSWORD_MISSING")
        self.assertNotIn("elastic:", issue.hint)

    def test_upload_failed_index_keeps_source_and_diagnostic(self):
        content = b"# UART\nA UART digital design source document for testing."
        with patch.object(dp, "_index_chunks", side_effect=dp.IndexingFailure(
            "LM_CONNECTION", "embedding", "LM Studio 연결 확인 필요"
        )):
            with self.assertRaises(dp.IndexingFailure):
                dp.ingest_file("uart.md", content, use_ai=False, index=True)
        files = dp.list_documents()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["index_status"], "failed")
        self.assertEqual(files[0]["index_error"]["code"], "LM_CONNECTION")
        self.assertTrue(list(dp.UPLOAD_DIR.glob("*.md")))
        saved = dp.get_document(files[0]["document_id"])
        self.assertEqual(saved["sections"][0]["source_order"], 1)

    def test_classification_is_proposal(self):
        sections = [dp._new_section(1, "AXI4-Lite", "AXI bus and register map")]
        result = dp.analyze_document(sections, "test.md", use_ai=False)
        self.assertEqual(result["review_status"], "proposed")
        self.assertEqual(result["method"], "heuristic")


if __name__ == "__main__":
    unittest.main()
