"""공개 시작 페이지 상태 확인(/api/status)과 CORS 규칙 오프라인 테스트."""
import importlib.util
import unittest
from unittest import mock

import local_status as ls

ORIGIN = "https://yuul-jung.github.io"
CHAT = "deepseek-r1-distill-qwen-14b"
EMB = "text-embedding-qwen3-embedding-4b"

# 2026-11-12 실측: 비전 모델만 올라가 있고 채팅 모델 로드가 실패한 상태
VLM_ONLY = [
    {"id": "qwen3-vl-4b", "type": "vlm", "state": "loaded", "context": 16384},
    {"id": EMB, "type": "embeddings", "state": "not-loaded", "context": None},
    {"id": CHAT, "type": "llm", "state": "not-loaded", "context": None},
]


class CorsTests(unittest.TestCase):
    def test_allowed_origin_get(self):
        h = ls.cors_headers("/api/status", ORIGIN, "GET")
        self.assertEqual(h["Access-Control-Allow-Origin"], ORIGIN)
        self.assertNotIn("Access-Control-Allow-Private-Network", h)

    def test_preflight_with_private_network(self):
        h = ls.cors_headers("/api/status", ORIGIN, "OPTIONS", private_network=True)
        self.assertEqual(h["Access-Control-Allow-Methods"], "GET")
        self.assertEqual(h["Access-Control-Allow-Private-Network"], "true")

    def test_other_paths_and_origins_get_nothing(self):
        self.assertIsNone(ls.cors_headers("/api/chat", ORIGIN, "OPTIONS"))
        self.assertIsNone(ls.cors_headers("/api/documents", ORIGIN, "GET"))
        self.assertIsNone(ls.cors_headers("/api/status", "https://evil.example", "GET"))
        self.assertIsNone(ls.cors_headers("/api/status", None, "GET"))


class StatusTests(unittest.TestCase):
    def test_vlm_blocks_chat_model(self):
        st = ls.build_status(VLM_ONLY, chat_model=CHAT, embedding_model=EMB, es_ok=True, es_version="9.5.6")
        self.assertEqual(st["overall"], "warn")
        chat = next(c for c in st["components"] if c["name"] == "채팅 모델")
        self.assertEqual(chat["level"], "warn")
        self.assertEqual(st["advice"][0]["command"],
                         f"lms unload qwen3-vl-4b && lms load {CHAT}")

    def test_all_good(self):
        states = [dict(m, state="loaded") for m in VLM_ONLY if m["id"] != "qwen3-vl-4b"]
        st = ls.build_status(states, chat_model=CHAT, embedding_model=EMB, es_ok=True, es_version="9.5.6")
        self.assertEqual(st["overall"], "ok")
        self.assertEqual(st["advice"], [])

    def test_lmstudio_and_es_down(self):
        st = ls.build_status(None, chat_model=CHAT, embedding_model=EMB, es_ok=False)
        self.assertEqual(st["overall"], "error")
        cmds = [a["command"] for a in st["advice"]]
        self.assertIn("lms server start", cmds)
        self.assertIn("sudo systemctl start elasticsearch", cmds)

    def test_chat_failure_hint(self):
        self.assertIn("lms unload qwen3-vl-4b", ls.chat_failure_hint(VLM_ONLY, CHAT))
        self.assertIn("lms server start", ls.chat_failure_hint(None, CHAT))

    def test_fetch_model_states_parses_and_handles_failure(self):
        fake = mock.Mock()
        fake.json.return_value = {"data": [{"id": "a", "type": "llm", "state": "loaded",
                                            "loaded_context_length": 4096}]}
        fake.raise_for_status.return_value = None
        with mock.patch.object(ls.requests, "get", return_value=fake) as get:
            rows = ls.fetch_model_states("http://127.0.0.1:1234/v1")
        get.assert_called_once_with("http://127.0.0.1:1234/api/v0/models", timeout=4)
        self.assertEqual(rows, [{"id": "a", "type": "llm", "state": "loaded", "context": 4096}])
        with mock.patch.object(ls.requests, "get", side_effect=ls.requests.ConnectionError()):
            self.assertIsNone(ls.fetch_model_states("http://127.0.0.1:1234/v1"))


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"),
                     "fastapi/httpx 미설치")
class AppEndpointTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import app
        self.app = app
        self.client = TestClient(app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

    def test_status_endpoint_with_cors(self):
        es = mock.Mock()
        es.info.return_value = {"version": {"number": "9.5.6"}}
        with mock.patch.object(self.app, "fetch_model_states", return_value=VLM_ONLY), \
             mock.patch.object(self.app, "es_client", return_value=es):
            r = self.client.get("/api/status", headers={"Origin": ORIGIN})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["access-control-allow-origin"], ORIGIN)
        self.assertEqual(r.json()["overall"], "warn")

    def test_preflight(self):
        r = self.client.options("/api/status", headers={
            "Origin": ORIGIN, "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Private-Network": "true"})
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r.headers["access-control-allow-private-network"], "true")

    def test_chat_not_exposed_cross_origin(self):
        r = self.client.options("/api/chat", headers={"Origin": ORIGIN,
                                                      "Access-Control-Request-Method": "POST"})
        self.assertNotIn("access-control-allow-origin", r.headers)


if __name__ == "__main__":
    unittest.main()
