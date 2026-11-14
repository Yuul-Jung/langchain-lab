import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("bpt", Path(__file__).resolve().parent.parent / "scripts" / "build-parts-tree.py")
bpt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bpt)

TAX = {
    "domains": [{"id": "d1", "ko": "도메인1", "en": "D1", "definition": "x"}, {"id": "d2", "ko": "도메인2", "en": "D2", "definition": "y"}],
    "functions": [{"id": "f1", "domain": "d1", "ko": "기능1", "en": "F1"}, {"id": "f2", "domain": "d2", "ko": "기능2", "en": "F2"}],
    "libraries": {"Lib": {"function": "f1", "status": "confirmed", "mixed": True, "also_functions": ["f2"],
                          "part_rules": {"Fan": {"function": "f2", "ko": "팬"}}}},
    "generic": {"Gen": {"R": {"function": "f2", "ko": "저항", "status": "rule"}}}, "unmapped": ["Odd"],
}


class TreeBuildTest(unittest.TestCase):
    def test_part_rules_split_and_mixed_chip_and_generic(self):
        parts = {"Lib": [{"name": "Fan_3pin"}, {"name": "Other"}], "Gen": [{"name": "R_Small"}, {"name": "Q"}], "Odd": [{"name": "Z"}]}
        out = bpt.build(TAX, parts, {})
        d1 = next(d for d in out["domains"] if d["id"] == "d1")
        d2 = next(d for d in out["domains"] if d["id"] == "d2")
        lib = d1["branches"][0]["libraries"][0]
        self.assertEqual((lib["kicad"], lib["parts"], lib["mixed"]), ("Lib", 1, ["기능2"]))
        names = {l["kicad"]: l for b in d2["branches"] for l in b["libraries"]}
        self.assertEqual(names["Lib [팬]"]["parts"], 1)
        self.assertEqual(names["Lib [팬]"]["status"], "이름 규칙")
        self.assertEqual(names["Gen [저항]"]["parts"], 1)                  # 'Q' 는 규칙이 없어 빠진다
        self.assertEqual(out["unmapped"][0]["kicad"], "Odd")


if __name__ == "__main__":
    unittest.main()
