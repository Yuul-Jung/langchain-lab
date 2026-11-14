import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("cpt", Path(__file__).resolve().parent.parent / "scripts" / "check-parts-taxonomy.py")
cpt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpt)

TAX = {
    "domains": [{"id": "power", "definition": "d1"}, {"id": "analog", "definition": "d2"}],
    "functions": [{"id": "ldo", "domain": "power"}, {"id": "reference", "domain": "analog"}, {"id": "resistor", "domain": "analog"}],
    "libraries": {"Reg": {"function": "ldo", "status": "confirmed", "approver": "delegated: a + b", "also_ok": []},
                  "Ref": {"function": "reference", "status": "proposed", "approver": "-", "also_ok": ["power"]}},
    "generic": {"Device": {"R": {"function": "resistor", "status": "rule"}}},
    "unmapped": ["Odd"],
}
PARTS = [{"library": "Reg", "name": "A"}, {"library": "Reg", "name": "B"}, {"library": "Ref", "name": "C"},
         {"library": "Device", "name": "R_Small"}, {"library": "Device", "name": "R"}, {"library": "Odd", "name": "Z"}]


def run(tax=TAX, parts=PARTS, ref=None, ids=None):
    return cpt.validate(copy.deepcopy(tax), parts, ref, ids)


class TaxonomyCheckTest(unittest.TestCase):
    def test_clean_taxonomy_passes_and_reports_coverage(self):
        r = run()
        self.assertEqual(r["problems"], {"check1": [], "check2": [], "check3": []})
        self.assertEqual(r["coverage"]["confirmed"][0], 2)
        self.assertEqual(r["coverage"]["rule"][0], 2)
        self.assertEqual(r["coverage"]["unmapped"][0], 1)
        self.assertTrue(r["check3_skipped"])

    def test_unknown_missing_and_duplicate_libraries_fail(self):
        r = run(parts=PARTS + [{"library": "New", "name": "N"}])
        self.assertTrue(any("분류 체계에 없는" in m for m in r["problems"]["check1"]))
        r = run(parts=[p for p in PARTS if p["library"] != "Ref"])
        self.assertTrue(any("카탈로그에 없는" in m for m in r["problems"]["check1"]))
        t = copy.deepcopy(TAX); t["unmapped"].append("Reg")
        self.assertTrue(any("여러 곳" in m for m in run(tax=t)["problems"]["check1"]))

    def test_generic_part_without_rule_fails(self):
        r = run(parts=PARTS + [{"library": "Device", "name": "Xyz"}])
        self.assertTrue(any("이름 규칙에 안 걸림" in m for m in r["problems"]["check1"]))
        self.assertEqual(cpt.match_rule({"R": 1, "*": 2}, "Q_x"), 2)
        self.assertEqual(cpt.match_rule({"R": 1}, "RotaryEncoder"), None)      # 'R' 이 'RotaryEncoder' 를 삼키지 않는다

    def test_confirmed_needs_reviewer_label_and_functions_must_exist(self):
        t = copy.deepcopy(TAX); t["libraries"]["Reg"]["approver"] = "-"
        self.assertTrue(any("확인자" in m for m in run(tax=t)["problems"]["check2"]))
        t = copy.deepcopy(TAX); t["libraries"]["Reg"]["function"] = "nope"
        self.assertTrue(any("없는 기능" in m for m in run(tax=t)["problems"]["check2"]))
        t = copy.deepcopy(TAX); t["libraries"]["Ref"]["also_ok"] = ["analog"]       # 자기 도메인은 also_ok 가 아님
        self.assertTrue(any("also_ok" in m for m in run(tax=t)["problems"]["check2"]))
        t = copy.deepcopy(TAX); t["domains"][0]["definition"] = ""
        self.assertTrue(any("정의 없음" in m for m in run(tax=t)["problems"]["check2"]))

    def test_check3_only_when_reference_and_raw_exist(self):
        ref = {"libraries": {"Reg": 5}, "functions": {"ldo": [5, 99]}}
        r = run(ref=ref, ids={5})
        self.assertFalse(r["check3_skipped"])
        self.assertTrue(any("99" in m for m in r["problems"]["check3"]))
        self.assertTrue(run(ref=ref, ids=None)["check3_skipped"])
        self.assertTrue(run(ref=None, ids={5})["check3_skipped"])


if __name__ == "__main__":
    unittest.main()
