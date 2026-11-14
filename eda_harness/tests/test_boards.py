import unittest

from edaharness import boards
from edaharness.ratings import level_link_block
from edaharness.boards import BoardError

XDC = """## x
##Pmod Header JA
#set_property -dict { PACKAGE_PIN J1   IOSTANDARD LVCMOS33 } [get_ports {JA[0]}];#Sch name = JA1
#set_property -dict { PACKAGE_PIN L2   IOSTANDARD LVCMOS33 } [get_ports {JA[1]}];#Sch name = JA2

##Pmod Header JXADC
#set_property -dict { PACKAGE_PIN J3   IOSTANDARD LVCMOS33 } [get_ports {JXADC[0]}];#Sch name = XA1_P
##VGA Connector
#set_property -dict { PACKAGE_PIN G19  IOSTANDARD LVCMOS33 } [get_ports {vgaRed[0]}];#Sch name = R0
"""
DS = "intro\nLVCMOS33    –0.300   0.8   2.000   3.450   0.400\n\fCIN Die input capacitance at the pad – – 8 pF\n"
ITEMS = [
    {"key": "vih_min_v", "value": 2.0, "quote": "LVCMOS33 –0.300 0.8 2.000 3.450", "locator": "Table 8"},
    {"key": "vmax_v", "value": 3.45, "quote": "LVCMOS33 –0.300 0.8 2.000 3.450", "locator": "Table 8"},
    {"key": "cin_f", "value": 8e-12, "quote": "Die input capacitance at the pad – – 8 pF", "locator": "Table 3"},
]


def prof():
    items = [dict(i) for i in ITEMS]
    items[2]["quote_number"] = 8          # 인용문에는 8 pF, 값은 SI(F)로 환산
    return boards.build_profile("B", XDC, "xdc", DS, "ds", items, ["JA"], ["JXADC"])


class Boards(unittest.TestCase):
    def test_parse_only_pmod_headers(self):
        h = boards.parse_xdc(XDC)
        self.assertEqual(sorted(h), ["JA", "JXADC"])
        self.assertEqual(h["JA"][0], {"sch": "JA1", "fpga_pin": "J1", "iostandard": "LVCMOS33", "port": "JA[0]"})

    def test_missing_header_refused(self):
        with self.assertRaises(BoardError):
            boards.build_profile("B", XDC, "x", DS, "d", [], ["JD"])

    def test_fabricated_quote_refused(self):
        bad = [dict(ITEMS[0], quote="LVCMOS33 1.000 9.9")]
        with self.assertRaises(BoardError):
            boards.build_profile("B", XDC, "x", DS, "d", bad, ["JA"])

    def test_number_not_in_quote_refused(self):
        bad = [dict(ITEMS[0], value=2.4)]
        with self.assertRaises(BoardError):
            boards.build_profile("B", XDC, "x", DS, "d", bad, ["JA"])

    def test_page_found(self):
        self.assertEqual(boards.page_of(DS, "Die input capacitance at the pad"), 2)

    def test_proposed_is_assumed_until_approved(self):
        p = prof()
        part = boards.sink_part(p, "JA1")
        self.assertTrue(all(v["basis"] == "assumed" for v in part["signals"]["GPIO"].values()))
        q = boards.sink_part(boards.approve(p, "사용자가 원문 확인"), "JA1")
        self.assertTrue(all(v["basis"] == "datasheet" for v in q["signals"]["GPIO"].values()))

    def test_approve_requires_reason(self):
        with self.assertRaises(BoardError):
            boards.approve(prof(), "  ")

    def test_unknown_signal_refused(self):
        with self.assertRaises(BoardError):
            boards.sink_part(prof(), "JD1")

    def test_feeds_level_link(self):
        src = {"name": "s", "signals": {"O": {"voh_v": {"value": 5.0, "basis": "derived"},
                                              "voh_tol": {"value": 0.1, "basis": "derived"},
                                              "iout_max_a": {"value": 0.001, "basis": "assumed"}}}}
        blk, ass = level_link_block(src, "O", boards.sink_part(prof(), "JA2"), "GPIO", 1000)
        self.assertEqual(blk["params"]["sink_vmax_v"], 3.45)


if __name__ == "__main__":
    unittest.main()


# 실제 Digilent 보드 파일 3종에서 가져온 줄 형식 (표기가 서로 다르다)
NEXYS = """##Pmod Header JA
#set_property -dict { PACKAGE_PIN C17   IOSTANDARD LVCMOS33 } [get_ports { JA[1] }]; #IO_L20N_T3_A19_15 Sch=ja[1]
#set_property -dict { PACKAGE_PIN D18   IOSTANDARD LVCMOS33 } [get_ports { JA[2] }]; #IO_L21N_T3_DQS_A18_15 Sch=ja[2]
##Pmod Header JD
#set_property -dict { PACKAGE_PIN H4    IOSTANDARD LVCMOS33 } [get_ports { JD[1] }]; #IO_L21N_T3_DQS_35 Sch=jd[1]
"""
ARTY = """## Pmod Header JA
set_property -dict { PACKAGE_PIN G13   IOSTANDARD LVCMOS33 } [get_ports { ja[0] }]; #IO_0_15 Sch=ja[1]
set_property -dict { PACKAGE_PIN B11   IOSTANDARD LVCMOS33 } [get_ports { ja[1] }]; #IO_L4P_T0_15 Sch=ja[2]
"""
NO_SCH = """## Pmod Header JA
set_property -dict { PACKAGE_PIN G13 IOSTANDARD LVCMOS33 } [get_ports {pmod_a[0]}]
"""
UNKNOWN = """## Pmod Header JA
set_property PACKAGE_PIN G13 [get_ports ja0]
set_property IOSTANDARD LVCMOS33 [get_ports ja0]
"""


class XdcFormats(unittest.TestCase):
    def test_format_with_spaces_and_sch_equals(self):
        h = boards.parse_xdc(NEXYS)
        self.assertEqual([(p["sch"], p["fpga_pin"]) for p in h["JA"]], [("JA1", "C17"), ("JA2", "D18")])
        self.assertEqual(h["JD"][0]["sch"], "JD1")

    def test_active_lines_and_zero_based_port(self):
        h = boards.parse_xdc(ARTY)
        self.assertEqual([(p["sch"], p["port"]) for p in h["JA"]], [("JA1", "ja[0]"), ("JA2", "ja[1]")])

    def test_label_falls_back_to_port_when_no_sch_comment(self):
        self.assertEqual(boards.parse_xdc(NO_SCH)["JA"][0]["sch"], "PMOD_A0")

    def test_unknown_format_is_refused_not_silently_dropped(self):
        # PACKAGE_PIN과 IOSTANDARD가 다른 줄에 있는 형식 — 읽지 못한 줄이 있으면 오류
        with self.assertRaises(BoardError):
            boards.parse_xdc(UNKNOWN)


class FormatIndependence(unittest.TestCase):
    def test_profile_from_any_importer_table(self):
        # XDC가 아닌 다른 방식(예: 다른 도구의 보드 파일)으로 읽은 표도 그대로 받는다
        table = {"P1": [{"sch": "P1_1", "fpga_pin": "A1", "iostandard": "LVCMOS33", "port": "x"}]}
        items = [dict(i) for i in ITEMS]
        items[2]["quote_number"] = 8
        p = boards.build_profile("임의 보드", table, "다른 형식에서 읽음", DS, "ds", items, ["P1"])
        self.assertEqual(p["signals"]["P1_1"]["fpga_pin"], "A1")
        self.assertEqual(p["pins_source"], "다른 형식에서 읽음")
        self.assertNotIn("xdc_source", p)
