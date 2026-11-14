import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import networkx as nx

import ontology_graph as og
import parts_chat
import parts_log
import settings

CAT = [{"lib_id": "Zeta:ZX100", "name": "ZX100", "description": "fixed gadget alpha", "keywords": "gadget alpha",
        "library": "Zeta", "pins": [], "pin_count": 3}]


class FakeEs:
    def search(self, index, **body):
        return {"hits": {"hits": [{"_source": CAT[0]}]}}


def onto():
    g = nx.Graph()
    g.add_node("lib:Zeta", kind="library", label="Zeta")
    og.add_korean_bridge(g, [{"ko": ["가젯 알파"], "lib": ["Zeta"], "review_status": "proposed"}])
    return g


class PartsLogTest(unittest.TestCase):
    def ask(self, q, path, log=True, server=True):
        with mock.patch.object(settings, "PARTS_SEMANTIC_SEARCH", True), \
             mock.patch.object(settings, "PARTS_ONTOLOGY_INCLUDE_PROPOSED", True), \
             mock.patch.object(settings, "PARTS_ROUTE_LOG", log), \
             mock.patch.object(parts_log, "in_server_process", return_value=server), \
             mock.patch.object(parts_log, "DEFAULT_PATH", path), \
             mock.patch.object(parts_chat, "TERM_VECS_PATH", path.with_name("nope.npz")):
            return parts_chat.answer(q, es=FakeEs(), embed=lambda s: [0.1], ontology=onto(), catalog=CAT)

    def test_handled_and_unhandled_questions_are_both_logged(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "log.jsonl"
            self.assertIsNotNone(self.ask("가젯 알파 부품 추천", path))
            self.assertIsNone(self.ask("오늘 날씨 어때", path))
            rows = parts_log.read(path)
            self.assertEqual([r["handled"] for r in rows], [True, False])
            self.assertEqual(rows[0]["backend"], "es-semantic")
            self.assertEqual(rows[0]["libraries"], ["Zeta"])
            self.assertEqual(rows[0]["concepts"], ["가젯 알파"])
            self.assertEqual(rows[1]["question"], "오늘 날씨 어때")

    def test_scripts_are_never_logged_even_if_setting_is_on(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            self.assertIsNotNone(self.ask("가젯 알파 부품 추천", path, log=True, server=False))   # 답은 그대로
            self.assertFalse(path.exists())                                                      # 기록은 없음

    def test_server_detection_uses_uvicorn_module(self):
        with mock.patch.dict("sys.modules", {"uvicorn": object()}):
            self.assertTrue(parts_log.in_server_process())
        import sys
        saved = sys.modules.pop("uvicorn", None)
        try:
            self.assertFalse(parts_log.in_server_process())
        finally:
            if saved is not None:
                sys.modules["uvicorn"] = saved

    def test_off_switch_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            self.ask("가젯 알파 부품 추천", path, log=False)
            self.assertFalse(path.exists())

    def test_write_failure_never_breaks_chat(self):
        with tempfile.TemporaryDirectory() as d:
            blocker = Path(d) / "file"
            blocker.write_text("x")
            self.assertFalse(parts_log.record("q", {"answered": True}, path=blocker / "log.jsonl"))   # 폴더를 만들 수 없음
            self.assertIsNotNone(self.ask("가젯 알파 부품 추천", blocker / "log.jsonl"))              # 답은 그대로 나온다

    def test_old_entries_are_dropped_when_file_grows_too_big(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            with mock.patch.object(parts_log, "MAX_BYTES", 2000), mock.patch.object(parts_log, "KEEP_ENTRIES", 5):
                for i in range(60):
                    parts_log.record(f"질문 {i}", {"answered": False}, path=path)
            rows = parts_log.read(path)
            self.assertLessEqual(len(rows), 60)
            self.assertLess(len(rows), 40)                                  # 상한이 실제로 동작
            self.assertEqual(rows[-1]["question"], "질문 59")                  # 가장 최근 기록은 남는다
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_read_skips_broken_lines_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            self.assertEqual(parts_log.read(path), [])
            path.write_text(json.dumps({"handled": True}) + "\n{깨진 줄\n", encoding="utf-8")
            self.assertEqual(len(parts_log.read(path)), 1)


class FeedbackTest(unittest.TestCase):
    def test_record_returns_id_and_feedback_refers_to_it(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            rid = parts_log.record("가젯 알파 부품 추천", {"answered": True}, path=path)
            self.assertRegex(rid, r"^[0-9a-f]{12}$")
            self.assertTrue(parts_log.feedback(rid, "not_parts", path=path))
            self.assertFalse(parts_log.feedback(rid, "anything_else", path=path))
            rows = parts_log.read(path)
            self.assertEqual(rows[0]["id"], rid)
            self.assertEqual(rows[1], {**rows[1], "type": "feedback", "ref": rid, "label": "not_parts"})
            self.assertNotIn("question", rows[1])            # 평가 줄에는 질문 원문을 다시 쓰지 않는다
            self.assertEqual(len(rows), 2)

    def test_endpoint_saves_only_known_labels_and_valid_ids(self):
        from fastapi.testclient import TestClient
        import app
        client = TestClient(app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            with mock.patch.object(parts_log, "DEFAULT_PATH", path), mock.patch.object(settings, "PARTS_ROUTE_LOG", True):
                ok = client.post("/api/parts/feedback", json={"log_id": "a1b2c3d4e5f6", "label": "missed_parts"})
                self.assertEqual(ok.json(), {"saved": True})
                self.assertEqual(client.post("/api/parts/feedback", json={"log_id": "a1b2c3d4e5f6", "label": "x"}).status_code, 400)
                self.assertEqual(client.post("/api/parts/feedback", json={"log_id": "../etc", "label": "correct"}).status_code, 422)
            with mock.patch.object(parts_log, "DEFAULT_PATH", path), mock.patch.object(settings, "PARTS_ROUTE_LOG", False):
                self.assertEqual(client.post("/api/parts/feedback", json={"log_id": "a1b2c3d4e5f6", "label": "correct"}).json(), {"saved": False})
            self.assertEqual(len(parts_log.read(path)), 1)


if __name__ == "__main__":
    unittest.main()
