"""채팅 RAG 검색 대상 선택 (서버·모델 없이 실행)."""
import importlib.util
import unittest
from unittest import mock

import chat_search

DOC_HITS = [
    {"document_id": "d1", "chunk_id": "d1-c3", "filename": "과제.pdf", "title": "핀 연결",
     "page": 23, "text": "KEY XK7", "score": 0.93},
    {"document_id": "d1", "chunk_id": "d1-c4", "filename": "과제.pdf", "title": "XDC",
     "page": 24, "text": "PackagePin", "score": 0.88},
]
LAB_HITS = [{"id": "motor_hot", "score": 0.64, "text": "전동기가 과열되면 …"}]


def fakes(doc_hits=DOC_HITS, lab_hits=LAB_HITS):
    up = mock.Mock(return_value=list(doc_hits))
    lab = mock.Mock(return_value=list(lab_hits))
    return up, lab


class SearchForChatTest(unittest.TestCase):
    def test_default_documents_does_not_touch_lab(self):
        up, lab = fakes()
        found = chat_search.search_for_chat("질문", "documents", search_uploaded=up, search_lab=lab)
        self.assertEqual([h["page"] for h in found], [23, 24])
        self.assertEqual(found[0]["source"], "documents")
        lab.assert_not_called()

    def test_documents_falls_back_to_lab_when_nothing_uploaded(self):
        up, lab = fakes(doc_hits=[])
        found = chat_search.search_for_chat("질문", "documents", search_uploaded=up, search_lab=lab)
        self.assertEqual([h["id"] for h in found], ["motor_hot"])

    def test_lab_only(self):
        up, lab = fakes()
        found = chat_search.search_for_chat("질문", "lab", search_uploaded=up, search_lab=lab)
        up.assert_not_called()
        self.assertEqual(found[0]["source"], "lab")

    def test_both_merges_by_score_and_limits(self):
        up, lab = fakes()
        found = chat_search.search_for_chat("질문", "both", search_uploaded=up, search_lab=lab, limit=2)
        self.assertEqual([h["score"] for h in found], [0.93, 0.88])

    def test_unknown_source_is_rejected(self):
        up, lab = fakes()
        with self.assertRaises(ValueError):
            chat_search.search_for_chat("질문", "web", search_uploaded=up, search_lab=lab)

    def test_long_query_is_cut_to_search_limit(self):
        up, lab = fakes()
        chat_search.search_for_chat("가" * 5000, "documents", search_uploaded=up, search_lab=lab)
        self.assertEqual(len(up.call_args.args[0]), chat_search.MAX_QUERY)

    def test_context_has_filename_and_page(self):
        ctx = chat_search.format_context([chat_search.from_uploaded(DOC_HITS[0]),
                                          chat_search.from_lab(LAB_HITS[0])])
        self.assertIn("[자료 1] (과제.pdf · p.23) KEY XK7", ctx)
        self.assertIn("[자료 2] (제1장 실습 문장)", ctx)


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"),
                     "fastapi/httpx 미설치")
class ChatRagEndpointTest(unittest.TestCase):
    def test_rag_mode_answers_from_uploaded_documents(self):
        from fastapi.testclient import TestClient
        import app
        llm = mock.Mock()
        llm.invoke.return_value = mock.Mock(content="XK7에 연결합니다 [자료 1]")
        with mock.patch.object(app, "available_models", return_value=[app.CHAT_MODEL]), \
             mock.patch.object(app, "search_uploaded", return_value=list(DOC_HITS)), \
             mock.patch.object(app, "search_documents", return_value=list(LAB_HITS)) as lab, \
             mock.patch.object(app.settings, "CHAT_RAG_SOURCE", "documents"), \
             mock.patch.object(app, "make_chat", return_value=llm):
            r = TestClient(app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)).post("/api/chat", json={
                "mode": "rag", "provider": "local",
                "messages": [{"role": "user", "content": "KEY 핀은?"}]})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["sources"][0]["page"], 23)
        system_prompt = llm.invoke.call_args.args[0][0][1]
        self.assertIn("(과제.pdf · p.23) KEY XK7", system_prompt)
        lab.assert_not_called()


if __name__ == "__main__":
    unittest.main()
