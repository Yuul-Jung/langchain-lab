import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import document_pipeline as dp

DOC = "a" * 32


class FakeIndices:
    def get(self, index):
        return {"langchain_documents_v1": {}, "langchain_mixed_v1": {}, ".hidden": {}}


class FakeEs:
    def __init__(self, fail=False):
        self.indices, self.calls, self.fail = FakeIndices(), [], fail

    def delete_by_query(self, index, **kw):
        if self.fail:
            raise ConnectionError("es down")
        self.calls.append((index, kw["query"]))
        return {"deleted": 3 if index == "langchain_documents_v1" else 0}


class DeleteDocumentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cat, self.up = root / "cat", root / "up"
        self.cat.mkdir(); self.up.mkdir()
        (self.cat / f"{DOC}.json").write_text(json.dumps({"document_id": DOC, "filename": "x.pdf"}))
        (self.up / f"{DOC}.pdf").write_bytes(b"%PDF")
        (self.up / ("b" * 32 + ".pdf")).write_bytes(b"%PDF")       # 다른 문서는 남아야 한다
        self.patches = [mock.patch.object(dp, "CATALOG_DIR", self.cat), mock.patch.object(dp, "UPLOAD_DIR", self.up)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_removes_chunks_everywhere_then_file_then_catalog(self):
        es = FakeEs()
        with mock.patch.object(dp, "es_client", return_value=es):
            r = dp.delete_document(DOC)
        self.assertEqual(r["chunks_deleted"], {"langchain_documents_v1": 3})
        self.assertEqual(sorted(i for i, _ in es.calls), ["langchain_documents_v1", "langchain_mixed_v1"])   # 숨은 색인 제외
        self.assertEqual(r["files_deleted"], [f"{DOC}.pdf"])
        self.assertFalse((self.cat / f"{DOC}.json").exists())
        self.assertTrue((self.up / ("b" * 32 + ".pdf")).exists())

    def test_search_engine_failure_keeps_catalog_and_file_for_retry(self):
        with mock.patch.object(dp, "es_client", return_value=FakeEs(fail=True)):
            with self.assertRaises(ConnectionError):
                dp.delete_document(DOC)
        self.assertTrue((self.cat / f"{DOC}.json").exists())
        self.assertTrue((self.up / f"{DOC}.pdf").exists())

    def test_unknown_or_invalid_id(self):
        with self.assertRaises(FileNotFoundError):
            dp.delete_document("c" * 32)
        with self.assertRaises(ValueError):
            dp.delete_document("../etc/passwd")


if __name__ == "__main__":
    unittest.main()
