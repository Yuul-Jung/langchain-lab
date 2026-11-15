"""오라클 자체 시험(규칙 문장 R1~R9 의 사례) + 엔진 독립 점검(AST)."""
import ast
import pathlib
import unittest

from oracle_constraints import PASS, UNKNOWN, VIOLATION, judge

HERE = pathlib.Path(__file__).parent


def case(v="3.3", ta=(0, 50), **fields):
    base = {"supply_min_v": [("datasheet", "3.0")], "supply_max_v": [("datasheet", "3.6")],
            "abs_max_supply_v": [("datasheet", "4.0")], "temp_min_c": [("datasheet", -40)], "temp_max_c": [("datasheet", 85)]}
    base.update(fields)
    return {"fields": base, "v": v, "ta": ta}


class OracleRules(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(judge(case())[0], PASS)

    def test_boundaries_inclusive(self):
        for v in ("3.0", "3.6"):
            self.assertEqual(judge(case(v=v))[0], PASS)
        self.assertEqual(judge(case(v="3.7"))[0], VIOLATION)
        self.assertEqual(judge(case(v="2.9"))[0], VIOLATION)

    def test_abs_max_equal_not_exceeded(self):
        c = case(v="4.0", supply_max_v=[("datasheet", "5.0")])
        self.assertEqual(judge(c)[0], PASS)
        self.assertEqual(judge(case(v="4.1", supply_max_v=[("datasheet", "5.0")]))[0], VIOLATION)

    def test_r7_abs_max_missing_is_unknown_not_pass(self):
        self.assertEqual(judge(case(abs_max_supply_v=[]))[0], UNKNOWN)

    def test_risk_cell1(self):  # 절대 최대 없음 × 절대 최대 초과 위치: supply_max 확정이면 위반, 없음이면 판정 불가
        self.assertEqual(judge(case(v="9.0", abs_max_supply_v=[]))[0], VIOLATION)
        self.assertEqual(judge(case(v="9.0", abs_max_supply_v=[], supply_max_v=[]))[0], UNKNOWN)

    def test_r2_same_tier_conflict(self):
        c = case(supply_max_v=[("distributor", "3.6"), ("distributor", "3.8")], v="3.3")
        self.assertEqual(judge(c)[0], UNKNOWN)
        self.assertEqual(judge(case(supply_max_v=[("distributor", "3.6"), ("distributor", "3.6")]))[0], PASS)

    def test_r3_higher_tier_wins(self):
        c = case(supply_max_v=[("datasheet", "3.6"), ("distributor", "3.0")], v="3.5")
        self.assertEqual(judge(c)[0], PASS)

    def test_r5_delegated_warns_and_abs_max_rejected(self):
        res, warns, _ = judge(case(supply_min_v=[("delegated", "3.0")]))
        self.assertEqual(res, PASS)
        self.assertIn("DELEGATED_CONFIRMATION", warns)
        self.assertEqual(judge(case(abs_max_supply_v=[("delegated", "4.0")]))[0], UNKNOWN)

    def test_r8_temperature_edges(self):
        self.assertEqual(judge(case(ta=(-40, 85)))[0], PASS)
        self.assertEqual(judge(case(ta=(-41, 50)))[0], VIOLATION)
        self.assertEqual(judge(case(ta=(0, 50), temp_max_c=[]))[0], UNKNOWN)
        self.assertEqual(judge(case(ta=(-50, 50), temp_max_c=[]))[0], VIOLATION)  # 위반 우선

    def test_r9_violation_beats_missing(self):
        self.assertEqual(judge(case(v="9.0", temp_min_c=[]))[0], VIOLATION)

    def test_extracted_is_input_error(self):
        with self.assertRaises(ValueError):
            judge(case(supply_min_v=[("extracted", "3.0")]))


class OracleReasonsAndInputs(unittest.TestCase):
    def test_reasons(self):
        res, _, why = judge(case(v="4.5", supply_max_v=[("datasheet", "5.0")]))
        self.assertEqual(res, VIOLATION)
        self.assertEqual(why["violation"], {"abs_max_supply_v"})  # 권장 안이지만 절대 최대 초과
        res, _, why = judge(case(v="9.0"))
        self.assertEqual(why["violation"], {"supply_max_v", "abs_max_supply_v"})
        _, _, why = judge(case(abs_max_supply_v=[]))
        self.assertEqual(why["unknown"], {"abs_max_supply_v"})

    def test_input_validation_r0(self):
        with self.assertRaises(ValueError):
            judge(case(ta=(50, 0)))  # Ta_lo > Ta_hi
        with self.assertRaises(ValueError):
            judge({"fields": {}, "v": None, "ta": (0, 1)})
        with self.assertRaises(ValueError):
            judge(case(v=3.3))  # float 금지
        with self.assertRaises(ValueError):
            judge(case(supply_min_v=[("datasheet", "abc")]))

    def test_nonfinite_rejected(self):
        for bad in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(ValueError):
                judge(case(v=bad))
            with self.assertRaises(ValueError):
                judge(case(supply_max_v=[("datasheet", bad)]))

    def test_decimal_boundary_exact(self):
        self.assertEqual(judge(case(v="3.6"))[0], PASS)
        self.assertEqual(judge(case(v="3.6000001"))[0], VIOLATION)


class OracleIndependence(unittest.TestCase):
    def test_no_engine_import(self):
        tree = ast.parse((HERE / "oracle_constraints.py").read_text(encoding="utf-8"))
        names = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                names.add(n.module or "")
        bad = {x for x in names if "edaharness" in x or "constraints" in x.replace("oracle_constraints", "")}
        self.assertFalse(bad, f"엔진 import 금지: {bad}")


if __name__ == "__main__":
    unittest.main()
