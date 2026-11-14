import unittest

import networkx as nx

import ontology_graph as og
import part_conditions as pc
import parts_graph as pg


def part(desc, name="X1", keywords="", footprint=""):
    return {"lib_id": f"Zeta:{name}", "library": "Zeta", "name": name, "description": desc, "keywords": keywords, "footprint": footprint}


class ParseTest(unittest.TestCase):
    def labels(self, q):
        return [(c.family, c.label) for c in pc.parse(q)]

    def test_interfaces_voltage_channels_package_lowpower_isolation(self):
        got = self.labels("절연 4채널 I2C 저전력 3.3V SOT-23 칩")
        for want in [("interface", "I2C"), ("voltage", "3.3V"), ("channels", "4채널"), ("package", "SOT-23"),
                     ("low_power", "저전력"), ("isolated", "절연")]:
            self.assertIn(want, got)

    def test_bare_lowercase_can_is_not_an_interface_and_tssop_is_not_sop(self):
        self.assertEqual(self.labels("can you find a TSSOP part"), [("package", "TSSOP")])

    def test_second_concept_becomes_function_condition(self):
        g = nx.Graph()
        g.add_node("kw:boost", kind="keyword", label="boost")
        og.add_korean_bridge(g, [{"ko": ["가젯 알파"], "kw": []}, {"ko": ["베타 승압"], "kw": ["boost"]}])
        ids = ["concept:0", "concept:1"]
        conds = pc.parse("가젯 알파랑 베타 승압", g, ids)
        self.assertEqual([(c.family, c.label) for c in conds], [("function", "베타 승압")])
        self.assertEqual(pc.check(conds[0], part("Boost converter")), pc.OK)
        self.assertEqual(pc.check(conds[0], part("boosted? no: reboost")), pc.UNKNOWN)   # 낱말 경계


class CheckTest(unittest.TestCase):
    def cond(self, q):
        return pc.parse(q)[0]

    def test_voltage_ok_in_range_no_when_other_values_unknown_when_absent(self):
        c = self.cond("3.3V")
        self.assertEqual(pc.check(c, part("LDO, 2.5..16V input")), pc.OK)
        self.assertEqual(pc.check(c, part("LDO, 3.3V fixed output")), pc.OK)
        self.assertEqual(pc.check(c, part("LDO, 5V fixed output")), pc.NO)
        self.assertEqual(pc.check(c, part("LDO regulator")), pc.UNKNOWN)

    def test_channels_by_number_or_word(self):
        c = self.cond("4채널")
        self.assertEqual(pc.check(c, part("Quad op amp")), pc.OK)
        self.assertEqual(pc.check(c, part("8-channel ADC")), pc.NO)
        self.assertEqual(pc.check(c, part("ADC")), pc.UNKNOWN)

    def test_interface_evidence_or_unknown_never_no(self):
        c = self.cond("CAN 되는 칩")
        self.assertEqual(pc.check(c, part("CAN FD transceiver")), pc.OK)
        self.assertEqual(pc.check(c, part("ARM Cortex-M4 MCU")), pc.UNKNOWN)

    def test_rank_puts_more_satisfied_first_and_keeps_order_on_ties(self):
        conds = pc.parse("I2C 3.3V")
        rows = [part("SPI 5V", "A"), part("I2C sensor 1.8..3.6V", "B"), part("sensor", "C"), part("I2C sensor", "D")]
        self.assertEqual([p["name"] for p in pc.rank(conds, rows)], ["B", "D", "C", "A"])


class GraphTest(unittest.TestCase):
    def test_answer_lists_conditions_and_marks_unknown(self):
        g = nx.Graph()
        g.add_node("lib:Zeta", kind="library", label="Zeta")
        og.add_korean_bridge(g, [{"ko": ["가젯 알파"], "lib": ["Zeta"], "review_status": "approved"}])
        rows = [part("Gadget, SPI", "A"), part("Gadget, I2C interface", "B")]
        d = pg.PartsDeps(find=lambda q, n: (rows, "es-semantic"), ontology=g, conditions=True)
        r = pg.ask_parts(pg.build_parts_graph(d), "I2C 가젯 알파 3.3V 부품 추천")
        self.assertEqual(r["conditions"], ["I2C", "3.3V"])
        self.assertEqual(r["parts"][0]["name"], "B")
        self.assertIn("조건: I2C ✓ · 3.3V ?", r["answer"])
        self.assertIn("확인하지 못했습니다", r["answer"])

    def test_flag_off_keeps_old_behaviour(self):
        g = nx.Graph()
        g.add_node("lib:Zeta", kind="library", label="Zeta")
        og.add_korean_bridge(g, [{"ko": ["가젯 알파"], "lib": ["Zeta"], "review_status": "approved"}])
        rows = [part("Gadget, SPI", "A"), part("Gadget, I2C interface", "B")]
        r = pg.ask_parts(pg.build_parts_graph(pg.PartsDeps(find=lambda q, n: (rows, "es-semantic"), ontology=g)), "I2C 가젯 알파 부품 추천")
        self.assertEqual(r["conditions"], [])
        self.assertEqual([p["name"] for p in r["parts"]], ["A", "B"])
        self.assertNotIn("조건:", r["answer"])


if __name__ == "__main__":
    unittest.main()
