import unittest

import kicad_parts as kp

PARTS = [
    {"lib_id": "Zeta:ZX100", "name": "ZX100", "description": "fixed gadget alpha", "keywords": "gadget alpha",
     "library": "Zeta", "pins": [], "pin_count": 0},
    {"lib_id": "Zeta:QW200", "name": "QW200", "description": "adjustable gadget beta", "keywords": "gadget beta",
     "library": "Zeta", "pins": [], "pin_count": 0},
]


class FakeEs:
    def __init__(self, rows=None, fail=False):
        self.rows, self.fail, self.calls = rows, fail, []

    def search(self, index, **body):
        self.calls.append((index, body))
        if self.fail:
            raise RuntimeError("down")
        return {"hits": {"hits": [{"_source": r} for r in (self.rows or [])]}}


class FindPartsTest(unittest.TestCase):
    def test_off_by_default_uses_file_without_touching_es(self):
        es = FakeEs(rows=[PARTS[0]])
        rows, how = kp.find_parts("gadget", PARTS, 5, embed=lambda q: [0.1], es=es)
        self.assertEqual(how, "file")
        self.assertEqual(es.calls, [])
        self.assertTrue(rows)

    def test_semantic_when_on(self):
        es = FakeEs(rows=[PARTS[1]])
        rows, how = kp.find_parts("베타 가젯", PARTS, 5, semantic=True, embed=lambda q: [0.1, 0.2], es=es)
        self.assertEqual(how, "es-semantic")
        self.assertEqual(rows[0]["lib_id"], "Zeta:QW200")
        index, body = es.calls[0]
        self.assertEqual(index, kp.ES_PARTS_V2)
        self.assertEqual(body["knn"]["query_vector"], [0.1, 0.2])
        self.assertIn("embedding", body["_source"]["excludes"])

    def test_falls_back_when_es_fails(self):
        rows, how = kp.find_parts("gadget", PARTS, 5, semantic=True, embed=lambda q: [0.1], es=FakeEs(fail=True))
        self.assertEqual(how, "file")
        self.assertTrue(rows)

    def test_falls_back_when_embedding_fails(self):
        def boom(q):
            raise RuntimeError("no model")
        _, how = kp.find_parts("gadget", PARTS, 5, semantic=True, embed=boom, es=FakeEs(rows=[PARTS[0]]))
        self.assertEqual(how, "file")

    def test_falls_back_when_index_returns_nothing(self):
        _, how = kp.find_parts("gadget", PARTS, 5, semantic=True, embed=lambda q: [0.1], es=FakeEs(rows=[]))
        self.assertEqual(how, "file")

    def test_empty_catalog_gives_empty_list(self):
        rows, how = kp.find_parts("gadget", [], 5)
        self.assertEqual((rows, how), ([], "file"))


if __name__ == "__main__":
    unittest.main()
