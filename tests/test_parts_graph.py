import unittest

import networkx as nx

import ontology_graph as og
import parts_graph as pg

ZET = [{"lib_id": "Zeta:ZX100", "name": "ZX100", "description": "fixed gadget alpha", "pin_count": 3}]


def onto(status="proposed"):
    g = nx.Graph()
    g.add_node("lib:Zeta", kind="library", label="Zeta")
    og.add_korean_bridge(g, [{"ko": ["가젯 알파"], "lib": ["Zeta"], "review_status": status}])
    return g


def deps(rows=None, backend="es-semantic", **kw):
    calls = []

    def find(q, n):
        calls.append((q, n))
        return (ZET if rows is None else rows), backend
    d = pg.PartsDeps(find=find, **kw)
    d.calls = calls
    return d


class PartsGraphTest(unittest.TestCase):
    def run_graph(self, d, q):
        return pg.ask_parts(pg.build_parts_graph(d), q)

    def test_answers_from_search_results_without_model(self):
        d = deps(ontology=onto(), include_proposed=True)
        r = self.run_graph(d, "가젯 알파 부품 추천해줘")
        self.assertTrue(r["answered"])
        self.assertIn("ZX100", r["answer"])
        self.assertIn("의미 검색", r["answer"])
        self.assertTrue(any("search[es-semantic]" in t for t in r["trace"]))

    def test_proposed_concepts_are_ignored_by_default(self):
        d = deps(ontology=onto("proposed"))
        r = self.run_graph(d, "가젯 알파 부품 추천해줘")
        self.assertFalse(r["answered"])
        self.assertEqual(d.calls, [])

    def test_approved_concepts_are_used(self):
        r = self.run_graph(deps(ontology=onto("approved")), "가젯 알파 부품 추천해줘")
        self.assertTrue(r["answered"])

    def test_no_intent_goes_to_existing_flow(self):
        d = deps(ontology=onto(), include_proposed=True)
        self.assertFalse(self.run_graph(d, "가젯 알파 동작 원리 설명해줘")["answered"])
        self.assertEqual(d.calls, [])

    def test_document_questions_are_not_hijacked(self):
        d = deps(ontology=onto(), include_proposed=True)
        self.assertFalse(self.run_graph(d, "올려 둔 문서에서 가젯 알파 부품 알려줘")["answered"])

    def test_no_results_falls_through(self):
        r = self.run_graph(deps(rows=[], ontology=onto(), include_proposed=True), "가젯 알파 부품 추천")
        self.assertFalse(r["answered"])
        self.assertNotIn("answer", r)

    def test_no_ontology_goes_to_existing_flow(self):
        self.assertFalse(self.run_graph(deps(), "가젯 알파 부품 추천")["answered"])


if __name__ == "__main__":
    unittest.main()
