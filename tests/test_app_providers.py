"""FastAPI: 모델 제공자 목록·거절 응답 테스트 (CI·사용자 PC에서 실행, 외부 호출 없음)."""
import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"),
                     "fastapi/httpx 미설치")
class AppProviderTests(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        from fastapi.testclient import TestClient
        import app
        self.app, self.mock = app, mock
        self.client = TestClient(app.app)

    def test_models_lists_providers_without_keys(self):
        with self.mock.patch.object(self.app, "available_models", return_value=["deepseek-r1-distill-qwen-14b"]):
            data = self.client.get("/api/models").json()
        ids = [p["id"] for p in data["providers"]]
        self.assertIn("local", ids)
        for p in data["providers"]:
            self.assertEqual(set(p), {"id", "label", "model", "ready", "external", "reason"})

    def test_unconfigured_provider_returns_400(self):
        r = self.client.post("/api/chat", json={
            "mode": "chat", "provider": "nope",
            "messages": [{"role": "user", "content": "안녕"}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("제공자", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
