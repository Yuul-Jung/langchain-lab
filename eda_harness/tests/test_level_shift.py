"""범용 레벨 변환 분압기: 특정 부품이 아니라 수치 사양으로 동작함을 검증한다."""
import unittest

from helpers import by_role, clone, codes
from edaharness import checks
from edaharness.intent import SCHEMA_ID, validate_intent
from edaharness.synth import SynthesisError, synthesize


def params(**kw):
    base = {"src_high_v": 5.0, "src_tol": 0.1, "src_iout_max_a": 0.001,
            "sink_vih_min_v": 2.0, "sink_vmax_v": 3.45,
            "signal_max_hz": 10000.0, "sink_cin_f": 20e-12}
    base.update(kw)
    return base


def make_intent(**kw):
    return {"schema": SCHEMA_ID, "source": {"kind": "manual"},
            "power_input": {"connector": "dc", "voltage_v": 5.0},
            "blocks": [{"id": "B1", "type": "level_shift_divider", "params": params(**kw)}],
            "assumptions": [], "questions": [], "unparsed": []}


def findings(x):
    return checks.structural(x) + checks.semantic(x) + checks.electrical(x)


class LevelShift(unittest.TestCase):
    def test_nominal_passes_all_gates(self):
        x = synthesize(make_intent(), "t")
        self.assertEqual(codes(findings(x)), set())

    def test_many_voltage_pairs_pass_without_code_change(self):
        # (보내는 High V, 받는 Vih_min, 받는 Vmax) — 부품 이름은 어디에도 없다
        cases = [(5.0, 2.0, 3.45), (5.0, 1.17, 1.98), (12.0, 2.0, 3.45), (3.6, 1.2, 1.98),
                 (5.0, 2.4, 3.6), (24.0, 2.0, 5.5)]
        for vs, vih, vmx in cases:
            with self.subTest(vs=vs, vih=vih, vmx=vmx):
                x = synthesize(make_intent(src_high_v=vs, sink_vih_min_v=vih, sink_vmax_v=vmx), "t")
                self.assertEqual(codes(findings(x)), set())

    def test_not_needed_is_refused(self):
        with self.assertRaises(SynthesisError):
            synthesize(make_intent(src_high_v=3.0, src_tol=0.05), "t")

    def test_cannot_raise_voltage(self):
        with self.assertRaises(SynthesisError):
            synthesize(make_intent(src_high_v=5.0, src_tol=0.1, sink_vih_min_v=4.6, sink_vmax_v=4.8), "t")

    def test_too_fast_signal_refused(self):
        with self.assertRaises(SynthesisError):
            synthesize(make_intent(signal_max_hz=5e6, sink_cin_f=50e-12), "t")

    def test_weak_source_refused(self):
        with self.assertRaises(SynthesisError):
            synthesize(make_intent(src_iout_max_a=1e-6), "t")

    def test_unknown_key_rejected(self):
        it = make_intent()
        it["blocks"][0]["params"]["vendor"] = "x"
        self.assertTrue(validate_intent(it))

    def test_deterministic(self):
        from edaharness.synth import sha256_of
        self.assertEqual(sha256_of(synthesize(make_intent(), "t")), sha256_of(synthesize(make_intent(), "t")))

    def test_divider_formula_against_hand_values(self):
        from edaharness.units import divider_window
        lo, hi = divider_window(5.0, 5.0, 1000.0, 2000.0, 0.0)
        self.assertAlmostEqual(lo, 3.3333, places=3)
        self.assertAlmostEqual(hi, 3.3333, places=3)
        lo, hi = divider_window(5.0, 5.0, 1000.0, 2000.0, 0.01)
        self.assertAlmostEqual(lo, 5.0 * 2000 * 0.99 / (2000 * 0.99 + 1000 * 1.01), places=6)
        self.assertAlmostEqual(hi, 5.0 * 2000 * 1.01 / (2000 * 1.01 + 1000 * 0.99), places=6)
        self.assertGreater(hi, 3.3333)
        self.assertLess(lo, 3.3333)

    def test_narrow_window_refused_by_synthesis(self):
        with self.assertRaises(SynthesisError):
            synthesize(make_intent(sink_vih_min_v=3.0, sink_vmax_v=3.2), "t")

    # ---- 결함 주입: 검사가 실제로 잡는지
    def _mut(self, role, ohms):
        x = clone(synthesize(make_intent(), "t"))
        c = by_role(x, "B1", role)
        c["params"]["r_ohm"] = ohms
        return x

    def test_fault_top_too_small_overvoltage(self):
        self.assertIn("LEVEL_SINK_VMAX", codes(findings(self._mut("R_TOP", 100.0))))

    def test_fault_bottom_too_small_undervoltage(self):
        self.assertIn("LEVEL_SINK_VIH", codes(findings(self._mut("R_BOT", 100.0))))

    def test_fault_low_resistance_overloads_source(self):
        x = clone(synthesize(make_intent(), "t"))
        by_role(x, "B1", "R_TOP")["params"]["r_ohm"] = 1000.0
        by_role(x, "B1", "R_BOT")["params"]["r_ohm"] = 2000.0
        self.assertIn("LEVEL_SRC_CURRENT", codes(findings(x)))

    def test_fault_high_resistance_slow_edge(self):
        x = clone(synthesize(make_intent(), "t"))
        by_role(x, "B1", "R_TOP")["params"]["r_ohm"] = 3e6
        by_role(x, "B1", "R_BOT")["params"]["r_ohm"] = 6e6
        self.assertIn("LEVEL_RISE_TIME", codes(findings(x)))

    def test_fault_wrong_topology(self):
        x = clone(synthesize(make_intent(), "t"))
        by_role(x, "B1", "R_BOT")["pins"]["2"] = by_role(x, "B1", "R_TOP")["pins"]["1"]
        self.assertIn("LEVEL_TOPOLOGY", codes(findings(x)))

    def test_self_report_not_trusted(self):
        x = clone(synthesize(make_intent(), "t"))
        by_role(x, "B1", "R_TOP")["params"]["r_ohm"] = 100.0
        x["blocks"]["B1"]["design"]["vout_worst_max_v"] = 3.0    # 합성기 자기 보고는 무시돼야 함
        self.assertIn("LEVEL_SINK_VMAX", codes(findings(x)))


if __name__ == "__main__":
    unittest.main()
