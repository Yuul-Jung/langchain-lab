import unittest
from unittest import mock

import reranker
import settings

HITS = [{"text": "alpha", "score": 0.9}, {"text": "beta", "score": 0.8}, {"text": "gamma", "score": 0.7}]


class RerankerTest(unittest.TestCase):
    def test_reorders_head_by_scorer_and_keeps_tail_below(self):
        out = reranker.rerank("q", HITS, pool=2, scorer=lambda q, texts: [-1.0, 3.0])
        self.assertEqual([h["text"] for h in out], ["beta", "alpha", "gamma"])
        self.assertEqual(out[0]["pre_rerank_score"], 0.8)
        self.assertGreater(out[0]["score"], out[1]["score"])
        self.assertLess(out[2]["score"], out[1]["score"])          # 재순위 안 한 것은 아래로

    def test_scorer_failure_keeps_original_order(self):
        def boom(q, texts):
            raise RuntimeError("model broke")
        self.assertIs(reranker.rerank("q", HITS, pool=3, scorer=boom), HITS)
        self.assertIs(reranker.rerank("q", HITS, pool=3, scorer=lambda q, t: [1.0]), HITS)   # 개수가 안 맞음

    def test_missing_model_falls_back_silently(self):
        with mock.patch.dict(reranker._state, {"loaded": True, "model": None}, clear=True):
            self.assertIs(reranker.rerank("q", HITS, pool=3), HITS)

    def test_load_failure_is_cached_and_returns_none(self):
        with mock.patch.dict(reranker._state, {}, clear=True), \
             mock.patch.object(settings, "DOCUMENT_RERANKER_MODEL", "/nonexistent/model"):
            self.assertIsNone(reranker._load())
            self.assertIn("loaded", reranker._state)

    def test_off_by_default(self):
        self.assertFalse(settings.DOCUMENT_RERANKER)


if __name__ == "__main__":
    unittest.main()
