import unittest
from unittest import mock

import graph_views as gv
import settings


class GraphViewsTest(unittest.TestCase):
    def test_structure_has_both_graphs_with_mermaid(self):
        gs = {g["key"]: g for g in gv.structure()}
        self.assertEqual(set(gs), {"parts", "rag"})
        self.assertIn("classify", gs["parts"]["mermaid"])
        self.assertIn("retrieve", gs["rag"]["mermaid"])
        self.assertIn("classify", gs["parts"]["nodes"])
        self.assertTrue(any(e["source"] == "classify" and e["target"] == "search" for e in gs["parts"]["edges"]))
        self.assertTrue(any(e["conditional"] for e in gs["rag"]["edges"]))
        self.assertTrue(gs["parts"]["runnable"])
        self.assertFalse(gs["rag"]["runnable"])

    def test_executed_nodes_from_trace(self):
        trace = ["classify: 부품 추천 질문", "search[es-semantic]: 5건", "answer: 검색된 부품 값으로 답함"]
        self.assertEqual(gv.executed_nodes(trace), ["classify", "search", "answer"])

    def test_highlight_marks_nodes_and_keeps_empty_as_is(self):
        out = gv.highlight("graph TD;\n\ta --> b;", ["a", "b"])
        self.assertIn("class a,b ran", out)
        self.assertEqual(gv.highlight("graph TD;", []), "graph TD;")

    def test_explain_reports_disabled_when_feature_is_off(self):
        with mock.patch.object(settings, "PARTS_SEMANTIC_SEARCH", False):
            r = gv.explain_parts("아무 질문")
        self.assertFalse(r["enabled"])
        self.assertIn("graph", r["mermaid"])

    def test_explain_returns_trace_even_when_not_answered(self):
        fake = {"trace": ["classify: 해당 없음 → 기존 흐름"], "answered": False, "concepts": []}
        with mock.patch.object(gv.parts_chat, "run", return_value=fake):
            r = gv.explain_parts("오늘 날씨")
        self.assertTrue(r["enabled"])
        self.assertFalse(r["answered"])
        self.assertEqual(r["nodes"], ["classify"])
        self.assertIn("class classify ran", r["mermaid"])


if __name__ == "__main__":
    unittest.main()
