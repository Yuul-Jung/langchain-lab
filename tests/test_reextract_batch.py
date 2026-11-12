"""재추출 승인 유지 · 변경 미리보기 · 일괄 재추출 (Elasticsearch·LM Studio 불필요)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import document_pipeline as dp


def sec(number, title, page=1):
    return {"id": f"s{number:04d}", "source_order": number, "title": title, "page": page,
            "level": 1, "parent_id": None, "provenance": "source_extracted"}


def proposed(src, dst, kind="prerequisite"):
    return {"from": src, "to": dst, "type": kind, "provenance": "rule_inferred", "review_status": "proposed"}


class CarryOverApprovalsTest(unittest.TestCase):
    def carry(self, old_meta, sections, relations=None, order=None, same_content=False):
        classification = {"topic": "t", "review_status": "proposed"}
        relations = relations if relations is not None else []
        sequence = {"section_ids": order or [s["id"] for s in sections], "review_status": "proposed"}
        summary = dp.carry_over_approvals(old_meta, sections, classification, relations, sequence,
                                          same_content=same_content)
        return summary, classification, relations, sequence

    def test_renamed_titles_keep_approvals_when_the_text_is_identical(self):
        # 제목 표기만 바뀐 경우('PDF 3쪽' → 'PDF 3쪽 · 첫 줄'): 본문이 같으면 같은 절이다
        approved = dict(proposed("s0001", "s0002"), review_status="approved")
        old = {"sections": [sec(1, "PDF 1쪽"), sec(2, "PDF 2쪽", page=2)], "relations": [approved],
               "learning_sequence": {"section_ids": ["s0001", "s0002"], "review_status": "approved"}}
        renamed = [sec(1, "PDF 1쪽 · 첫 줄 제목"), sec(2, "PDF 2쪽 · 다른 제목", page=2)]
        summary, _, relations, sequence = self.carry(old, renamed, [proposed("s0001", "s0002")], same_content=True)
        self.assertEqual((summary["same_structure"], summary["learning_sequence"], sequence["review_status"]),
                         (True, "kept", "approved"))
        self.assertEqual((relations[0]["review_status"], summary["relations_kept"]), ("approved", 1))
        # 본문이 달라졌다면 제목이 다른 절은 다른 절로 본다
        summary, _, _, sequence = self.carry(old, renamed, same_content=False)
        self.assertEqual((summary["learning_sequence"], sequence["review_status"]), ("reset", "proposed"))

    def test_identical_text_but_different_page_layout_is_not_treated_as_the_same(self):
        old = {"sections": [sec(1, "가"), sec(2, "나", page=2)],
               "learning_sequence": {"section_ids": ["s0001", "s0002"], "review_status": "approved"}}
        summary, _, _, sequence = self.carry(old, [sec(1, "가"), sec(2, "나", page=3)], same_content=True)
        self.assertEqual((summary["learning_sequence"], sequence["review_status"]), ("reset", "proposed"))

    def test_classification_approval_is_kept(self):
        old = {"sections": [sec(1, "가")], "classification": {"review_status": "approved"}}
        summary, classification, _, _ = self.carry(old, [sec(1, "가"), sec(2, "나")])
        self.assertEqual((summary["classification"], classification["review_status"]), ("kept", "approved"))

    def test_nothing_is_approved_out_of_thin_air(self):
        old = {"sections": [sec(1, "가")], "classification": {"review_status": "proposed"},
               "learning_sequence": {"section_ids": ["s0001"], "review_status": "proposed"}}
        summary, classification, _, sequence = self.carry(old, [sec(1, "가")])
        self.assertEqual((summary["classification"], summary["learning_sequence"]), ("not_approved", "not_approved"))
        self.assertEqual((classification["review_status"], sequence["review_status"]), ("proposed", "proposed"))

    def test_sequence_kept_only_when_structure_and_order_are_the_same(self):
        old = {"sections": [sec(1, "가"), sec(2, "나")],
               "learning_sequence": {"section_ids": ["s0002", "s0001"], "review_status": "approved"}}
        same, _, _, sequence = self.carry(old, [sec(1, "가"), sec(2, "나")], order=["s0002", "s0001"])
        self.assertEqual((same["learning_sequence"], sequence["review_status"]), ("kept", "approved"))
        reordered, _, _, sequence = self.carry(old, [sec(1, "가"), sec(2, "나")], order=["s0001", "s0002"])
        self.assertEqual((reordered["learning_sequence"], sequence["review_status"]), ("reset", "proposed"))
        grown, _, _, sequence = self.carry(old, [sec(1, "가"), sec(2, "나"), sec(3, "다")])
        self.assertEqual((grown["learning_sequence"], sequence["review_status"]), ("reset", "proposed"))

    def test_same_ids_with_different_titles_is_not_the_same_structure(self):
        # 절 ID는 그대로인데 가리키는 절이 달라진 경우: ID만 비교하면 엉뚱한 승인을 유지하게 된다
        old = {"sections": [sec(1, "가"), sec(2, "나")],
               "learning_sequence": {"section_ids": ["s0001", "s0002"], "review_status": "approved"}}
        summary, _, _, sequence = self.carry(old, [sec(1, "머리말"), sec(2, "가")])
        self.assertFalse(summary["same_structure"])
        self.assertEqual(sequence["review_status"], "proposed")

    def test_relation_approval_follows_page_and_title_not_section_id(self):
        approved = dict(proposed("s0001", "s0002"), review_status="approved")
        old = {"sections": [sec(1, "가"), sec(2, "나")], "relations": [approved]}
        # 앞에 절이 하나 생겨 ID가 한 칸씩 밀렸다
        new_sections = [sec(1, "머리말"), sec(2, "가"), sec(3, "나")]
        relations = [proposed("s0002", "s0003"), proposed("s0001", "s0002")]
        summary, _, relations, _ = self.carry(old, new_sections, relations)
        self.assertEqual([r["review_status"] for r in relations], ["approved", "proposed"])
        self.assertEqual((summary["relations_kept"], summary["relations_reset"]), (1, 0))

    def test_approved_relation_that_is_not_proposed_again_counts_as_reset(self):
        approved = dict(proposed("s0001", "s0002"), review_status="approved")
        old = {"sections": [sec(1, "가"), sec(2, "나")], "relations": [approved]}
        summary, _, _, _ = self.carry(old, [sec(1, "가"), sec(2, "다")], [proposed("s0001", "s0002")])
        self.assertEqual((summary["relations_kept"], summary["relations_reset"]), (0, 1))

    def test_relation_type_must_match_and_source_relations_stay_untouched(self):
        approved = dict(proposed("s0001", "s0002", "related"), review_status="approved")
        old = {"sections": [sec(1, "가"), sec(2, "나")], "relations": [approved]}
        fixed = {"from": "s0001", "to": "s0002", "type": "precedes", "provenance": "source_extracted",
                 "review_status": "not_required"}
        summary, _, relations, _ = self.carry(old, [sec(1, "가"), sec(2, "나")], [proposed("s0001", "s0002"), fixed])
        self.assertEqual([r["review_status"] for r in relations], ["proposed", "not_required"])
        self.assertEqual(summary["relations_kept"], 0)

    def test_repeated_titles_on_one_page_are_told_apart(self):
        signatures = dp.section_signatures([sec(1, "표"), sec(2, "표"), sec(3, "표", page=2)])
        self.assertEqual(list(signatures.values()), [(1, "표", 0), (1, "표", 1), (2, "표", 0)])


class PreviewAndBatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        for name, value in (("UPLOAD_DIR", base / "uploads"), ("CATALOG_DIR", base / "catalog")):
            p = patch.object(dp, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.ids = []
        for n in range(3):
            doc = dp.ingest_file(f"doc{n}.md", f"# 문서 {n}\n문서 {n}의 본문은 실습 절차를 설명한다.".encode(),
                                 use_ai=False, index=False)
            self.ids.append(doc["document"]["document_id"])

    def grow(self, document_id):
        """추출 결과가 달라지는 상황을 원본 파일 내용으로 흉내 낸다."""
        stored = dp.UPLOAD_DIR / f"{document_id}.md"
        stored.write_text(stored.read_text(encoding="utf-8") + "\n## 추가 절\n새로 추출되는 절의 본문이다.", encoding="utf-8")

    def catalog_bytes(self):
        return {p.name: p.read_bytes() for p in dp.CATALOG_DIR.glob("*.json")}

    def test_ingest_stores_a_digest_of_the_chunks(self):
        meta = dp.get_document(self.ids[0])
        chunks = dp.make_chunks(dp.extract_sections(dp.UPLOAD_DIR / f"{self.ids[0]}.md"))
        self.assertEqual(meta["chunks_digest"], dp.chunks_digest(chunks))

    def test_preview_changes_nothing_and_compares_with_the_index(self):
        self.grow(self.ids[0])
        before = self.catalog_bytes()
        with patch.object(dp, "indexed_digest", return_value=("예전 색인의 지문", 1, "예전 제목 지문")):
            info = dp.reextract_preview(self.ids[0])
        self.assertEqual(self.catalog_bytes(), before)
        self.assertEqual((info["changed"], info["compared_with"], info["indexed_chunk_count"]), (True, "index", 1))
        self.assertEqual(info["changed_parts"], ["본문", "제목"])
        self.assertEqual((info["stored"]["section_count"], info["new"]["section_count"]), (1, 2))
        self.assertEqual(info["approvals"]["classification"], "not_approved")

    def test_preview_says_unchanged_when_the_index_matches(self):
        chunks = dp.make_chunks(dp.extract_sections(dp.UPLOAD_DIR / f"{self.ids[0]}.md"))
        same = (dp.chunks_digest(chunks), len(chunks), dp.titles_digest(chunks))
        with patch.object(dp, "indexed_digest", return_value=same):
            info = dp.reextract_preview(self.ids[0])
        self.assertEqual((info["changed"], info["changed_parts"]), (False, []))

    def test_preview_notices_documents_whose_titles_alone_changed(self):
        # 본문은 색인과 같고 제목만 달라진 경우 (예: 쪽 제목 규칙이 바뀐 뒤)
        chunks = dp.make_chunks(dp.extract_sections(dp.UPLOAD_DIR / f"{self.ids[0]}.md"))
        only_titles = (dp.chunks_digest(chunks), len(chunks), "예전 제목 지문")
        with patch.object(dp, "indexed_digest", return_value=only_titles):
            info = dp.reextract_preview(self.ids[0])
        self.assertEqual((info["changed"], info["changed_parts"]), (True, ["제목"]))

    def test_preview_flags_documents_missing_from_the_index(self):
        # 새 PC 로 옮긴 직후: 문서 목록과 원본은 있는데 색인에는 이 문서의 청크가 없다
        empty = (dp.chunks_digest([]), 0, dp.titles_digest([]))
        with patch.object(dp, "indexed_digest", return_value=empty):
            info = dp.reextract_preview(self.ids[0])
        self.assertEqual((info["changed"], info["changed_parts"], info["indexed_chunk_count"]), (True, ["색인 없음"], 0))
        # 원본에서 나오는 본문이 그사이 달라졌다면 그것도 함께 알려 준다
        self.grow(self.ids[0])
        with patch.object(dp, "indexed_digest", return_value=empty):
            self.assertEqual(dp.reextract_preview(self.ids[0])["changed_parts"], ["색인 없음", "본문", "제목"])

    def test_missing_index_is_not_confused_with_an_unreachable_server(self):
        class NoIndex:
            class indices:
                @staticmethod
                def exists(index):
                    return False
        with patch.object(dp, "es_client", return_value=NoIndex()):
            self.assertEqual(dp.indexed_digest(self.ids[0])[1], 0)
        with patch.object(dp, "es_client", side_effect=RuntimeError("연결 실패")):
            self.assertIsNone(dp.indexed_digest(self.ids[0]))

    def test_preview_falls_back_to_catalog_digest_then_structure(self):
        with patch.object(dp, "indexed_digest", return_value=None):
            self.assertEqual((dp.reextract_preview(self.ids[0])["changed"], dp.reextract_preview(self.ids[0])["compared_with"]),
                             (False, "catalog"))
            self.grow(self.ids[0])
            self.assertTrue(dp.reextract_preview(self.ids[0])["changed"])
            meta = dp.get_document(self.ids[1])
            meta.pop("chunks_digest")
            dp._write_catalog(meta)
            info = dp.reextract_preview(self.ids[1])
            self.assertEqual((info["changed"], info["compared_with"]), (False, "structure"))

    def test_preview_reports_a_missing_original_instead_of_failing(self):
        (dp.UPLOAD_DIR / f"{self.ids[2]}.md").unlink()
        with patch.object(dp, "indexed_digest", return_value=None):
            rows = dp.reextract_preview_all()
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(1 for r in rows if r.get("error")), 1)

    def test_batch_stops_at_the_first_indexing_failure_and_leaves_the_rest(self):
        untouched = dp.CATALOG_DIR / f"{self.ids[2]}.json"
        before = untouched.read_bytes()
        failure = dp.IndexingFailure("LM_CONNECTION", "embedding", "LM Studio 연결 확인")
        with patch.object(dp, "delete_document_chunks"), \
             patch.object(dp, "_index_chunks", side_effect=[None, failure]):
            outcome = dp.reextract_batch(self.ids)
        self.assertEqual([r["ok"] for r in outcome["results"]], [True, False])
        self.assertEqual((outcome["stopped"], outcome["remaining"]), (True, 1))
        self.assertEqual(outcome["results"][1]["code"], "LM_CONNECTION")
        self.assertEqual(untouched.read_bytes(), before)

    def test_batch_skips_a_missing_original_and_continues(self):
        (dp.UPLOAD_DIR / f"{self.ids[0]}.md").unlink()
        with patch.object(dp, "delete_document_chunks"), patch.object(dp, "_index_chunks"):
            outcome = dp.reextract_batch(self.ids)
        self.assertEqual([r["ok"] for r in outcome["results"]], [False, True, True])
        self.assertEqual((outcome["results"][0]["code"], outcome["stopped"], outcome["remaining"]), ("SOURCE", False, 0))

    def test_batch_reports_kept_approvals_per_document(self):
        meta = dp.get_document(self.ids[0])
        meta["classification"]["review_status"] = "approved"
        meta["learning_sequence"]["review_status"] = "approved"
        dp._write_catalog(meta)
        with patch.object(dp, "delete_document_chunks"), patch.object(dp, "_index_chunks"):
            outcome = dp.reextract_batch([self.ids[0]])
        approvals = outcome["results"][0]["approvals"]
        self.assertEqual((approvals["classification"], approvals["learning_sequence"]), ("kept", "kept"))
        saved = dp.get_document(self.ids[0])
        self.assertEqual(saved["learning_sequence"]["review_status"], "approved")


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"),
                     "fastapi/httpx 미설치")
class MaintenanceApiTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import app
        import document_api
        self.api = document_api
        self.client = TestClient(app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
        self.ready = {"elasticsearch": {"ok": True}, "embedding": {"ok": True}}

    def test_preview_route_counts_changed_and_errors(self):
        rows = [{"document_id": "a", "changed": True}, {"document_id": "b", "changed": False},
                {"document_id": "c", "error": "저장된 원본 파일을 찾지 못했습니다."}]
        with patch.object(self.api, "reextract_preview_all", return_value=rows):
            data = self.client.get("/api/documents/maintenance/reextract-preview").json()
        self.assertEqual((data["changed"], data["errors"], len(data["documents"])), (1, 1, 3))

    def test_batch_does_not_start_when_search_or_embedding_is_down(self):
        down = {"elasticsearch": {"ok": True}, "embedding": {"ok": False}}
        with patch.object(self.api, "indexing_health", return_value=down), \
             patch.object(self.api, "reextract_batch") as batch:
            r = self.client.post("/api/documents/maintenance/reextract-batch", json={})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "NOT_READY")
        batch.assert_not_called()

    def test_batch_without_ids_takes_the_changed_documents(self):
        rows = [{"document_id": "a", "changed": True}, {"document_id": "b", "changed": False},
                {"document_id": "c", "changed": True, "error": "x"}]
        outcome = {"results": [{"document_id": "a", "ok": True}], "stopped": False, "remaining": 0}
        with patch.object(self.api, "indexing_health", return_value=self.ready), \
             patch.object(self.api, "reextract_preview_all", return_value=rows), \
             patch.object(self.api, "reextract_batch", return_value=outcome) as batch:
            data = self.client.post("/api/documents/maintenance/reextract-batch", json={}).json()
        batch.assert_called_once_with(["a"], keep_approvals=True)
        self.assertEqual((data["requested"], data["done"], data["failed"]), (1, 1, 0))

    def test_batch_rejects_an_unknown_document_id_before_touching_anything(self):
        with patch.object(self.api, "indexing_health", return_value=self.ready), \
             patch.object(self.api, "reextract_batch") as batch:
            r = self.client.post("/api/documents/maintenance/reextract-batch",
                                 json={"document_ids": ["0" * 32]})
        self.assertIn(r.status_code, (400, 404))
        batch.assert_not_called()

    def test_single_reextract_passes_the_keep_approvals_choice(self):
        result = {"document": {"index_status": "indexed", "section_count": 1, "chunk_count": 1},
                  "previous": {}, "approvals": {"classification": "reset"}}
        with patch.object(self.api, "_load"), \
             patch.object(self.api, "reextract_document", return_value=result) as one:
            data = self.client.post("/api/documents/" + "a" * 32 + "/reextract?keep_approvals=false").json()
        one.assert_called_once_with("a" * 32, keep_approvals=False)
        self.assertEqual(data["approvals"]["classification"], "reset")


if __name__ == "__main__":
    unittest.main()
