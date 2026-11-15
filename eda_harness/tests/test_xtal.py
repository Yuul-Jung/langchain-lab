"""xtal: 크리스탈 발진회로 설계·검증. 값은 모두 지어낸 것(실제 부품 아님)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from edaharness import xtal  # noqa: E402


def v(x, basis="datasheet"):
    return {"value": x, "basis": basis}


def crystal(**over):
    d = {"f_hz": v(8e6), "cl_f": v(18e-12), "esr_ohm": v(60.0), "c0_f": v(3e-12)}
    d.update(over)
    return d


IC = {"gm_s": v(10e-3)}
CIRCUIT = {"cstray_f": v(4e-12)}


def codes(findings, sev=None):
    return sorted(f["code"] for f in findings if sev is None or f["severity"] == sev)


class Math(unittest.TestCase):
    def test_gm_crit_matches_formula(self):
        got = xtal.gm_crit(8e6, 60.0, 3e-12, 18e-12)
        want = 4 * 60 * (2 * math.pi * 8e6) ** 2 * (21e-12) ** 2
        self.assertAlmostEqual(got / want, 1.0, places=9)
        self.assertAlmostEqual(got * 1e3, 0.2674, places=3)      # mS

    def test_cl_of_series_plus_stray(self):
        self.assertAlmostEqual(xtal.cl_of(27e-12, 27e-12, 4e-12), 17.5e-12, places=18)
        self.assertAlmostEqual(xtal.cl_of(10e-12, 30e-12, 0.0), 7.5e-12, places=18)


class Design(unittest.TestCase):
    def test_picks_e24_and_passes(self):
        r = xtal.design(crystal(), IC, CIRCUIT)
        self.assertAlmostEqual(r["c_target_f"], 28e-12, places=18)
        self.assertAlmostEqual(r["c1_f"], 27e-12, places=18)
        self.assertEqual(r["c1_f"], r["c2_f"])
        self.assertTrue(xtal.passes(r["findings"]))
        self.assertGreater(r["margin"], 10)

    def test_design_is_recomputed_not_trusted(self):
        r = xtal.design(crystal(), IC, CIRCUIT)
        again = xtal.verify(crystal(), IC, CIRCUIT, r["c1_f"], r["c2_f"])
        self.assertAlmostEqual(again["cl_actual_f"], r["cl_actual_f"], places=18)

    def test_stray_larger_than_cl_is_refused(self):
        with self.assertRaises(xtal.XtalError):
            xtal.design(crystal(), IC, {"cstray_f": v(20e-12)})


class FaultInjection(unittest.TestCase):
    def test_wrong_load_caps(self):
        r = xtal.verify(crystal(), IC, CIRCUIT, 100e-12, 100e-12)
        self.assertIn("LOAD_CAP_MISMATCH", codes(r["findings"], "ERROR"))
        self.assertFalse(xtal.passes(r["findings"]))

    def test_weak_amplifier_fails_gain_margin(self):
        r = xtal.design(crystal(), {"gm_s": v(0.5e-3)}, CIRCUIT)
        self.assertIn("GAIN_MARGIN", codes(r["findings"], "ERROR"))

    def test_low_but_passing_margin_warns(self):
        r = xtal.design(crystal(), {"gm_s": v(2.0e-3)}, CIRCUIT)       # 약 7배
        self.assertEqual(codes(r["findings"], "ERROR"), [])
        self.assertIn("GAIN_MARGIN_LOW", codes(r["findings"], "WARN"))

    def test_high_esr_crystal_is_harder(self):
        easy = xtal.design(crystal(), IC, CIRCUIT)["margin"]
        hard = xtal.design(crystal(esr_ohm=v(600.0)), IC, CIRCUIT)["margin"]
        self.assertLess(hard, easy / 5)

    def test_drive_level_is_always_flagged_unverified(self):
        r = xtal.design(crystal(), IC, CIRCUIT)
        self.assertIn("DRIVE_LEVEL_NOT_CHECKED", codes(r["findings"], "WARN"))


class FailClosed(unittest.TestCase):
    def test_missing_value_refused(self):
        c = crystal()
        del c["esr_ohm"]
        with self.assertRaises(xtal.XtalError):
            xtal.design(c, IC, CIRCUIT)

    def test_bad_numbers_refused(self):
        for bad in (0, -1e-12, float("nan"), True, "18p"):
            with self.assertRaises(xtal.XtalError, msg=repr(bad)):
                xtal.design(crystal(cl_f=v(bad)), IC, CIRCUIT)

    def test_missing_or_unknown_basis_refused(self):
        with self.assertRaises(xtal.XtalError):
            xtal.design(crystal(f_hz={"value": 8e6}), IC, CIRCUIT)
        with self.assertRaises(xtal.XtalError):
            xtal.design(crystal(f_hz={"value": 8e6, "basis": "forum"}), IC, CIRCUIT)

    def test_non_datasheet_basis_warns_but_does_not_block(self):
        r = xtal.design(crystal(), IC, {"cstray_f": v(4e-12, "assumed")})
        self.assertIn("UNVERIFIED_BASIS", codes(r["findings"], "WARN"))
        self.assertTrue(xtal.passes(r["findings"]))


if __name__ == "__main__":
    unittest.main()
