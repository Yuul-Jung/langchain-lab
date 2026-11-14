import unittest

from helpers import intent  # noqa: F401  (경로 설정)
from edaharness import sexpr
from edaharness.units import cap_voltage_rating, e_nearest, format_si, parse_si, rail_name


class Units(unittest.TestCase):
    def test_e24(self):
        self.assertEqual(e_nearest(4700), 4700)
        self.assertEqual(e_nearest(608, mode="ceil"), 620)
        self.assertEqual(e_nearest(608, mode="floor"), 560)
        self.assertAlmostEqual(e_nearest(71500), 75000)

    def test_e24_rejects_nonpositive(self):
        for v in (0, -1, float("inf")):
            with self.assertRaises(ValueError):
                e_nearest(v)

    def test_format_and_parse(self):
        for v, s in ((4700, "4.7k"), (1e-5, "10u"), (1e-7, "100n"), (5100, "5.1k"), (270, "270"), (1e5, "100k")):
            self.assertEqual(format_si(v), s)
            self.assertAlmostEqual(parse_si(s), v, places=12)

    def test_rail_name(self):
        self.assertEqual(rail_name(3.3), "+3V3")
        self.assertEqual(rail_name(5.0), "+5V")
        self.assertEqual(rail_name(12), "+12V")
        self.assertEqual(rail_name(1.8), "+1V8")
        self.assertEqual(rail_name(2.5), "+2V5")

    def test_cap_rating(self):
        self.assertEqual(cap_voltage_rating(5), 10)
        self.assertEqual(cap_voltage_rating(12), 25)
        self.assertEqual(cap_voltage_rating(3.3), 6.3)


class SExpr(unittest.TestCase):
    def test_roundtrip_and_escape(self):
        S = sexpr.Sym
        node = [S("a"), "q\"uo\\te", 1, 2.5, -0.0001, [S("b"), S("yes"), "x\ny"]]
        back = sexpr.loads(sexpr.dumps(node))
        self.assertEqual(back[1], 'q"uo\\te')
        self.assertEqual(back[2], 1)
        self.assertAlmostEqual(back[3], 2.5)
        self.assertEqual(back[5][2], "x\ny")
        self.assertIsInstance(back[5][1], sexpr.Sym)
        self.assertIsInstance(back[1], sexpr.QStr)

    def test_parse_errors(self):
        for bad in ("(a (b)", "(a))", "", '(a "x)', "(a)(b)"):
            with self.assertRaises(sexpr.ParseError):
                sexpr.loads(bad)

    def test_number_format(self):
        self.assertEqual(sexpr.dumps([sexpr.Sym("at"), 1.27, 3.81, 0]), "(at 1.27 3.81 0)")
        self.assertEqual(sexpr.dumps([sexpr.Sym("x"), 1e-6]), "(x 0)")


if __name__ == "__main__":
    unittest.main()


class LengthUnits(unittest.TestCase):
    def test_conversions(self):
        from edaharness.units import format_length, mil_to_mm, mm_to_mil, parse_length_mm
        self.assertAlmostEqual(mil_to_mm(100), 2.54)
        self.assertAlmostEqual(mm_to_mil(2.54), 100)
        self.assertAlmostEqual(parse_length_mm("100mil"), 2.54)
        self.assertAlmostEqual(parse_length_mm("2.54 mm"), 2.54)
        self.assertAlmostEqual(parse_length_mm("0.1in"), 2.54)
        self.assertEqual(format_length(2.54), "2.54mm (100mil)")

    def test_unitless_length_refused(self):
        from edaharness.units import parse_length_mm
        for bad in ("2.54", "100 mills", "mil"):
            with self.assertRaises(ValueError):
                parse_length_mm(bad)
