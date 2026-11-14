"""룰팩 합성기: IntentSpec -> Design IR.

결정론적이다 (같은 IntentSpec -> 바이트 단위로 같은 IR). LLM은 여기 관여하지 않는다.
각 블록은 부품 선택·값 계산의 근거를 IR의 blocks.<id>.design에 남긴다.
"""
from __future__ import annotations

import copy
import hashlib
import json

from . import library
from .intent import LED_COLORS, validate_intent, blocking_questions
from .units import (E24, cap_voltage_rating, divider_window, e_nearest, format_si,
                    rail_name, rc_rise_time)

IR_SCHEMA = "eda.ir/1"


class SynthesisError(Exception):
    pass


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_of(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


class Builder:
    def __init__(self, project: str):
        self.project = project
        self.nets: dict = {}
        self.components: dict = {}
        self.blocks: dict = {}
        self.order: list = []

    # ---- nets
    def net(self, name, kind="signal", voltage=None, external=False, owner=None):
        cur = self.nets.get(name)
        spec = {"kind": kind, "voltage_v": voltage, "external_supply": external}
        if cur is None:
            self.nets[name] = dict(spec, current_a=0.0, owner=owner)
        else:
            if any(cur[k] != spec[k] for k in spec) or (owner and cur["owner"] and cur["owner"] != owner):
                raise SynthesisError(
                    f"넷 {name} 정의 충돌: 기존 {cur['owner']} / 신규 {owner} — "
                    "서로 다른 소스가 같은 레일 이름을 만들 수 없음")
        return name

    def load(self, net, amps):
        self.nets[net]["current_a"] = round(self.nets[net]["current_a"] + amps, 6)

    def voltage(self, net):
        v = self.nets[net]["voltage_v"]
        if v is None:
            raise SynthesisError(f"넷 {net}의 전압을 모름")
        return v

    # ---- components
    def comp(self, block, role, part_key, value, pins, params=None,
             footprint=None, no_connect=None):
        part = library.get(part_key)
        cid = f"{block}.{role}"
        if cid in self.components:
            raise SynthesisError(f"컴포넌트 id 중복 {cid}")
        for n in pins.values():
            if n not in self.nets:
                raise SynthesisError(f"{cid}: 선언되지 않은 넷 {n}")
        merged = dict(part.params)
        merged.update(params or {})
        self.components[cid] = {
            "id": cid, "ref": None, "part": part_key, "value": value,
            "footprint": part.default_footprint if footprint is None else footprint,
            "block": block, "role": role, "params": merged,
            "pins": dict(pins), "no_connect": dict(no_connect or {})}
        self.order.append(cid)
        return cid

    def resistor(self, block, role, ohms, a, b, purpose=""):
        return self.comp(block, role, "R", format_si(ohms),
                         {"1": a, "2": b}, {"r_ohm": ohms, "purpose": purpose})

    def capacitor(self, block, role, farads, a, b, net_v):
        rating = cap_voltage_rating(net_v)
        fp = ("Capacitor_SMD:C_0805_2012Metric" if farads >= 4.7e-6
              else "Capacitor_SMD:C_0603_1608Metric")
        return self.comp(block, role, "C", f"{format_si(farads)}/{rating:g}V",
                         {"1": a, "2": b}, {"c_f": farads, "voltage_rating_v": rating},
                         footprint=fp)

    def pwr_flag(self, net):
        return self.comp("PWR", f"FLAG_{net.strip('+').replace('.', '_')}",
                         "PWR_FLAG", "PWR_FLAG", {"1": net})


# ------------------------------------------------------------------ 블록 룰팩

def _ldo(b: Builder, bid, p, rails):
    vin_net = rails[p["rail_in"]]
    vin = b.voltage(vin_net)
    vout, iout = p["vout_v"], p["iout_max_a"]
    key = f"AMS1117-{vout:.1f}"
    out = b.net(rail_name(vout), "power", vout, False, owner=bid)
    b.comp(bid, "U", key, key, {"3": vin_net, "2": out, "1": "GND"})
    part = library.get(key)
    b.capacitor(bid, "C_IN", part.params["cin_min_f"], vin_net, "GND", vin)
    b.capacitor(bid, "C_OUT", part.params["cout_min_f"], out, "GND", vout)
    b.load(vin_net, iout + part.params["quiescent_a"])
    rails[bid] = out
    b.blocks[bid]["design"] = {
        "part": key, "vin_v": vin, "pd_worst_w": round((vin - vout) * iout, 4),
        "why": "AMS1117 고정 출력. 데이터시트 최소 Cin/Cout 적용."}


def _led_resistor(v_drive, vf, i_target, where):
    head = v_drive - vf
    if head <= 0:
        raise SynthesisError(f"{where}: 구동 전압 {v_drive:.2f}V가 LED Vf {vf}V 이하 — 점등 불가")
    r = e_nearest(head / i_target, mode="ceil")
    i = head / r
    return r, i, head


def _led_indicator(b: Builder, bid, p, rails):
    rail = rails[p["rail"]]
    v = b.voltage(rail)
    vf = LED_COLORS[p["color"]]
    r, i, head = _led_resistor(v, vf, p["current_a"], bid)
    na = b.net(f"N_{bid}_LED_A")
    b.resistor(bid, "R_LED", r, rail, na, "LED 전류 제한")
    b.comp(bid, "LED", "LED", f"LED_{p['color']}", {"2": na, "1": "GND"},
           {"vf_v": vf, "color": p["color"]})
    b.load(rail, i)
    b.blocks[bid]["design"] = {"r_ohm": r, "i_led_a": round(i, 6), "headroom_v": round(head, 3),
                               "p_r_w": round(i * i * r, 6),
                               "why": "R = (Vrail - Vf) / I, E24 올림 선택 (전류가 목표 이하)"}


def _blinker_555(b: Builder, bid, p, rails):
    rail = rails[p["rail"]]
    vcc = b.voltage(rail)
    f = p["freq_hz"]
    ra = 1000.0
    pick = None
    for c in (10e-6, 1e-6, 100e-9, 10e-9, 1e-9):
        rb_ideal = (1.44 / (f * c) - ra) / 2
        if 1e3 <= rb_ideal <= 1e6:
            pick = (c, e_nearest(rb_ideal))
            break
    if pick is None:
        raise SynthesisError(f"{bid}: {f}Hz를 Ra=1k, Rb∈[1k,1M] 범위로 만들 수 없음")
    c, rb = pick
    f_act = 1.44 / ((ra + 2 * rb) * c)
    n_dis, n_trig = b.net(f"N_{bid}_DIS"), b.net(f"N_{bid}_TRIG")
    n_cv, n_out, n_a = b.net(f"N_{bid}_CV"), b.net(f"N_{bid}_OUT"), b.net(f"N_{bid}_LED_A")
    b.comp(bid, "U", "NE555P", "NE555P",
           {"8": rail, "4": rail, "1": "GND", "7": n_dis, "2": n_trig,
            "6": n_trig, "5": n_cv, "3": n_out})
    b.resistor(bid, "R_A", ra, rail, n_dis, "타이밍 Ra")
    b.resistor(bid, "R_B", rb, n_dis, n_trig, "타이밍 Rb")
    b.capacitor(bid, "C_T", c, n_trig, "GND", vcc)
    b.capacitor(bid, "C_CV", 10e-9, n_cv, "GND", vcc)
    b.capacitor(bid, "C_DEC", 100e-9, rail, "GND", vcc)
    vf = LED_COLORS[p["color"]]
    voh = vcc - 1.7
    r, i, head = _led_resistor(voh, vf, p["led_current_a"], bid)
    b.resistor(bid, "R_LED", r, n_out, n_a, "LED 전류 제한")
    b.comp(bid, "LED", "LED", f"LED_{p['color']}", {"2": n_a, "1": "GND"},
           {"vf_v": vf, "color": p["color"]})
    b.load(rail, library.get("NE555P").params["icc_a"] + i)
    b.blocks[bid]["design"] = {
        "ra_ohm": ra, "rb_ohm": rb, "ct_f": c, "f_target_hz": f,
        "f_actual_hz": round(f_act, 6), "f_error": round(abs(f_act - f) / f, 6),
        "voh_v": round(voh, 3), "i_led_a": round(i, 6), "p_r_led_w": round(i * i * r, 6),
        "why": "f = 1.44 / ((Ra + 2Rb)·C), C는 Rb가 1k~1M에 들도록 큰 값부터 선택"}


MOSFET_CANDIDATES = ("AO3400A", "IRLZ44N")


def _mosfet_ok(part, v, i, vctrl):
    pr = part.params
    return (pr["vds_v"] >= 1.5 * v and i <= 0.5 * pr["id_a"]
            and vctrl >= pr["rds_spec_vgs_v"] and i * i * pr["rds_on_ohm"] <= pr["pd_max_w"])


def _lowside_switch(b: Builder, bid, p, rails):
    rail = rails[p["rail"]]
    v = b.voltage(rail)
    i, vctrl = p["load_current_a"], p["control_v"]
    chosen = next((k for k in MOSFET_CANDIDATES
                   if _mosfet_ok(library.get(k), v, i, vctrl)), None)
    reason = "조건(Vds≥1.5V, Id≤50%, Vctrl≥Rds 규격 Vgs, Pd)을 만족하는 첫 후보"
    if chosen is None:
        chosen = MOSFET_CANDIDATES[-1]
        reason = "조건을 만족하는 후보 없음 — 가장 큰 후보를 넣고 G3에서 FAIL로 드러낸다"
    n_d, n_g, n_c = b.net(f"N_{bid}_DRAIN"), b.net(f"N_{bid}_GATE"), b.net(f"N_{bid}_CTRL")
    conn = "Conn_01x02" if i <= library.get("Conn_01x02").params["current_max_a"] else "TB_1x02"
    b.comp(bid, "J_LOAD", conn, "LOAD", {"1": rail, "2": n_d})
    b.comp(bid, "Q", chosen, chosen, {"1": n_g, library.pin_number(chosen, "D"): n_d,
                                      library.pin_number(chosen, "S"): "GND"})
    b.resistor(bid, "R_G", 100.0, n_c, n_g, "게이트 직렬 저항")
    b.resistor(bid, "R_PD", 100e3, n_g, "GND", "게이트 풀다운 (MCU 리셋 중 OFF 보장)")
    b.comp(bid, "J_CTRL", "Conn_01x02", "CTRL", {"1": n_c, "2": "GND"})
    diode = None
    if p["inductive"]:
        diode = "SS34" if i <= library.get("SS34").params["if_a"] else "SS54"
        b.comp(bid, "D_FLY", diode, diode, {"1": rail, "2": n_d})
    b.load(rail, i)
    b.blocks[bid]["design"] = {"mosfet": chosen, "mosfet_reason": reason,
                               "load_connector": conn, "flyback": diode,
                               "p_cond_w": round(i * i * library.get(chosen).params["rds_on_ohm"], 4)}


def _solve_divider(bid, p):
    """최악 조건을 만족하는 분압 저항 쌍 탐색 (level_shift_divider, logic_module 공용)."""
    vs, tol = p["src_high_v"], p["src_tol"]
    v_lo, v_hi = vs * (1 - tol), vs * (1 + tol)
    vih, vmx = p["sink_vih_min_v"], p["sink_vmax_v"]
    if vmx <= vih:
        raise SynthesisError(f"{bid}: 받는 쪽 최대 전압 {vmx}V가 High 인식 전압 {vih}V 이하 — 사양 오류")
    if v_hi <= vmx:
        raise SynthesisError(f"{bid}: 최악 출력 {v_hi:.2f}V가 받는 쪽 최대 {vmx}V 이하 — 레벨 변환 불필요, 직결")
    if v_lo <= vih:
        raise SynthesisError(f"{bid}: 최소 출력 {v_lo:.2f}V가 High 인식 {vih}V 이하 — 분압기로는 올릴 수 없음, "
                             "능동 레벨 변환기가 필요(미지원)")
    r_tol = library.get("R").params["tolerance"]
    values = [m * 10 ** e for e in (3, 4, 5) for m in E24] + [1e6]
    target = (vih + vmx) / 2
    best = None
    for rt in values:
        for rb in values:
            lo, hi = divider_window(v_lo, v_hi, rt, rb, r_tol)
            if hi > vmx or lo < vih:
                continue
            if v_hi / (rt + rb) > p["src_iout_max_a"]:
                continue
            if rc_rise_time(rt, rb, p["sink_cin_f"]) > 0.1 / p["signal_max_hz"]:
                continue
            key = (round(abs((lo + hi) / 2 - target), 3), rt + rb)
            if best is None or key < best[0]:
                best = (key, rt, rb, lo, hi)
    if best is None:
        raise SynthesisError(f"{bid}: 최악 조건(전압·저항 허용오차·구동 전류·속도)을 모두 만족하는 분압 저항 조합 없음 — "
                             "능동 레벨 변환기가 필요(미지원)")
    return best[1], best[2], best[3], best[4]


def _level_shift_divider(b: Builder, bid, p, rails):
    """신호 전압이 받는 쪽 입력 한계보다 높을 때 저항 분압으로 낮춘다 (단방향·저속 신호 전용).

    입력은 수치 사양뿐이다 (부품 이름·벤더 없음). 조건을 만족하는 조합이 없으면 합성 실패.
    """
    rt, rb, lo, hi = _solve_divider(bid, p)
    vs = p["src_high_v"]
    n_in = b.net(f"N_{bid}_IN", "signal", vs, False, owner=bid)
    n_out = b.net(f"N_{bid}_OUT", "signal", round(vs * rb / (rt + rb), 4), False, owner=bid)
    b.comp(bid, "J_SRC", "Conn_01x02", "SRC", {"1": n_in, "2": "GND"})
    b.resistor(bid, "R_TOP", rt, n_in, n_out, "분압 위쪽")
    b.resistor(bid, "R_BOT", rb, n_out, "GND", "분압 아래쪽")
    b.comp(bid, "J_SNK", "Conn_01x02", "SNK", {"1": n_out, "2": "GND"})
    b.blocks[bid]["design"] = {
        "r_top_ohm": rt, "r_bot_ohm": rb, "vout_worst_min_v": round(lo, 4),
        "vout_worst_max_v": round(hi, 4),
        "why": "최악 조건에서 [High 인식 전압, 받는 쪽 최대 전압] 창 안에 들고 창 중앙에 가장 가까운 E24 쌍. "
               "단방향·저속 신호 전용"}


def _divider_params(e):
    """logic_module의 out 핀 사양 -> 분압 탐색 입력."""
    return {"src_high_v": e["voh_v"], "src_tol": e["voh_tol"], "src_iout_max_a": e["iout_max_a"],
            "sink_vih_min_v": e["sink_vih_min_v"], "sink_vmax_v": e["sink_vmax_v"],
            "signal_max_hz": e["signal_max_hz"], "sink_cin_f": e["sink_cin_f"]}


def _logic_module(b: Builder, bid, p, rails):
    """핀 목록으로 기술된 모듈 하나를 연결한다 (핀 개수·이름·부품 종류에 의존하지 않음).

    vcc: 레일에 연결, 전압 범위 확인, 레일마다 100nF 디커플링 / gnd: GND / nc: 사유와 함께 NC
    in : 호스트가 구동 — 호스트 High 출력 범위가 모듈 입력 사양 안이어야 함(직결)
    out: 모듈이 구동 — 받는 쪽 한계를 넘으면 분압 레벨 변환(최악 조건 탐색), 불가능하면 합성 실패
    호스트 쪽 커넥터는 신호마다 1핀 + 끝에 GND.
    """
    pins = sorted(p["pins"], key=lambda e: int(e["number"]))
    mod_nets, nc, loads, rail_order = {}, {}, {}, []
    signals = []
    for e in pins:
        num, role = e["number"], e["role"]
        if role == "gnd":
            mod_nets[num] = "GND"
        elif role == "nc":
            nc[num] = e["reason"]
        elif role == "vcc":
            if e["rail"] not in rails:
                raise SynthesisError(f"{bid}: 핀 {num}의 레일 {e['rail']!r}이 정의되지 않음")
            if e["min_v"] >= e["max_v"]:
                raise SynthesisError(f"{bid}: 핀 {num} 전원 범위 오류")
            net = rails[e["rail"]]
            v = b.voltage(net)
            if not (e["min_v"] <= v <= e["max_v"]):
                raise SynthesisError(f"{bid}: 핀 {num} 레일 {v}V가 모듈 전원 범위 {e['min_v']}~{e['max_v']}V 밖")
            mod_nets[num] = net
            loads[net] = loads.get(net, 0.0) + e["current_a"]
            if net not in rail_order:
                rail_order.append(net)
        else:
            signals.append(e)
    host_pins, extra = [], []
    for k, e in enumerate(signals, 1):
        num = e["number"]
        if e["role"] == "in":
            if e["host_voh_max_v"] > e["vmax_v"]:
                raise SynthesisError(f"{bid}: 핀 {num} 호스트 출력 최대 {e['host_voh_max_v']}V가 모듈 입력 한계 {e['vmax_v']}V 초과")
            if e["host_voh_min_v"] < e["vih_min_v"]:
                raise SynthesisError(f"{bid}: 핀 {num} 호스트 출력 최소 {e['host_voh_min_v']}V가 모듈 High 인식 "
                                     f"{e['vih_min_v']}V 미만 — 직결 불가, 레벨 업 변환 필요(미지원)")
            n = b.net(f"N_{bid}_S{k}", "signal", e["host_voh_max_v"], False, owner=bid)
            mod_nets[num] = n
            host_pins.append(n)
        else:
            rt, rb, lo, hi = _solve_divider(f"{bid} 핀 {num}", _divider_params(e))
            vs = e["voh_v"]
            n_mod = b.net(f"N_{bid}_S{k}_MOD", "signal", vs, False, owner=bid)
            n_host = b.net(f"N_{bid}_S{k}_HOST", "signal", round(vs * rb / (rt + rb), 4), False, owner=bid)
            mod_nets[num] = n_mod
            host_pins.append(n_host)
            extra.append((k, rt, rb, n_mod, n_host, lo, hi))
    n_total = len(pins)
    b.comp(bid, "J_MOD", f"Conn_01x{n_total:02d}", "MODULE",
           {num: net for num, net in mod_nets.items()}, no_connect=nc)
    if host_pins:
        n_h = len(host_pins) + 1
        hp = {str(i + 1): net for i, net in enumerate(host_pins)}
        hp[str(n_h)] = "GND"
        b.comp(bid, "J_HOST", f"Conn_01x{n_h:02d}", "HOST", hp)
    design = {"dividers": {}}
    for k, rt, rb, n_mod, n_host, lo, hi in extra:
        b.resistor(bid, f"R_TOP_{k}", rt, n_mod, n_host, f"신호 {k} 분압 위쪽")
        b.resistor(bid, f"R_BOT_{k}", rb, n_host, "GND", f"신호 {k} 분압 아래쪽")
        design["dividers"][f"S{k}"] = {"r_top_ohm": rt, "r_bot_ohm": rb, "vout_worst_min_v": round(lo, 4),
                                       "vout_worst_max_v": round(hi, 4)}
    for i, net in enumerate(rail_order, 1):
        b.capacitor(bid, f"C_DEC_{i}", 100e-9, net, "GND", b.voltage(net))
        b.load(net, loads[net])
    design["why"] = ("핀 역할별로 연결: vcc 범위 확인·디커플링, in 직결 전압 호환 확인, out 최악 조건 분압 탐색. "
                     "100nF 디커플링은 설계 관례(데이터시트 요구 아님)")
    b.blocks[bid]["design"] = design


def _power_input(b: Builder, pi, in_net):
    v = pi["voltage_v"]
    i = b.nets[in_net]["current_a"]
    blk = "P0"
    b.blocks[blk] = {"type": "power_input", "params": dict(pi), "design": {}}
    if pi["connector"] == "usb_c":
        cc1, cc2 = b.net("N_P0_CC1"), b.net("N_P0_CC2")
        b.comp(blk, "J_IN", "USB_C_Power_6P", "USB_C",
               {"A9": in_net, "B9": in_net, "A12": "GND", "B12": "GND",
                "SH": "GND", "A5": cc1, "B5": cc2})
        b.resistor(blk, "R_CC1", 5100.0, cc1, "GND", "USB-C 싱크 Rd")
        b.resistor(blk, "R_CC2", 5100.0, cc2, "GND", "USB-C 싱크 Rd")
        conn = "USB_C_Power_6P"
    else:
        conn = "Conn_01x02" if i <= library.get("Conn_01x02").params["current_max_a"] else "TB_1x02"
        b.comp(blk, "J_IN", conn, "PWR_IN", {"1": in_net, "2": "GND"})
    b.capacitor(blk, "C_BULK", 10e-6, in_net, "GND", v)
    b.pwr_flag(in_net)
    b.pwr_flag("GND")
    b.blocks[blk]["design"] = {"connector": conn, "i_total_a": round(i, 6)}


_RULES = {"ldo": _ldo, "led_indicator": _led_indicator,
          "blinker_555": _blinker_555, "lowside_switch": _lowside_switch,
          "level_shift_divider": _level_shift_divider,
          "logic_module": _logic_module}


def synthesize(intent: dict, project: str) -> dict:
    errs = validate_intent(intent)
    if errs:
        raise SynthesisError("IntentSpec 무효: " + "; ".join(errs))
    if blocking_questions(intent):
        raise SynthesisError("BLOCKING 질문이 남아 있어 합성할 수 없음")
    b = Builder(project)
    pi = intent["power_input"]
    b.net("GND", "ground", 0.0, True, owner="P0")
    in_net = b.net(rail_name(pi["voltage_v"]), "power", float(pi["voltage_v"]), True, owner="P0")
    rails = {"INPUT": in_net}
    for blk in intent["blocks"]:
        b.blocks[blk["id"]] = {"type": blk["type"], "params": copy.deepcopy(blk["params"]),
                               "design": {}}
        _RULES[blk["type"]](b, blk["id"], blk["params"], rails)
    n_before = len(b.order)
    _power_input(b, pi, in_net)
    order = b.order[n_before:] + b.order[:n_before]     # 전원 입력을 맨 앞에
    counters: dict = {}
    comps = {}
    for cid in order:
        c = b.components[cid]
        pre = library.get(c["part"]).ref_prefix
        counters[pre] = counters.get(pre, 0) + 1
        c["ref"] = f"{pre}{counters[pre]:02d}" if pre.startswith("#") else f"{pre}{counters[pre]}"
        comps[cid] = c
    for n in b.nets.values():
        n.pop("owner", None)
    return {"schema": IR_SCHEMA,
            "project": {"name": project},
            "intent_sha256": sha256_of(intent),
            "assumptions": copy.deepcopy(intent["assumptions"]),
            "nets": b.nets, "components": comps, "blocks": b.blocks}
