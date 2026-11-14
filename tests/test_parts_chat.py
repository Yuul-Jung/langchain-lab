import unittest
from unittest import mock

import networkx as nx

import ontology_graph as og
import parts_chat
import settings

CAT = [{"lib_id": "Zeta:ZX100", "name": "ZX100", "description": "fixed gadget alpha", "keywords": "gadget alpha",
        "library": "Zeta", "pins": [], "pin_count": 3}]


class FakeEs:
    def search(self, index, **body):
        return {"hits": {"hits": [{"_source": CAT[0]}]}}


def onto(status="proposed"):
    g = nx.Graph()
    g.add_node("lib:Zeta", kind="library", label="Zeta")
    og.add_korean_bridge(g, [{"ko": ["가젯 알파"], "lib": ["Zeta"], "review_status": status}])
    return g


def ask(q="가젯 알파 부품 추천", **flags):
    with mock.patch.object(settings, "PARTS_SEMANTIC_SEARCH", flags.get("sem", True)), \
         mock.patch.object(settings, "PARTS_ONTOLOGY_INCLUDE_PROPOSED", flags.get("prop", False)), \
         mock.patch.object(parts_chat, "TERM_VECS_PATH", parts_chat.TERM_VECS_PATH.with_name("nope.npz")):   # 이 PC의 data/ 파일에 기대지 않는다
        return parts_chat.answer(q, es=FakeEs(), embed=lambda s: [0.1], ontology=flags.get("onto", onto()), catalog=CAT)


class PartsChatTest(unittest.TestCase):
    def test_off_by_default_returns_none(self):
        self.assertIsNone(ask(sem=False, prop=True))

    def test_proposed_concepts_need_explicit_flag(self):
        self.assertIsNone(ask(prop=False))
        out = ask(prop=True)
        self.assertIn("ZX100", out["answer"])
        self.assertEqual(out["backend"], "es-semantic")

    def test_approved_concepts_work_without_proposed_flag(self):
        self.assertIsNotNone(ask(prop=False, onto=onto("approved")))

    def test_missing_ontology_file_returns_none(self):
        with mock.patch.object(settings, "PARTS_SEMANTIC_SEARCH", True), \
             mock.patch.object(parts_chat, "GRAPH_PATH", parts_chat.GRAPH_PATH.with_name("nope.json")), \
             mock.patch.dict(parts_chat._cache, {}, clear=True):
            self.assertIsNone(parts_chat.answer("가젯 알파 부품 추천", es=FakeEs(), embed=lambda s: [0.1], catalog=CAT))

    def test_unrelated_question_returns_none(self):
        self.assertIsNone(ask("오늘 날씨 어때", prop=True))


if __name__ == "__main__":
    unittest.main()
