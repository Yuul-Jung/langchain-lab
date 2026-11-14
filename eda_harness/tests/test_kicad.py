import re
import unittest

from helpers import codes, ir
from edaharness import library, sexpr
from edaharness.kicad_reader import compare_with_ir, read_schematic
from edaharness.kicad_writer import layout, write_schematic, write_symbol_library
from edaharness.preview import render_svg


class Writer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ir = ir("mix")
        cls.text = write_schematic(cls.ir)
        cls.root = sexpr.loads(cls.text)

    def test_header(self):
        self.assertEqual(self.root[0], "kicad_sch")
        self.assertEqual(sexpr.find(self.root, "version")[1], 20231120)
        self.assertIsNotNone(sexpr.find(self.root, "sheet_instances"))

    def test_lib_ids_embedded(self):
        libs = {str(s[1]) for s in sexpr.find_all(sexpr.find(self.root, "lib_symbols"), "symbol")}
        used = {str(sexpr.find(s, "lib_id")[1]) for s in sexpr.find_all(self.root, "symbol")}
        self.assertEqual(used, libs)

    def test_subsymbol_names_have_no_library_prefix(self):
        for s in sexpr.find_all(sexpr.find(self.root, "lib_symbols"), "symbol"):
            for sub in sexpr.find_all(s, "symbol"):
                self.assertNotIn(":", str(sub[1]))
                self.assertTrue(re.search(r"_\d+_\d+$", str(sub[1])))

    def test_on_grid(self):
        for s in sexpr.find_all(self.root, "symbol"):
            at = sexpr.find(s, "at")
            for v in at[1:3]:
                self.assertAlmostEqual((v / 1.27) - round(v / 1.27), 0, places=6)
        for w in sexpr.find_all(self.root, "wire"):
            for xy in sexpr.find_all(sexpr.find(w, "pts"), "xy"):
                for v in xy[1:3]:
                    self.assertAlmostEqual((v / 1.27) - round(v / 1.27), 0, places=6)

    def test_uuids_unique(self):
        ids = re.findall(r'\(uuid "([0-9a-f-]{36})"\)', self.text)
        self.assertEqual(len(ids), len(set(ids)))

    def test_deterministic_bytes(self):
        self.assertEqual(self.text, write_schematic(ir("mix")))

    def test_every_pin_gets_wire_or_nc(self):
        n_pins = sum(len(library.get(c["part"]).pins) for c in self.ir["components"].values())
        n = len(sexpr.find_all(self.root, "wire")) + len(sexpr.find_all(self.root, "no_connect"))
        self.assertEqual(n, n_pins)

    def test_symbol_library_parses(self):
        lib = sexpr.loads(write_symbol_library(self.ir))
        self.assertEqual(lib[0], "kicad_symbol_lib")
        names = {str(s[1]) for s in sexpr.find_all(lib, "symbol")}
        self.assertIn("NE555P", names)

    def test_layout_stays_on_paper(self):
        lay = layout(self.ir)
        self.assertEqual(lay["paper"], "A3")

    def test_preview_svg(self):
        svg = render_svg(self.text)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("NE555P", svg)


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.ir = ir("mix")
        self.text = write_schematic(self.ir)

    def rt(self, text):
        return codes(compare_with_ir(self.ir, read_schematic(text)))

    def test_clean(self):
        self.assertEqual(self.rt(self.text), set())

    def test_all_examples_clean(self):
        for k in ("usb_ldo", "motor", "blink"):
            x = ir(k)
            self.assertEqual(codes(compare_with_ir(x, read_schematic(write_schematic(x)))), set(), k)

    def test_renamed_label(self):
        bad = self.text.replace('(label "N_B2_DIS"', '(label "N_B2_DISX"', 1)
        self.assertIn("RT_NET_MISMATCH", self.rt(bad))

    def test_deleted_wire(self):
        bad = re.sub(r"\(wire\b.*?\n  \)\n", "", self.text, count=1, flags=re.S)
        self.assertNotEqual(bad, self.text)
        self.assertTrue({"RT_NET_MISMATCH", "RT_UNCONNECTED"} & self.rt(bad))

    def test_value_changed(self):
        bad = self.text.replace('(property "Value" "75k"', '(property "Value" "68k"', 1)
        self.assertIn("RT_VALUE", self.rt(bad))

    def test_symbol_moved_breaks_connectivity(self):
        root = sexpr.loads(self.text)
        inst = [s for s in sexpr.find_all(root, "symbol")
                if str(sexpr.find(s, "lib_id")[1]) == "eda:NE555P"][0]
        sexpr.find(inst, "at")[1] += 1.27
        self.assertIn("RT_NET_MISMATCH", self.rt(sexpr.dumps(root)))

    def test_label_on_wire_creates_short(self):
        root = sexpr.loads(self.text)
        w = sexpr.find_all(root, "wire")[0]
        a, b = sexpr.find_all(sexpr.find(w, "pts"), "xy")
        mx, my = (a[1] + b[1]) / 2, (a[2] + b[2]) / 2
        root.append([sexpr.Sym("label"), "GND", [sexpr.Sym("at"), mx, my, 0]])
        self.assertIn("RT_NET_MULTI_NAME", self.rt(sexpr.dumps(root)))

    def test_extra_component(self):
        root = sexpr.loads(self.text)
        inst = sexpr.find_all(root, "symbol")[-1]
        import copy
        dup = copy.deepcopy(inst)
        for p in sexpr.find_all(dup, "property"):
            if p[1] == "Reference":
                p[2] = "R99"
        sexpr.find(dup, "at")[2] += 200
        root.append(dup)
        self.assertIn("RT_COMPONENT_EXTRA", self.rt(sexpr.dumps(root)))

    def test_rotation_unsupported_is_error(self):
        bad = self.text.replace("(at 30.48 50.8 0)", "(at 30.48 50.8 90)", 1)
        if bad == self.text:
            root = sexpr.loads(self.text)
            sexpr.find(sexpr.find_all(root, "symbol")[0], "at")[3] = 90
            bad = sexpr.dumps(root)
        self.assertIn("RT_UNSUPPORTED_TRANSFORM", self.rt(bad))

    def test_identity_swap(self):
        bad = self.text.replace('"EDA_ID" "B2.R_A"', '"EDA_ID" "B2.R_X"', 1)
        self.assertIn("RT_IDENTITY", self.rt(bad))


if __name__ == "__main__":
    unittest.main()
