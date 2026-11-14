import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("cpt", Path(__file__).resolve().parent.parent / "scripts" / "check-parts-taxonomy.py")
cpt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpt)

TAX = {
    "domains": [{"id": "power", "definition": "d1"}, {"id": "analog", "definition": "d2"}],
    "functions": [{"id": "ldo", "domain": "power", "kind": "ic"}, {"id": "reference", "domain": "analog", "kind": "ic"},
                  {"id": "resistor", "domain": "analog", "kind": "electromech"}],
    "libraries": {"Reg": {"function": "ldo", "status": "confirmed", "approver": "delegated: a + b", "also_ok": []},
                  "Ref": {"function": "reference", "status": "proposed", "approver": "-", "also_ok": []}},
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

    def test_mixed_library_schema_and_part_rules(self):
        t = copy.deepcopy(TAX)
        t["functions"].append({"id": "fan", "domain": "power", "kind": "module"})
        t["libraries"]["Ref"].update({"mixed": True, "also_functions": ["ldo"], "also_ok": ["power"],
                                      "part_rules": {"Fan": {"function": "fan"}}})
        r = run(tax=t, parts=PARTS + [{"library": "Ref", "name": "Fan_3pin"}, {"library": "Ref", "name": "Fanatic"}])
        self.assertEqual(r["problems"]["check2"], [])
        self.assertEqual(r["coverage"]["rule"][0], 3)                     # Device 2 + Fan_3pin ('Fanatic' 은 규칙에 안 걸림)
        t["libraries"]["Ref"]["also_ok"] = []                              # also_functions 와 도메인이 어긋남
        self.assertTrue(any("도메인과 다름" in m for m in run(tax=t)["problems"]["check2"]))
        t["libraries"]["Ref"]["mixed"] = False
        self.assertTrue(any("mixed 표시가 없음" in m for m in run(tax=t)["problems"]["check2"]))
        t = copy.deepcopy(TAX); t["libraries"]["Reg"]["mixed"] = True      # 근거 없는 mixed
        self.assertTrue(any("mixed 인데" in m for m in run(tax=t)["problems"]["check2"]))
        rules = {"NUCLEO144": 1, "RaspberryPi_Pico": 2}
        self.assertEqual(cpt.match_rule(rules, "RaspberryPi_Pico_W_Debug", "_-"), 2)
        self.assertIsNone(cpt.match_rule(rules, "RaspberryPi-CM3", "_-"))      # 컴퓨트 모듈은 보드 규칙에 안 걸린다
        self.assertEqual(cpt.match_rule({"NUCLEO144": 1}, "NUCLEO144-F207ZG", "_-"), 1)

    def test_function_kind_is_required_valid_and_fits_the_domain(self):
        t = copy.deepcopy(TAX); del t["functions"][0]["kind"]
        self.assertTrue(any("kind 가 없음" in m for m in run(tax=t)["problems"]["check2"]))
        t = copy.deepcopy(TAX); t["functions"][0]["kind"] = "gadget"
        self.assertTrue(any("허용되지 않는 kind" in m for m in run(tax=t)["problems"]["check2"]))
        t = copy.deepcopy(TAX)
        t["domains"].append({"id": "passive", "definition": "p"})
        t["functions"].append({"id": "res", "domain": "passive", "kind": "ic"})     # 수동 소자 도메인에 IC 종류
        self.assertTrue(any("맞지 않는 kind" in m for m in run(tax=t)["problems"]["check2"]))
        t["functions"][-1]["kind"] = "passive"
        self.assertEqual(run(tax=t)["problems"]["check2"], [])

    def test_external_names_are_informational_only(self):
        t = copy.deepcopy(TAX); t["external_names_not_in_catalog"] = ["Driver_Haptic", "Reg"]
        r = run(tax=t)
        self.assertEqual(r["problems"], {"check1": [], "check2": [], "check3": []})
        self.assertEqual(r["info"]["external_names_present_in_catalog"], ["Reg"])

    def test_check3_only_when_reference_and_raw_exist(self):
        ref = {"libraries": {"Reg": 5}, "functions": {"ldo": [5, 99]}}
        r = run(ref=ref, ids={5})
        self.assertFalse(r["check3_skipped"])
        self.assertTrue(any("99" in m for m in r["problems"]["check3"]))
        self.assertTrue(run(ref=ref, ids=None)["check3_skipped"])
        self.assertTrue(run(ref=None, ids={5})["check3_skipped"])


if __name__ == "__main__":
    unittest.main()
