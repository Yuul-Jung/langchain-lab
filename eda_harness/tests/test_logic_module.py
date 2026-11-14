"""범용 로직 모듈: 핀 개수·이름·역할 구성이 다른 모듈이 같은 코드로 처리되는지 검증한다."""
import unittest

from helpers import by_role, clone, codes
from edaharness import checks
from edaharness.intent import SCHEMA_ID, validate_intent
from edaharness.ratings import RatingsError, logic_module_block
from edaharness.synth import SynthesisError, synthesize


def e(v, basis="datasheet", note=""):
    return {"value": v, "basis": basis, "note": note}


SINK33 = {"name": "3.3V 입력", "signals": {"G": {"vih_min_v": e(2.0), "vmax_v": e(3.45), "cin_f": e(8e-12)}}}
HOST33 = {"voh_min_v": e(2.9, "derived"), "voh_max_v": e(3.3, "derived")}
SUP5 = {"min_v": e(4.5), "max_v": e(5.5), "current_a": e(0.02)}


def out_sig(v=5.0):
    return {"voh_v": e(v, "derived"), "voh_tol": e(0.1, "derived"), "iout_max_a": e(0.001, "assumed")}


def in_sig(vih=2.0, vmax=5.5):
    return {"vih_min_v": e(vih, "assumed"), "vmax_v": e(vmax, "derived")}


# 모양 A: 입력 1 · 출력 1 · 전원 1 · 접지 1 (4핀)
MOD_A = {"name": "A", "pin_order_verified": True,
         "pins": [{"number": "1", "name": "VCC", "role": "vcc"}, {"number": "2", "name": "TRIG", "role": "in"},
                  {"number": "3", "name": "ECHO", "role": "out"}, {"number": "4", "name": "GND", "role": "gnd"}],
         "supply": {"VCC": SUP5}, "signals": {"TRIG": in_sig(), "ECHO": out_sig()}}
CONN_A = {"VCC": {"rail": "INPUT"}, "TRIG": {"host_out": HOST33},
          "ECHO": {"sink_part": SINK33, "sink_pin": "G", "signal_max_hz": 10000}}

# 모양 B: 입력 3 · 출력 2 · 전원 2(서로 다른 전압) · 접지 2 · 미연결 1 (10핀, 핀 순서·이름 전혀 다름)
MOD_B = {"name": "B", "pin_order_verified": True,
         "pins": [{"number": str(i + 1), "name": n, "role": r} for i, (n, r) in enumerate([
             ("G1", "gnd"), ("SDA_IN", "in"), ("V5", "vcc"), ("OUT_A", "out"), ("CLK", "in"),
             ("V33", "vcc"), ("OUT_B", "out"), ("G2", "gnd"), ("RSV", "nc"), ("EN", "in")])],
         "supply": {"V5": SUP5, "V33": {"min_v": e(3.0), "max_v": e(3.6), "current_a": e(0.005)}},
         "signals": {"SDA_IN": in_sig(), "CLK": in_sig(), "EN": in_sig(2.0, 3.6),
                     "OUT_A": out_sig(5.0), "OUT_B": out_sig(5.0)}}
CONN_B = {"V5": {"rail": "INPUT"}, "V33": {"rail": "B1"}, "RSV": {"reason": "제조사 예약 핀"},
          "SDA_IN": {"host_out": HOST33}, "CLK": {"host_out": HOST33}, "EN": {"host_out": HOST33},
          "OUT_A": {"sink_part": SINK33, "sink_pin": "G", "signal_max_hz": 10000},
          "OUT_B": {"sink_part": SINK33, "sink_pin": "G", "signal_max_hz": 10000}}

# 모양 C: 신호 없이 전원만 쓰는 모듈 (2핀)
MOD_C = {"name": "C", "pin_order_verified": True,
         "pins": [{"number": "1", "name": "P", "role": "vcc"}, {"number": "2", "name": "N", "role": "gnd"}],
         "supply": {"P": SUP5}, "signals": {}}


def intent_of(blocks):
    return {"schema": SCHEMA_ID, "source": {"kind": "manual"},
            "power_input": {"connector": "dc", "voltage_v": 5.0},
            "blocks": blocks, "assumptions": [], "questions": [], "unparsed": []}


def ldo_block():
    return {"id": "B1", "type": "ldo", "params": {"rail_in": "INPUT", "vout_v": 3.3, "iout_max_a": 0.3}}


def findings(x):
    return checks.structural(x) + checks.semantic(x) + checks.electrical(x)


def build(mod, conn, bid="B1", pre=()):
    blk, ass = logic_module_block(mod, conn, bid)
    it = intent_of(list(pre) + [blk])
    it["assumptions"] = ass
    return it


class Shapes(unittest.TestCase):
    def test_shape_a_passes(self):
        it = build(MOD_A, CONN_A)
        self.assertEqual(validate_intent(it), [])
        self.assertEqual(codes(findings(synthesize(it, "t"))), set())

    def test_shape_b_many_pins_two_rails_nc(self):
        it = build(MOD_B, CONN_B, "B2", pre=[ldo_block()])
        self.assertEqual(validate_intent(it), [])
        x = synthesize(it, "t")
        self.assertEqual(codes(findings(x)), set())
        j = by_role(x, "B2", "J_MOD")
        self.assertEqual(j["part"], "Conn_01x10")
        self.assertEqual(j["no_connect"], {"9": "제조사 예약 핀"})
        self.assertEqual(j["pins"]["3"], "+5V")
        self.assertEqual(j["pins"]["6"], "+3V3")
        self.assertEqual(by_role(x, "B2", "J_HOST")["part"], "Conn_01x06")        # 신호 5 + GND
        self.assertEqual(len([c for c in x["components"].values() if c["role"].startswith("R_TOP_")]), 2)
        self.assertEqual(len([c for c in x["components"].values() if c["role"].startswith("C_DEC_")]), 2)

    def test_shape_c_power_only(self):
        x = synthesize(build(MOD_C, {"P": {"rail": "INPUT"}}), "t")
        self.assertEqual(codes(findings(x)), set())
        self.assertFalse([c for c in x["components"].values() if c["role"] == "J_HOST"])

    def test_pin_order_independence(self):
        # 같은 모듈 A를 다른 핀 순서로 정의해도 같은 코드로 올바르게 연결된다
        m = clone(MOD_A)
        order = ["GND", "ECHO", "TRIG", "VCC"]
        role = {"VCC": "vcc", "TRIG": "in", "ECHO": "out", "GND": "gnd"}
        m["pins"] = [{"number": str(i + 1), "name": n, "role": role[n]} for i, n in enumerate(order)]
        x = synthesize(build(m, CONN_A), "t")
        self.assertEqual(codes(findings(x)), set())
        self.assertEqual(by_role(x, "B1", "J_MOD")["pins"]["4"], "+5V")

    def test_pin_names_have_no_meaning(self):
        # 이름이 TRIG/ECHO가 아니어도, 역할만 맞으면 동일하게 동작
        m = clone(MOD_A)
        ren = {"TRIG": "Q1", "ECHO": "Q2", "VCC": "X", "GND": "Y"}
        m["pins"] = [dict(p, name=ren[p["name"]]) for p in m["pins"]]
        m["supply"] = {"X": SUP5}
        m["signals"] = {"Q1": in_sig(), "Q2": out_sig()}
        conn = {"X": {"rail": "INPUT"}, "Q1": {"host_out": HOST33},
                "Q2": {"sink_part": SINK33, "sink_pin": "G", "signal_max_hz": 10000}}
        self.assertEqual(codes(findings(synthesize(build(m, conn), "t"))), set())

    def test_many_voltage_combinations(self):
        for vs, sv, vmax in [(5.0, 2.0, 3.45), (12.0, 1.17, 1.98), (3.6, 1.2, 1.98), (24.0, 2.0, 5.5)]:
            with self.subTest(vs=vs, vmax=vmax):
                m = clone(MOD_A)
                m["signals"]["ECHO"] = out_sig(vs)
                sink = {"name": "s", "signals": {"G": {"vih_min_v": e(sv), "vmax_v": e(vmax), "cin_f": e(8e-12)}}}
                conn = dict(CONN_A, ECHO={"sink_part": sink, "sink_pin": "G", "signal_max_hz": 10000})
                self.assertEqual(codes(findings(synthesize(build(m, conn), "t"))), set())


class Refusals(unittest.TestCase):
    def test_role_required_not_guessed_from_name(self):
        m = clone(MOD_A); del m["pins"][0]["role"]
        with self.assertRaises(RatingsError):
            logic_module_block(m, CONN_A)

    def test_bidirectional_role_unsupported(self):
        m = clone(MOD_A); m["pins"][1]["role"] = "io"
        with self.assertRaises(RatingsError):
            logic_module_block(m, CONN_A)

    def test_missing_connection_info(self):
        with self.assertRaises(RatingsError):
            logic_module_block(MOD_A, {"VCC": {"rail": "INPUT"}})

    def test_nc_needs_reason(self):
        with self.assertRaises(RatingsError):
            logic_module_block(MOD_B, dict(CONN_B, RSV={"reason": " "}))

    def test_missing_supply_spec(self):
        m = clone(MOD_A); m["supply"] = {}
        with self.assertRaises(RatingsError):
            logic_module_block(m, CONN_A)

    def test_unknown_rail(self):
        with self.assertRaises(SynthesisError):
            synthesize(build(MOD_A, dict(CONN_A, VCC={"rail": "B9"})), "t")

    def test_rail_outside_range(self):
        m = clone(MOD_A); m["supply"] = {"VCC": {"min_v": e(2.7), "max_v": e(3.6), "current_a": e(0.02)}}
        with self.assertRaises(SynthesisError):
            synthesize(build(m, CONN_A), "t")

    def test_host_too_weak(self):
        weak = {"voh_min_v": e(1.5, "assumed"), "voh_max_v": e(1.8, "assumed")}
        with self.assertRaises(SynthesisError):
            synthesize(build(MOD_A, dict(CONN_A, TRIG={"host_out": weak})), "t")

    def test_host_too_strong(self):
        m = clone(MOD_A); m["signals"]["TRIG"] = in_sig(2.0, 3.0)
        with self.assertRaises(SynthesisError):
            synthesize(build(m, CONN_A), "t")

    def test_duplicate_or_gap_pin_numbers_invalid(self):
        it = build(MOD_A, CONN_A)
        it["blocks"][0]["params"]["pins"][1]["number"] = "1"
        self.assertTrue(validate_intent(it))
        it = build(MOD_A, CONN_A)
        it["blocks"][0]["params"]["pins"][1]["number"] = "7"
        self.assertTrue(validate_intent(it))

    def test_needs_supply_and_ground(self):
        it = build(MOD_A, CONN_A)
        it["blocks"][0]["params"]["pins"][3]["role"] = "nc"
        it["blocks"][0]["params"]["pins"][3]["reason"] = "x"
        self.assertTrue(validate_intent(it))

    def test_unknown_key_rejected(self):
        it = build(MOD_A, CONN_A)
        it["blocks"][0]["params"]["pins"][0]["vendor"] = "x"
        self.assertTrue(validate_intent(it))

    def test_pin_order_unverified_warns(self):
        m = dict(MOD_A, pin_order_verified=False)
        x = synthesize(build(m, CONN_A), "t")
        self.assertIn("MODULE_PIN_ORDER_UNVERIFIED", codes(findings(x), "WARN"))
        self.assertEqual(codes(findings(x)), set())

    def test_assumptions_recorded_and_datasheet_not(self):
        _, ass = logic_module_block(MOD_A, CONN_A)
        f = {a["field"] for a in ass}
        self.assertIn("보내는 쪽.ECHO.iout_max_a", f)
        self.assertIn("모듈 핀 TRIG.vih_min_v", f)
        self.assertNotIn("모듈 핀 VCC.min_v", f)


class Faults(unittest.TestCase):
    def _x(self):
        return clone(synthesize(build(MOD_B, CONN_B, "B2", pre=[ldo_block()]), "t"))

    def test_swapped_supply_pins(self):
        x = self._x()
        j = by_role(x, "B2", "J_MOD")
        j["pins"]["3"], j["pins"]["6"] = j["pins"]["6"], j["pins"]["3"]       # 5V <-> 3.3V 교환
        self.assertIn("MODULE_SUPPLY_RANGE", codes(findings(x)))

    def test_ground_pin_not_grounded(self):
        x = self._x()
        by_role(x, "B2", "J_MOD")["pins"]["1"] = "+5V"
        self.assertIn("MODULE_TOPOLOGY", codes(findings(x)))

    def test_missing_decoupling(self):
        x = self._x()
        del x["components"]["B2.C_DEC_2"]
        self.assertIn("DECOUPLING_MISSING", codes(findings(x)))

    def test_divider_resistor_wrong_second_output(self):
        x = self._x()
        by_role(x, "B2", "R_TOP_2")["params"]["r_ohm"] = 100.0
        self.assertIn("LEVEL_SINK_VMAX", codes(findings(x)))

    def test_nc_pin_connected(self):
        x = self._x()
        j = by_role(x, "B2", "J_MOD")
        del j["no_connect"]["9"]
        j["pins"]["9"] = "GND"
        self.assertIn("MODULE_TOPOLOGY", codes(findings(x)))

    def test_input_limit_changed(self):
        x = self._x()
        for e_ in x["blocks"]["B2"]["params"]["pins"]:
            if e_["role"] == "in":
                e_["vmax_v"] = 3.0
        self.assertIn("MODULE_IN_VMAX", codes(findings(x)))

    def test_input_threshold_changed(self):
        x = self._x()
        for e_ in x["blocks"]["B2"]["params"]["pins"]:
            if e_["role"] == "in":
                e_["vih_min_v"] = 3.1
        self.assertIn("MODULE_IN_VIH", codes(findings(x)))

    def test_two_signals_merged_into_one_net(self):
        # 모듈 입력 두 개를 같은 넷으로 합친 경우: 각 연결은 직결로 보이지만 신호가 섞여 버림
        x = self._x()
        j, h = by_role(x, "B2", "J_MOD"), by_role(x, "B2", "J_HOST")
        j["pins"]["5"] = j["pins"]["2"]       # CLK(세 번째 신호)을 SDA_IN(첫 번째) 넷에 합침
        h["pins"]["3"] = h["pins"]["1"]
        e_ = [f for f in findings(x) if f["code"] == "MODULE_TOPOLOGY"]
        self.assertEqual([f["message"] for f in e_], ["서로 다른 호스트 신호가 같은 넷을 씀"])

    def test_host_net_shared(self):
        x = self._x()
        h = by_role(x, "B2", "J_HOST")
        h["pins"]["2"] = h["pins"]["1"]
        self.assertIn("MODULE_TOPOLOGY", codes(findings(x)))


if __name__ == "__main__":
    unittest.main()
