"""모델 제공자 선택 테스트 (외부 API·LM Studio 호출 없음)."""
import importlib.util
import unittest
from types import SimpleNamespace
from unittest import mock

import llm_providers as lp


def cfg(**kw):
    base = dict(LLM_PROVIDERS=["local", "openai", "anthropic"], DEFAULT_PROVIDER="local",
                CHAT_MODEL="deepseek-r1-distill-qwen-14b", LM_STUDIO_URL="http://127.0.0.1:1234/v1",
                OPENAI_API_KEY="", OPENAI_MODEL="", OPENAI_BASE_URL="",
                ANTHROPIC_API_KEY="", ANTHROPIC_MODEL="", ALLOW_EXTERNAL_RAG=False)
    base.update(kw)
    return SimpleNamespace(**base)


class ProviderTests(unittest.TestCase):
    def test_default_is_local_and_ready(self):
        p = lp.resolve(None, "rag", cfg())
        self.assertEqual((p.id, p.ready, p.external), ("local", True, False))

    def test_api_providers_need_key_and_model(self):
        ps = {p.id: p for p in lp.providers(cfg())}
        self.assertFalse(ps["openai"].ready)
        self.assertIn("OPENAI_API_KEY", ps["openai"].reason)
        ps = {p.id: p for p in lp.providers(cfg(OPENAI_API_KEY="sk-test", OPENAI_MODEL="m1"))}
        self.assertTrue(ps["openai"].ready)

    def test_anthropic_needs_package(self):
        c = cfg(ANTHROPIC_API_KEY="k", ANTHROPIC_MODEL="m2")
        with mock.patch.object(importlib.util, "find_spec", return_value=None):
            p = {p.id: p for p in lp.providers(c)}["anthropic"]
        self.assertFalse(p.ready)
        self.assertIn("pip install langchain-anthropic", p.reason)

    def test_unknown_or_unready_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            lp.resolve("nope", "chat", cfg())
        with self.assertRaises(ValueError):
            lp.resolve("openai", "chat", cfg())

    def test_external_rag_blocked_unless_allowed(self):
        c = cfg(OPENAI_API_KEY="sk-test", OPENAI_MODEL="m1")
        self.assertEqual(lp.resolve("openai", "chat", c).id, "openai")
        with self.assertRaises(ValueError) as ctx:
            lp.resolve("openai", "rag", c)
        self.assertIn("ALLOW_EXTERNAL_RAG", str(ctx.exception))
        c.ALLOW_EXTERNAL_RAG = True
        self.assertEqual(lp.resolve("openai", "rag", c).id, "openai")

    def test_public_view_has_no_secrets(self):
        c = cfg(OPENAI_API_KEY="sk-SECRET", OPENAI_MODEL="m1")
        text = repr([p.public() for p in lp.providers(c)])
        self.assertNotIn("sk-SECRET", text)

    def test_provider_list_follows_settings(self):
        self.assertEqual([p.id for p in lp.providers(cfg(LLM_PROVIDERS=["local"]))], ["local"])

    @unittest.skipUnless(importlib.util.find_spec("langchain_openai"), "langchain_openai 미설치")
    def test_make_chat_local_and_openai(self):
        c = cfg(OPENAI_API_KEY="sk-test", OPENAI_MODEL="m1", OPENAI_BASE_URL="http://compat.example/v1")
        local = lp.make_chat(lp.resolve("local", "chat", c), c)
        self.assertEqual(local.model_name, "deepseek-r1-distill-qwen-14b")
        api = lp.make_chat(lp.resolve("openai", "chat", c), c)
        self.assertEqual(api.model_name, "m1")


if __name__ == "__main__":
    unittest.main()
