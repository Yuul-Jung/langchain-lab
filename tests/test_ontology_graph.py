"""온톨로지 뼈대 그래프 (서버·모델 없이 실행)."""
import tempfile
import unittest
from pathlib import Path

import ontology_graph as og

PARTS = [
    {"lib_id": "A:x1", "library": "A", "name": "x1", "description": "d1", "keywords": "LDO Regulator, Linear",
     "footprint": "Pkg:SOT-23", "datasheet": "http://d", "extends": "", "pin_count": 3},
    {"lib_id": "A:x2", "library": "A", "name": "x2", "description": "d2", "keywords": "ldo regulator",
     "footprint": "Pkg:SOT-23", "datasheet": "", "extends": "x1", "pin_count": 5},
    {"lib_id": "B:y1", "library": "B", "name": "y1", "description": "", "keywords": "ldo linear regulator",
     "footprint": "", "datasheet": "", "extends": "", "pin_count": 8},
    {"lib_id": "B:z", "library": "B", "name": "z", "description": "", "keywords": "", "footprint": "",
     "datasheet": "", "extends": "missing", "pin_count": 2},
]


def graph(n=2):
    return og.build_graph(PARTS, min_cooccurrence=n)


class OntologyGraphTest(unittest.TestCase):
    def test_split_keywords_lowercases_dedups_and_drops_short(self):
        self.assertEqual(og.split_keywords("LDO, ldo Regulator; x"), ["ldo", "regulator"])

    def test_node_kinds_and_edges(self):
        g = graph()
        self.assertEqual(og.summarize(g)["kinds"], {"library": 2, "part": 4, "keyword": 3, "footprint": 1})
        self.assertTrue(g.has_edge("part:A:x2", "part:A:x1"))  # extends
        self.assertEqual(g.nodes["kw:ldo"]["review_status"], "proposed")

    def test_dangling_extends_leaves_no_blank_node(self):
        self.assertNotIn("part:B:missing", graph())

    def test_related_concepts_ordered_by_cooccurrence(self):
        r = og.related_concepts(graph(), "LDO")
        self.assertEqual(r[0], {"keyword": "regulator", "cooccurrence": 3})
        self.assertIn({"keyword": "linear", "cooccurrence": 2}, r)

    def test_min_cooccurrence_filters_weak_pairs(self):
        r = og.related_concepts(graph(3), "ldo")
        self.assertEqual([x["keyword"] for x in r], ["regulator"])

    def test_parts_for_concept_prefers_datasheet(self):
        self.assertEqual(og.parts_for_concept(graph(), "ldo")[0]["lib_id"], "A:x1")

    def test_expand_query_adds_only_new_neighbors(self):
        self.assertEqual(og.expand_query(graph(), "ldo"), ["regulator", "linear"])
        self.assertEqual(og.expand_query(graph(), "ldo regulator"), ["linear"])
        self.assertEqual(og.expand_query(graph(), "unknownword"), [])

    def test_library_profile(self):
        self.assertEqual(og.library_profile(graph(), "A")[0], {"keyword": "ldo", "parts": 2})

    def test_save_load_roundtrip(self):
        g = graph()
        with tempfile.TemporaryDirectory() as d:
            og.save_graph(g, Path(d) / "o" / "g.json")
            g2 = og.load_graph(Path(d) / "o" / "g.json")
        self.assertEqual(og.summarize(g2), og.summarize(g))


if __name__ == "__main__":
    unittest.main()
