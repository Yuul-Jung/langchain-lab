"""constraints: 출처 단계 해결·충돌·동작점 판정. 값은 모두 지어낸 것(실제 부품 아님)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from edaharness import constraints as cs  # noqa: E402


def rec(**fields):
    return {"values": {k: v if isinstance(v, list) else [{"value": v, "source": "datasheet"}] for k, v in fields.items()}}


GOOD = dict(supply_min_v=2.0, supply_max_v=5.5, abs_max_supply_v=7.0, temp_min_c=-40, temp_max_c=85)


def codes(findings):
    return sorted(f["code"] for f in findings)


class Resolve(unittest.TestCase):
    def test_higher_source_wins(self):
        r = cs.resolve(rec(supply_max_v=[{"value": 6.0, "source": "library"}, {"value": 5.5, "source": "datasheet"},
                                         {"value": 5.0, "source": "distributor"}]), "supply_max_v")
        self.assertEqual((r["status"], r["value"], r["source"]), ("ok", 5.5, "datasheet"))

    def test_same_rank_disagreement_is_conflict(self):
        r = cs.resolve(rec(supply_max_v=[{"value": 5.5, "source": "distributor"}, {"value": 6.0, "source": "distributor"}]),
                       "supply_max_v")
        self.assertEqual(r["status"], "conflict")
        self.assertIsNone(r["value"])

    def test_missing_and_bad_input(self):
        self.assertEqual(cs.resolve({"values": {}}, "temp_max_c")["status"], "missing")
        with self.assertRaises(cs.ConstraintError):
            cs.resolve(rec(supply_max_v=[{"value": "5.5", "source": "datasheet"}]), "supply_max_v")
        with self.assertRaises(cs.ConstraintError):
            cs.resolve(rec(supply_max_v=[{"value": 5.5, "source": "forum"}]), "supply_max_v")

    def test_disagreements_lists_cross_rank_differences(self):
        d = cs.disagreements(rec(supply_max_v=[{"value": 5.5, "source": "datasheet"}, {"value": 6.0, "source": "distributor"}],
                                 temp_max_c=85))
        self.assertEqual([x["field"] for x in d], ["supply_max_v"])


class OperatingPoint(unittest.TestCase):
    def test_inside_everything_passes(self):
        f = cs.check_operating_point(rec(**GOOD), 3.3, (-20, 60))
        self.assertTrue(cs.passes(f))
        self.assertEqual(f, [])

    # 결함 주입: 규칙마다 하나씩
    def test_abs_max_exceeded(self):
        f = cs.check_operating_point(rec(**GOOD), 9.0)
        self.assertIn("ABS_MAX_EXCEEDED", codes(f))
        self.assertFalse(cs.passes(f))

    def test_above_recommended_but_below_abs_max(self):
        f = cs.check_operating_point(rec(**GOOD), 6.0)
        self.assertEqual(codes(f), ["ABOVE_RECOMMENDED"])

    def test_below_recommended(self):
        self.assertEqual(codes(cs.check_operating_point(rec(**GOOD), 1.8)), ["BELOW_RECOMMENDED"])

    def test_boundaries_are_inclusive(self):
        self.assertTrue(cs.passes(cs.check_operating_point(rec(**GOOD), 2.0, (-40, 85))))
        self.assertTrue(cs.passes(cs.check_operating_point(rec(**GOOD), 5.5)))

    def test_temperature_out_of_range(self):
        self.assertEqual(codes(cs.check_operating_point(rec(**GOOD), 3.3, (-45, 60))), ["TEMP_BELOW"])
        self.assertEqual(codes(cs.check_operating_point(rec(**GOOD), 3.3, (0, 90))), ["TEMP_ABOVE"])

    def test_missing_value_fails_closed(self):
        g = dict(GOOD)
        del g["abs_max_supply_v"]
        f = cs.check_operating_point(rec(**g), 3.3)
        self.assertEqual(codes(f), ["MISSING"])
        self.assertFalse(cs.passes(f))

    def test_conflict_fails_closed(self):
        g = dict(GOOD, supply_max_v=[{"value": 5.5, "source": "datasheet"}, {"value": 3.6, "source": "datasheet"}])
        self.assertIn("CONFLICT", codes(cs.check_operating_point(rec(**g), 3.3)))

    def test_non_datasheet_basis_warns_but_still_judges(self):
        g = dict(GOOD, abs_max_supply_v=[{"value": 7.0, "source": "distributor"}])
        f = cs.check_operating_point(rec(**g), 3.3)
        self.assertTrue(cs.passes(f))
        self.assertEqual(codes(f), ["UNVERIFIED_BASIS"])

    def test_inverted_range_is_error(self):
        self.assertIn("BAD_RANGE", codes(cs.check_operating_point(rec(**dict(GOOD, supply_min_v=6.0)), 6.2)))

    def test_rejects_bad_operating_point(self):
        with self.assertRaises(cs.ConstraintError):
            cs.check_operating_point(rec(**GOOD), -1)
        with self.assertRaises(cs.ConstraintError):
            cs.check_operating_point(rec(**GOOD), 3.3, (60, -20))


if __name__ == "__main__":
    unittest.main()
