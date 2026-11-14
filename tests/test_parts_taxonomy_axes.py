import unittest

import parts_taxonomy as pt


class AxesTest(unittest.TestCase):
    def test_material_and_circuit_nature_are_derived(self):
        self.assertEqual(pt.material("ic"), "semiconductor")
        self.assertEqual(pt.material("discrete"), "semiconductor")
        for k in ("passive", "electromech", "mechanical", "symbol", "tube"):
            self.assertEqual(pt.material(k), "non_semiconductor")
        self.assertEqual(pt.material("module"), "assembly")
        self.assertEqual(pt.circuit_nature("ic", "analog"), "analog")
        self.assertEqual(pt.circuit_nature("ic", "power"), "power")
        for d in ("processor", "logic", "memory"):
            self.assertEqual(pt.circuit_nature("ic", d), "digital")
        for d in ("interface", "rf", "sensor"):
            self.assertEqual(pt.circuit_nature("ic", d), "mixed_signal")
        self.assertIsNone(pt.circuit_nature("passive", "passive"))          # IC 만 회로 성격이 있다
        self.assertEqual(pt.circuit_nature("ic", "other"), "unspecified")

    def test_default_kinds_follow_the_agreed_table_and_fit_their_domains(self):
        self.assertEqual(pt.default_kind("microphone", "analog"), "electromech")
        self.assertEqual(pt.default_kind("acdc", "power"), "module")
        self.assertEqual(pt.default_kind("led", "opto"), "discrete")
        self.assertEqual(pt.default_kind("lcd_char", "opto"), "module")
        self.assertEqual(pt.default_kind("vacuum_tube", "other"), "tube")
        self.assertEqual(pt.default_kind("mcu", "processor"), "ic")
        for fid, kind in pt.FUNCTION_KIND.items():
            self.assertIn(kind, pt.KINDS)
        for dom, kind in pt.DOMAIN_DEFAULT_KIND.items():
            self.assertIn(kind, pt.DOMAIN_KINDS[dom])

    def test_tech_group_names(self):
        self.assertEqual(pt.tech_group("ic", "analog"), ("반도체", "IC · 아날로그"))
        self.assertEqual(pt.tech_group("discrete", "discrete"), ("반도체", "개별 소자"))
        self.assertEqual(pt.tech_group("passive", "passive"), ("비반도체", "수동 소자"))
        self.assertEqual(pt.tech_group("module", "rf"), ("조립품(모듈)", "모듈"))


if __name__ == "__main__":
    unittest.main()
