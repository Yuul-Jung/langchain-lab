import unittest

from helpers import codes
from edaharness import checks
from edaharness.intent import SCHEMA_ID, validate_intent
from edaharness.ratings import RatingsError, level_link_block
from edaharness.synth import synthesize


def e(v, basis="datasheet", note=""):
    return {"value": v, "basis": basis, "note": note}


SRC = {"name": "임의 5V 센서", "signals": {"OUT": {"voh_v": e(5.0, "derived", "전원 5V±10%"),
                                                  "voh_tol": e(0.1, "derived", "전원 범위에서 유도"),
                                                  "iout_max_a": e(0.001, "assumed", "사양 없음")}}}
SINK = {"name": "임의 3.3V 칩", "signals": {"IN": {"vih_min_v": e(2.0), "vmax_v": e(3.45, "assumed", "3.3V+5%"),
                                                  "cin_f": e(5e-12)}}}


def intent_of(block, assumptions):
    return {"schema": SCHEMA_ID, "source": {"kind": "manual"},
            "power_input": {"connector": "dc", "voltage_v": 5.0},
            "blocks": [block], "assumptions": assumptions, "questions": [], "unparsed": []}


class Ratings(unittest.TestCase):
    def test_end_to_end_passes_gates(self):
        blk, ass = level_link_block(SRC, "OUT", SINK, "IN", 10000)
        it = intent_of(blk, ass)
        self.assertEqual(validate_intent(it), [])
        x = synthesize(it, "t")
        f = checks.structural(x) + checks.semantic(x) + checks.electrical(x)
        self.assertEqual(codes(f), set())

    def test_non_datasheet_values_become_assumptions(self):
        _, ass = level_link_block(SRC, "OUT", SINK, "IN", 10000)
        fields = {a["field"] for a in ass}
        self.assertIn("보내는 쪽.OUT.iout_max_a", fields)
        self.assertIn("받는 쪽.IN.vmax_v", fields)
        self.assertNotIn("받는 쪽.IN.vih_min_v", fields)       # datasheet 값은 가정이 아님
        self.assertTrue(all("미검증" in a["reason"] for a in ass if a["field"] != "signal_max_hz"))

    def test_missing_value_refused(self):
        bad = {"name": "x", "signals": {"OUT": {"voh_v": e(5.0)}}}
        with self.assertRaises(RatingsError):
            level_link_block(bad, "OUT", SINK, "IN", 1000)

    def test_missing_basis_refused(self):
        bad = {"name": "x", "signals": {"IN": {"vih_min_v": {"value": 2.0}, "vmax_v": e(3.0), "cin_f": e(5e-12)}}}
        with self.assertRaises(RatingsError):
            level_link_block(SRC, "OUT", bad, "IN", 1000)

    def test_unknown_pin_refused(self):
        with self.assertRaises(RatingsError):
            level_link_block(SRC, "NOPE", SINK, "IN", 1000)

    def test_non_numeric_refused(self):
        bad = {"name": "x", "signals": {"OUT": {"voh_v": e("5V TTL"), "voh_tol": e(0.1), "iout_max_a": e(0.001)}}}
        with self.assertRaises(RatingsError):
            level_link_block(bad, "OUT", SINK, "IN", 1000)

    def test_bad_speed_refused(self):
        with self.assertRaises(RatingsError):
            level_link_block(SRC, "OUT", SINK, "IN", 0)


if __name__ == "__main__":
    unittest.main()
