import os
import tempfile
import unittest

from helpers import clone
from edaharness import kicadlib, library
from edaharness.gates import GATES

SYM_LIB = '''(kicad_symbol_lib (version 20240101)
\t(symbol "R"
\t\t(symbol "R_1_1"
\t\t\t(pin passive line (at 0 3.81 270) (length 1.27) (name "~" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))
\t\t\t(pin passive line (at 0 -3.81 90) (length 1.27) (name "~" (effects (font (size 1 1)))) (number "2" (effects (font (size 1 1)))))
\t\t)
\t)
\t(symbol "R_US"
\t\t(extends "R")
\t)
)
'''
FP = '(footprint "R_0603" (pad "1" smd roundrect (at 0 0)) (pad "2" smd roundrect (at 1 0)))'


def libs(sym=SYM_LIB, fp=FP, fp_name="R_0603"):
    d = tempfile.mkdtemp()
    sd, fd = os.path.join(d, "s"), os.path.join(d, "f")
    os.makedirs(sd)
    os.makedirs(os.path.join(fd, "Resistor_SMD.pretty"))
    open(os.path.join(sd, "Device.kicad_sym"), "w", encoding="utf-8").write(sym)
    open(os.path.join(fd, "Resistor_SMD.pretty", fp_name + ".kicad_mod"), "w", encoding="utf-8").write(fp)
    return sd, fd


def ir_one_resistor(fp="Resistor_SMD:R_0603"):
    return {"components": {"X.R": {"id": "X.R", "ref": "R1", "part": "R", "footprint": fp}}}


class WithEnv(unittest.TestCase):
    def run_check(self, ir, sd, fd):
        old = (os.environ.get("KICAD_SYMBOL_DIR"), os.environ.get("KICAD_FOOTPRINT_DIR"))
        os.environ["KICAD_SYMBOL_DIR"], os.environ["KICAD_FOOTPRINT_DIR"] = sd, fd
        try:
            return kicadlib.check(ir)
        finally:
            for k, v in zip(("KICAD_SYMBOL_DIR", "KICAD_FOOTPRINT_DIR"), old):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class Synthetic(WithEnv):
    def codes(self, f, sev):
        return {x["code"] for x in f if x["severity"] == sev}

    def test_matching_passes(self):
        st, f, m = self.run_check(ir_one_resistor(), *libs())
        self.assertEqual(st, "PASS")
        self.assertEqual(self.codes(f, "ERROR"), set())

    def test_symbol_extends_resolved(self):
        sd, _ = libs()
        pins = kicadlib.symbol_pins(sd, "Device:R_US")
        self.assertEqual(sorted(n for n, _ in pins), ["1", "2"])

    def test_pin_number_mismatch_is_error(self):
        sym = SYM_LIB.replace('(number "2"', '(number "3"')
        st, f, _ = self.run_check(ir_one_resistor(), *libs(sym=sym))
        self.assertEqual(st, "FAIL")
        self.assertIn("SYM_PIN_NUMBERS", self.codes(f, "ERROR"))

    def test_missing_footprint_is_error(self):
        st, f, _ = self.run_check(ir_one_resistor("Resistor_SMD:R_9999"), *libs())
        self.assertEqual(st, "FAIL")
        self.assertIn("FP_NOT_FOUND", self.codes(f, "ERROR"))

    def test_missing_pad_is_error(self):
        st, f, _ = self.run_check(ir_one_resistor(), *libs(fp='(footprint "R_0603" (pad "1" smd roundrect (at 0 0)))'))
        self.assertEqual(st, "FAIL")
        self.assertIn("FP_PAD_MISSING", self.codes(f, "ERROR"))

    def test_extra_pad_is_warning_only(self):
        fp = '(footprint "R_0603" (pad "1" smd rect (at 0 0)) (pad "2" smd rect (at 1 0)) (pad "SH" smd rect (at 2 0)))'
        st, f, _ = self.run_check(ir_one_resistor(), *libs(fp=fp))
        self.assertEqual(st, "PASS")
        self.assertIn("FP_PAD_EXTRA", self.codes(f, "WARN"))

    def test_libraries_missing_is_skipped_not_pass(self):
        st, f, _ = self.run_check(ir_one_resistor(), "/nonexistent/s", "/nonexistent/f")
        self.assertEqual(st, "SKIPPED")


SD, FD = kicadlib.locate()


@unittest.skipUnless(SD and FD, "실제 KiCad 라이브러리 없음")
class RealLibrary(unittest.TestCase):
    def test_every_harness_part_matches_kicad(self):
        for key, p in library.LIBRARY.items():
            with self.subTest(part=key):
                kp = kicadlib.symbol_pins(SD, p.kicad_symbol)
                self.assertIsNotNone(kp, p.kicad_symbol)
                self.assertEqual({n for n, _ in kp}, {x.number for x in p.pins})
                if p.default_footprint:
                    pads = kicadlib.pad_numbers(FD, p.default_footprint)
                    self.assertIsNotNone(pads, p.default_footprint)
                    self.assertTrue({x.number for x in p.pins} <= pads)

    def test_mosfet_pin_regression(self):
        # SOT-23 AO3400A: 1=G 2=S 3=D (KiCad 공식). 예전 하네스는 2=D 3=S로 잘못 정의했었다.
        self.assertEqual(library.pin_number("AO3400A", "D"), "3")
        self.assertEqual(library.pin_number("AO3400A", "S"), "2")
        self.assertEqual(library.pin_number("IRLZ44N", "D"), "2")

    def test_usb_shield_pad_name_regression(self):
        self.assertIn("SH", library.get("USB_C_Power_6P").pin_numbers)

    def test_g7_is_last_gate(self):
        self.assertEqual(GATES[-1], ("G7", "KICAD_LIBRARY"))


if __name__ == "__main__":
    unittest.main()


class MosfetWiring(unittest.TestCase):
    def test_ao3400a_drain_source_pins_wired_by_name(self):
        from helpers import ir
        x = ir("motor")
        q = [c for c in x["components"].values() if c["role"] == "Q"][0]
        self.assertEqual(q["part"], "AO3400A")
        self.assertEqual(q["pins"]["2"], "GND")                       # 소스
        self.assertTrue(q["pins"]["3"].startswith("N_B1_DRAIN"))      # 드레인
        self.assertTrue(q["pins"]["1"].startswith("N_B1_GATE"))
