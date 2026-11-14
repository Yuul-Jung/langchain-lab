import unittest

from helpers import by_role, clone, codes, intent, ir
from edaharness import checks
from edaharness.intent import parse_text
from edaharness.synth import SynthesisError, sha256_of, synthesize


def all_findings(x):
    return checks.structural(x) + checks.semantic(x) + checks.electrical(x)


class Synthesis(unittest.TestCase):
    def test_examples_pass_g1_g3(self):
        for k in ("usb_ldo", "motor", "blink", "mix"):
            with self.subTest(k):
                self.assertEqual(codes(all_findings(ir(k))), set())

    def test_deterministic(self):
        self.assertEqual(sha256_of(ir("mix")), sha256_of(ir("mix")))

    def test_refdes_sequence(self):
        refs = sorted(c["ref"] for c in ir("mix")["components"].values())
        self.assertIn("J1", refs)
        self.assertIn("#FLG01", refs)
        self.assertEqual(len(refs), len(set(refs)))

    def test_power_input_first(self):
        x = ir("usb_ldo")
        self.assertEqual(next(iter(x["components"].values()))["block"], "P0")

    def test_led_current_never_exceeds_target(self):
        for v in (3.3, 5.0, 9.0, 12.0):
            it = parse_text(f"{v}V 입력 전원 LED")
            x = synthesize(it, "t")
            self.assertLessEqual(x["blocks"]["B1"]["design"]["i_led_a"], 0.002 + 1e-12)

    def test_555_frequency_range(self):
        for f in (0.1, 1, 10, 100, 1000, 5000):
            with self.subTest(f=f):
                x = synthesize(parse_text(f"9V 입력 LED {f}Hz 깜빡"), "t")
                self.assertLessEqual(x["blocks"]["B1"]["design"]["f_error"], 0.10)

    def test_ldo_cannot_shadow_input_rail(self):
        with self.assertRaises(SynthesisError):
            synthesize(parse_text("USB 입력에서 5V LDO"), "t")

    def test_led_unlightable_is_synthesis_error(self):
        it = parse_text("5V 입력에서 1.8V LDO, 파란 전원 LED")
        with self.assertRaises(SynthesisError):
            synthesize(it, "t")

    def test_blocking_intent_refused(self):
        with self.assertRaises(SynthesisError):
            synthesize(parse_text("LDO 하나"), "t")

    def test_mosfet_selection(self):
        x = synthesize(parse_text("12V 입력, 12V 모터 2A를 3.3V MCU로 제어"), "t")
        self.assertEqual(x["blocks"]["B1"]["design"]["mosfet"], "AO3400A")
        x = synthesize(parse_text("12V 입력, 12V 히터 8A를 5V 로직으로 제어"), "t")
        self.assertEqual(x["blocks"]["B1"]["design"]["mosfet"], "IRLZ44N")
        self.assertEqual(x["blocks"]["B1"]["design"]["load_connector"], "TB_1x02")
        self.assertIsNone(x["blocks"]["B1"]["design"]["flyback"])

    def test_no_mosfet_fits_is_exposed_not_hidden(self):
        x = synthesize(parse_text("12V 입력, 12V 모터 8A를 3.3V MCU로 제어"), "t")
        self.assertIn("후보 없음", x["blocks"]["B1"]["design"]["mosfet_reason"])
        self.assertIn("FET_VGS_DRIVE", codes(checks.electrical(x)))


class SemanticFaults(unittest.TestCase):
    """정상 IR에 결함을 주입해 각 검사가 실제로 잡는지 확인."""

    def setUp(self):
        self.ok = ir("usb_ldo")

    def sem(self, x):
        return codes(checks.semantic(x))

    def test_unassigned_pin(self):
        x = clone(self.ok)
        del by_role(x, "B1", "U")["pins"]["1"]
        self.assertIn("PIN_UNASSIGNED", self.sem(x))

    def test_pin_both(self):
        x = clone(self.ok)
        by_role(x, "B1", "U")["no_connect"]["1"] = "test"
        self.assertIn("PIN_BOTH_NET_AND_NC", self.sem(x))

    def test_pin_identity_is_number_not_name(self):
        x = clone(self.ok)
        u = by_role(x, "B1", "U")
        u["pins"]["GND"] = u["pins"].pop("1")
        self.assertTrue({"PIN_UNKNOWN", "PIN_UNASSIGNED"} <= self.sem(x))

    def test_duplicate_ref(self):
        x = clone(self.ok)
        by_role(x, "B1", "C_OUT")["ref"] = by_role(x, "B1", "C_IN")["ref"]
        self.assertIn("REF_DUPLICATE", self.sem(x))

    def test_bad_ref_prefix(self):
        x = clone(self.ok)
        by_role(x, "B1", "C_OUT")["ref"] = "R99"
        self.assertIn("REF_FORMAT", self.sem(x))

    def test_missing_footprint(self):
        x = clone(self.ok)
        by_role(x, "B1", "U")["footprint"] = ""
        self.assertIn("FOOTPRINT_MISSING", self.sem(x))

    def test_ldo_output_shorted_to_input(self):
        x = clone(self.ok)
        by_role(x, "B1", "U")["pins"]["2"] = "+5V"
        self.assertIn("ERC_POWER_OUT_CONFLICT", self.sem(x))

    def test_missing_pwr_flag(self):
        x = clone(self.ok)
        del x["components"]["PWR.FLAG_5V"]
        s = self.sem(x)
        self.assertIn("ERC_EXTERNAL_NO_FLAG", s)
        self.assertIn("ERC_POWER_IN_UNDRIVEN", s)

    def test_dangling_net(self):
        x = clone(self.ok)
        by_role(x, "B2", "LED")["pins"]["2"] = "GND"     # R_LED 출력이 혼자 남음
        self.assertIn("NET_SINGLE_PIN", self.sem(x))

    def test_undeclared_net(self):
        x = clone(self.ok)
        by_role(x, "B2", "LED")["pins"]["1"] = "GNDX"
        self.assertIn("NET_UNDECLARED", self.sem(x))

    def test_power_net_name_must_match_voltage(self):
        x = clone(self.ok)
        x["nets"]["+3V3"]["voltage_v"] = 3.0
        self.assertIn("POWER_NET_NAME", self.sem(x))

    def test_input_undriven(self):
        x = clone(ir("blink"))
        # 555 RESET 입력을 다른 구동원이 없는 새 넷에 혼자 연결 (C_CV와 공유하지 않게)
        x["nets"]["N_FLOAT"] = {"kind": "signal", "voltage_v": None, "external_supply": False, "current_a": 0}
        u = by_role(x, "B1", "U")
        u["pins"]["4"] = "N_FLOAT"
        u["pins"]["5"] = "N_FLOAT"
        by_role(x, "B1", "C_CV")["pins"]["1"] = "GND"
        x["nets"].pop("N_B1_CV")
        self.assertIn("ERC_INPUT_UNDRIVEN", self.sem(x))

    def test_structural_closed(self):
        x = clone(self.ok)
        x["extra"] = 1
        self.assertIn("IR_TOP_KEYS", codes(checks.structural(x)))
        y = clone(self.ok)
        y["components"]["B1.U"]["id"] = "B1.X"
        self.assertIn("IR_ID_MISMATCH", codes(checks.structural(y)))


class ElectricalFaults(unittest.TestCase):
    def ele(self, x):
        return codes(checks.electrical(x))

    def test_ldo_thermal_and_led_headroom(self):
        x = synthesize(parse_text("12V 입력에서 3V3 LDO, 파란 전원 LED"), "t")
        self.assertTrue({"LDO_THERMAL", "LED_HEADROOM"} <= self.ele(x))

    def test_ldo_dropout(self):
        x = synthesize(parse_text("USB 입력에서 3.3V LDO"), "t")
        self.assertNotIn("LDO_DROPOUT", self.ele(x))
        x = synthesize(parse_text("4V 입력에서 3.3V LDO"), "t")
        self.assertIn("LDO_DROPOUT", self.ele(x))

    def test_ldo_vin_max(self):
        x = synthesize(parse_text("24V 입력에서 5V LDO 출력 50mA"), "t")
        self.assertIn("LDO_VIN_MAX", self.ele(x))

    def test_ldo_rail_overload(self):
        x = clone(ir("usb_ldo"))
        x["nets"]["+3V3"]["current_a"] = 0.5
        self.assertIn("LDO_RAIL_OVERLOAD", self.ele(x))

    def test_ldo_cout_too_small(self):
        x = clone(ir("usb_ldo"))
        by_role(x, "B1", "C_OUT")["params"]["c_f"] = 1e-6
        self.assertIn("LDO_COUT", self.ele(x))

    def test_usb_default_power(self):
        x = synthesize(parse_text("USB 입력에서 3.3V LDO 출력 600mA"), "t")
        self.assertIn("USB_DEFAULT_POWER", self.ele(x))

    def test_usb_rd_missing(self):
        x = clone(ir("usb_ldo"))
        by_role(x, "P0", "R_CC1")["params"]["r_ohm"] = 10000
        self.assertIn("USB_CC_RD", self.ele(x))

    def test_555_vcc(self):
        x = synthesize(parse_text("20V 입력 LED 1Hz 깜빡"), "t")
        self.assertIn("NE555_VCC", self.ele(x))

    def test_flyback_polarity(self):
        x = clone(ir("motor"))
        d = by_role(x, "B1", "D_FLY")
        d["pins"]["1"], d["pins"]["2"] = d["pins"]["2"], d["pins"]["1"]
        self.assertIn("FLYBACK_POLARITY", self.ele(x))

    def test_flyback_missing(self):
        x = clone(ir("motor"))
        del x["components"]["B1.D_FLY"]
        self.assertIn("FLYBACK_MISSING", self.ele(x))

    def test_555_freq_recomputed_from_parts(self):
        x = clone(ir("blink"))
        by_role(x, "B1", "R_B")["params"]["r_ohm"] = 10000      # design 값은 그대로 둔다
        self.assertIn("NE555_FREQ", self.ele(x))

    def test_led_current_recomputed_from_parts(self):
        x = clone(ir("usb_ldo"))
        by_role(x, "B2", "R_LED")["params"]["r_ohm"] = 300
        self.assertIn("LED_CURRENT_TARGET", self.ele(x))

    def test_led_resistor_rounds_up(self):
        from edaharness.synth import _led_resistor
        r, i, _ = _led_resistor(4.04, 2.0, 0.002, "t")      # 이상값 1020Ω
        self.assertEqual(r, 1100)
        self.assertLessEqual(i, 0.002)

    def test_cap_voltage(self):
        x = clone(ir("motor"))
        by_role(x, "P0", "C_BULK")["params"]["voltage_rating_v"] = 16
        self.assertIn("CAP_VOLTAGE", self.ele(x))

    def test_connector_current(self):
        x = clone(ir("motor"))
        by_role(x, "P0", "J_IN")["params"]["current_max_a"] = 1.0
        self.assertIn("CONNECTOR_CURRENT", self.ele(x))

    def test_unverified_parts_warn(self):
        self.assertIn("PART_DATA_UNVERIFIED", codes(checks.electrical(ir("motor")), "WARN"))

    def test_assumptions_surface(self):
        self.assertIn("ASSUMPTION", codes(checks.electrical(ir("usb_ldo")), "INFO"))


if __name__ == "__main__":
    unittest.main()
