"""Design IR 검사: 구조(G1), 의미·ERC(G2), 전기 규칙(G3).

모든 검사는 finding 목록을 반환한다.
finding = {"code", "severity": ERROR|WARN|INFO, "message", "where"}
ERROR가 하나라도 있으면 해당 Gate는 FAIL이다.
"""
from __future__ import annotations

from . import library
from .units import divider_window, rail_name, rc_rise_time

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"


def F(code, sev, msg, where=""):
    return {"code": code, "severity": sev, "message": msg, "where": where}


# ------------------------------------------------------------------ G1 구조

_TOP = {"schema", "project", "intent_sha256", "assumptions", "nets", "components", "blocks"}
_COMP = {"id", "ref", "part", "value", "footprint", "block", "role", "params", "pins", "no_connect"}
_NET = {"kind", "voltage_v", "external_supply", "current_a"}


def structural(ir) -> list:
    out = []
    if not isinstance(ir, dict):
        return [F("IR_TYPE", ERROR, "IR은 object여야 함")]
    if set(ir) != _TOP:
        out.append(F("IR_TOP_KEYS", ERROR, f"최상위 키 불일치: +{sorted(set(ir) - _TOP)} -{sorted(_TOP - set(ir))}"))
        return out
    if ir["schema"] != "eda.ir/1":
        out.append(F("IR_SCHEMA", ERROR, "schema는 eda.ir/1"))
    for name, n in ir["nets"].items():
        if not isinstance(n, dict) or set(n) != _NET:
            out.append(F("IR_NET_KEYS", ERROR, "넷 키 불일치", f"/nets/{name}"))
            continue
        if n["kind"] not in ("power", "ground", "signal"):
            out.append(F("IR_NET_KIND", ERROR, f"kind={n['kind']}", f"/nets/{name}"))
    for cid, c in ir["components"].items():
        if not isinstance(c, dict) or set(c) != _COMP:
            out.append(F("IR_COMP_KEYS", ERROR, "컴포넌트 키 불일치", f"/components/{cid}"))
            continue
        if c["id"] != cid:
            out.append(F("IR_ID_MISMATCH", ERROR, f"map 키 {cid} ≠ id {c['id']}", f"/components/{cid}"))
        if not isinstance(c["pins"], dict) or not isinstance(c["no_connect"], dict):
            out.append(F("IR_PINS_TYPE", ERROR, "pins/no_connect는 object", f"/components/{cid}"))
    return out


# ------------------------------------------------------------------ G2 의미 + ERC

_DRIVERS_FOR_INPUT = {"output", "bidirectional", "tri_state", "passive", "power_out",
                      "open_collector", "open_emitter", "unspecified"}


def net_members(ir) -> dict:
    """넷 이름 -> [(ref, pin_number, pin_type)]"""
    m = {n: [] for n in ir["nets"]}
    for c in ir["components"].values():
        try:
            part = library.get(c["part"])
        except KeyError:
            continue
        for num, net in c["pins"].items():
            try:
                et = part.pin(num).etype
            except KeyError:
                continue
            m.setdefault(net, []).append((c["ref"], num, et))
    return m


def semantic(ir) -> list:
    out = []
    refs = {}
    for cid, c in ir["components"].items():
        w = f"/components/{cid}"
        try:
            part = library.get(c["part"])
        except KeyError:
            out.append(F("PART_UNKNOWN", ERROR, f"라이브러리에 없는 부품 {c['part']}", w))
            continue
        ref = c["ref"]
        if not ref or not ref.startswith(part.ref_prefix) or not ref[len(part.ref_prefix):].isdigit():
            out.append(F("REF_FORMAT", ERROR, f"refdes {ref!r}가 접두사 {part.ref_prefix}+숫자가 아님", w))
        if ref in refs:
            out.append(F("REF_DUPLICATE", ERROR, f"refdes {ref} 중복 ({refs[ref]}, {cid})", w))
        refs[ref] = cid
        if not part.power_symbol and not c["footprint"]:
            out.append(F("FOOTPRINT_MISSING", ERROR, f"{ref} 풋프린트 없음", w))
        if c["part"] == "R" and not c["params"].get("r_ohm"):
            out.append(F("VALUE_MISSING", ERROR, f"{ref} 저항값 없음", w))
        if c["part"] == "C" and not c["params"].get("c_f"):
            out.append(F("VALUE_MISSING", ERROR, f"{ref} 용량 없음", w))
        valid = set(part.pin_numbers)
        for num in list(c["pins"]) + list(c["no_connect"]):
            if num not in valid:
                out.append(F("PIN_UNKNOWN", ERROR, f"{ref}에 핀 {num} 없음 (identity는 핀 번호)", w))
        for num in valid:
            inp, inn = num in c["pins"], num in c["no_connect"]
            if inp and inn:
                out.append(F("PIN_BOTH_NET_AND_NC", ERROR, f"{ref}.{num}이 넷과 NC에 동시 지정", w))
            elif not inp and not inn:
                out.append(F("PIN_UNASSIGNED", ERROR, f"{ref}.{num} 미연결이고 NC 표시도 없음", w))
        for num, reason in c["no_connect"].items():
            if not reason:
                out.append(F("NC_NO_REASON", ERROR, f"{ref}.{num} NC 사유 없음", w))
        for num, net in c["pins"].items():
            if net not in ir["nets"]:
                out.append(F("NET_UNDECLARED", ERROR, f"{ref}.{num} -> 선언 안 된 넷 {net}", w))

    members = net_members(ir)
    flagged = {c["pins"]["1"] for c in ir["components"].values() if c["part"] == "PWR_FLAG"}
    for name, n in ir["nets"].items():
        w = f"/nets/{name}"
        mem = members.get(name, [])
        types = [t for _, _, t in mem]
        if not mem:
            out.append(F("NET_UNUSED", WARN, f"넷 {name}에 연결된 핀 없음", w))
            continue
        if len(mem) < 2:
            out.append(F("NET_SINGLE_PIN", ERROR, f"넷 {name}에 핀이 1개뿐 (끊긴 연결)", w))
        if n["kind"] in ("power", "ground") and n["voltage_v"] is None:
            out.append(F("POWER_NET_NO_VOLTAGE", ERROR, f"전원 넷 {name} 전압 미정", w))
        if n["kind"] == "power" and n["voltage_v"] is not None and name != rail_name(n["voltage_v"]):
            out.append(F("POWER_NET_NAME", ERROR, f"전원 넷 이름 {name}이 전압 {n['voltage_v']}V와 불일치", w))
        if n["external_supply"] and name not in flagged:
            out.append(F("ERC_EXTERNAL_NO_FLAG", ERROR, f"외부 전원 넷 {name}에 PWR_FLAG 없음", w))
        n_pout, n_out = types.count("power_out"), types.count("output")
        if n_pout > 1:
            out.append(F("ERC_POWER_OUT_CONFLICT", ERROR, f"넷 {name}에 power_out {n_pout}개 (전원 단락)", w))
        if n_out > 1 or (n_out and n_pout):
            out.append(F("ERC_OUTPUT_CONFLICT", ERROR, f"넷 {name}에 출력 충돌", w))
        if "power_in" in types and n_pout == 0:
            out.append(F("ERC_POWER_IN_UNDRIVEN", ERROR, f"넷 {name}의 power_in 핀을 구동하는 전원이 없음", w))
        if "input" in types and not any(t in _DRIVERS_FOR_INPUT for t in types):
            out.append(F("ERC_INPUT_UNDRIVEN", ERROR, f"넷 {name}의 입력 핀이 구동되지 않음", w))
    return out


# ------------------------------------------------------------------ G3 전기 규칙

def _comps(ir, block=None, part=None, role=None):
    for c in ir["components"].values():
        if block and c["block"] != block:
            continue
        if part and c["part"] != part:
            continue
        if role and c["role"] != role:
            continue
        yield c


def _one(ir, block, role):
    for c in _comps(ir, block=block, role=role):
        return c
    return None


def electrical(ir) -> list:
    out = []
    nets = ir["nets"]

    def V(net):
        return nets[net]["voltage_v"]

    for bid, blk in ir["blocks"].items():
        t, p, d, w = blk["type"], blk["params"], blk["design"], f"/blocks/{bid}"
        if t == "ldo":
            u = _one(ir, bid, "U")
            pr = u["params"]
            vin, vout, iout = V(u["pins"]["3"]), pr["vout_v"], p["iout_max_a"]
            if vin - vout < pr["dropout_v"]:
                out.append(F("LDO_DROPOUT", ERROR,
                             f"{u['ref']}: Vin-Vout={vin - vout:.2f}V < 드롭아웃 {pr['dropout_v']}V", w))
            if vin > pr["vin_max_v"]:
                out.append(F("LDO_VIN_MAX", ERROR, f"{u['ref']}: Vin {vin}V > 최대 {pr['vin_max_v']}V", w))
            pd = (vin - vout) * iout
            pd_max = (pr["tj_max_c"] - 40.0) / pr["theta_ja_c_per_w"]
            if pd > pd_max:
                out.append(F("LDO_THERMAL", ERROR,
                             f"{u['ref']}: 손실 {pd:.2f}W > 허용 {pd_max:.2f}W (Ta=40°C, θja={pr['theta_ja_c_per_w']}) "
                             "— 출력 전류를 줄이거나 벅 컨버터가 필요", w))
            if iout > pr["iout_max_a"]:
                out.append(F("LDO_IOUT", ERROR, f"{u['ref']}: 요구 {iout}A > 정격 {pr['iout_max_a']}A", w))
            downstream = nets[u["pins"]["2"]]["current_a"]
            if downstream > iout + 1e-12:
                out.append(F("LDO_RAIL_OVERLOAD", ERROR,
                             f"{u['ref']}: 하위 부하 {downstream * 1e3:.1f}mA > 설계 전류 {iout * 1e3:.0f}mA", w))
            cin, cout = _one(ir, bid, "C_IN"), _one(ir, bid, "C_OUT")
            if not cin or cin["params"]["c_f"] < pr["cin_min_f"]:
                out.append(F("LDO_CIN", ERROR, f"{u['ref']}: 입력 커패시터 부족", w))
            if not cout or cout["params"]["c_f"] < pr["cout_min_f"]:
                out.append(F("LDO_COUT", ERROR, f"{u['ref']}: 출력 커패시터 부족 (안정도)", w))
        elif t in ("led_indicator", "blinker_555"):
            # 합성기가 기록한 design 값을 믿지 않고 IR의 부품 값에서 다시 계산한다 (자기 채점 방지)
            led, r = _one(ir, bid, "LED"), _one(ir, bid, "R_LED")
            if t == "led_indicator":
                v_drive = V(r["pins"]["1"])
                target = p["current_a"]
            else:
                v_drive = V(_one(ir, bid, "U")["pins"]["8"]) - 1.7     # 바이폴라 555 VOH ≈ Vcc-1.7V
                target = p["led_current_a"]
            head = v_drive - led["params"]["vf_v"]
            i = max(head, 0.0) / r["params"]["r_ohm"]
            if i > target * 1.05:
                out.append(F("LED_CURRENT_TARGET", ERROR,
                             f"{led['ref']}: 실제 {i * 1e3:.2f}mA > 의도 {target * 1e3:.2f}mA", w))
            if head < 0.5:
                out.append(F("LED_HEADROOM", ERROR,
                             f"{led['ref']}: 전류제한 여유 {head:.2f}V < 0.5V — Vf 편차로 밝기/전류가 크게 변함", w))
            if i > led["params"]["if_max_a"]:
                out.append(F("LED_OVERCURRENT", ERROR, f"{led['ref']}: {i * 1e3:.1f}mA > 정격", w))
            pr_w = i * i * r["params"]["r_ohm"]
            if pr_w > 0.5 * r["params"]["power_w"]:
                out.append(F("R_POWER", ERROR, f"{r['ref']}: {pr_w * 1e3:.1f}mW > 정격의 50%", w))
            if t == "blinker_555":
                u = _one(ir, bid, "U")
                vcc = V(u["pins"]["8"])
                if not (u["params"]["vcc_min_v"] <= vcc <= u["params"]["vcc_max_v"]):
                    out.append(F("NE555_VCC", ERROR,
                                 f"{u['ref']}: Vcc {vcc}V가 {u['params']['vcc_min_v']}~{u['params']['vcc_max_v']}V 밖", w))
                ra, rb = _one(ir, bid, "R_A")["params"]["r_ohm"], _one(ir, bid, "R_B")["params"]["r_ohm"]
                ct = _one(ir, bid, "C_T")["params"]["c_f"]
                f_act = 1.44 / ((ra + 2 * rb) * ct)
                err = abs(f_act - p["freq_hz"]) / p["freq_hz"]
                if err > 0.10:
                    out.append(F("NE555_FREQ", ERROR,
                                 f"{u['ref']}: 실제 {f_act:.3g}Hz, 목표 대비 오차 {err:.1%} > 10%", w))
                if i > u["params"]["iout_max_a"] * 0.5:
                    out.append(F("NE555_IOUT", ERROR, f"{u['ref']}: 출력 전류 과다", w))
                if not _one(ir, bid, "C_DEC"):
                    out.append(F("DECOUPLING_MISSING", ERROR, f"{u['ref']}: Vcc 디커플링 없음", w))
        elif t == "lowside_switch":
            q = _one(ir, bid, "Q")
            pr = q["params"]
            v, i, vc = V(_one(ir, bid, "J_LOAD")["pins"]["1"]), p["load_current_a"], p["control_v"]
            if pr["vds_v"] < 1.5 * v:
                out.append(F("FET_VDS", ERROR, f"{q['ref']}: Vds {pr['vds_v']}V < 1.5×{v}V", w))
            if i > 0.5 * pr["id_a"]:
                out.append(F("FET_ID", ERROR, f"{q['ref']}: {i}A > Id 정격의 50%", w))
            if vc < pr["rds_spec_vgs_v"]:
                out.append(F("FET_VGS_DRIVE", ERROR,
                             f"{q['ref']}: 제어 {vc}V < Rds(on) 규격 Vgs {pr['rds_spec_vgs_v']}V — 완전 도통 보장 안 됨 "
                             "(게이트 드라이버 또는 다른 MOSFET 필요)", w))
            pc = i * i * pr["rds_on_ohm"]
            if pc > pr["pd_max_w"]:
                out.append(F("FET_THERMAL", ERROR, f"{q['ref']}: 도통손실 {pc:.2f}W > {pr['pd_max_w']}W", w))
            if not _one(ir, bid, "R_PD"):
                out.append(F("FET_GATE_PULLDOWN", ERROR, f"{q['ref']}: 게이트 풀다운 없음", w))
            dfly = _one(ir, bid, "D_FLY")
            if p["inductive"]:
                if not dfly:
                    out.append(F("FLYBACK_MISSING", ERROR, f"{q['ref']}: 유도성 부하인데 플라이백 다이오드 없음", w))
                else:
                    if dfly["params"]["if_a"] < i:
                        out.append(F("FLYBACK_IF", ERROR, f"{dfly['ref']}: If {dfly['params']['if_a']}A < {i}A", w))
                    if dfly["params"]["vr_v"] < 1.25 * v:
                        out.append(F("FLYBACK_VR", ERROR, f"{dfly['ref']}: Vr 부족", w))
                    if dfly["pins"].get("1") != _one(ir, bid, "J_LOAD")["pins"]["1"] or \
                            dfly["pins"].get("2") != q["pins"][library.pin_number(q["part"], "D")]:
                        out.append(F("FLYBACK_POLARITY", ERROR, f"{dfly['ref']}: 캐소드=레일, 애노드=드레인이어야 함", w))
        elif t == "level_shift_divider":
            # design 값이 아니라 IR의 저항값·넷 연결에서 최악 조건을 다시 계산한다
            rt, rb = _one(ir, bid, "R_TOP"), _one(ir, bid, "R_BOT")
            js, jk = _one(ir, bid, "J_SRC"), _one(ir, bid, "J_SNK")
            if not (rt and rb and js and jk):
                out.append(F("LEVEL_TOPOLOGY", ERROR, "분압기 구성 부품 누락", w))
                continue
            n_in, n_out = js["pins"]["1"], jk["pins"]["1"]
            if not (rt["pins"]["1"] == n_in and rt["pins"]["2"] == n_out and
                    rb["pins"]["1"] == n_out and rb["pins"]["2"] == "GND" and n_in != n_out):
                out.append(F("LEVEL_TOPOLOGY", ERROR, "분압 연결이 입력-R_TOP-출력-R_BOT-GND 구조가 아님", w))
                continue
            out.extend(_level_findings(p, V(n_in), rt, rb, w))
        elif t == "logic_module":
            out.extend(_logic_findings(ir, bid, p, w, V))
        elif t == "power_input":
            j = _one(ir, bid, "J_IN")
            i_tot = nets[j["pins"].get("A9") or j["pins"]["1"]]["current_a"]
            if i_tot > j["params"]["current_max_a"]:
                out.append(F("CONNECTOR_CURRENT", ERROR, f"{j['ref']}: {i_tot}A > 정격 {j['params']['current_max_a']}A", w))
            if j["part"] == "USB_C_Power_6P":
                if i_tot > j["params"]["default_power_a"]:
                    out.append(F("USB_DEFAULT_POWER", ERROR,
                                 f"{j['ref']}: 총 {i_tot * 1e3:.0f}mA > USB 기본 전력 500mA "
                                 "(Rd만 있는 싱크는 PD/Type-C 전류 광고 확인 없이 초과 사용 불가)", w))
                for cc in ("A5", "B5"):
                    rd = [c for c in _comps(ir, part="R") if c["pins"].get("1") == j["pins"][cc]
                          and c["pins"].get("2") == "GND"]
                    if not rd or abs(rd[0]["params"]["r_ohm"] - 5100) > 5100 * 0.1:
                        out.append(F("USB_CC_RD", ERROR, f"{j['ref']}.{cc}: 5.1k Rd 풀다운 필요", w))

    for c in ir["components"].values():
        w = f"/components/{c['id']}"
        if c["part"] == "C":
            nv = max(V(n) or 0 for n in c["pins"].values())
            if c["params"]["voltage_rating_v"] < 1.5 * nv:
                out.append(F("CAP_VOLTAGE", ERROR, f"{c['ref']}: 정격 {c['params']['voltage_rating_v']}V < 1.5×{nv}V", w))
        if c["part"] in ("Conn_01x02", "TB_1x02") and c["role"] == "J_LOAD":
            bi = ir["blocks"][c["block"]]["params"]["load_current_a"]
            if bi > c["params"]["current_max_a"]:
                out.append(F("CONNECTOR_CURRENT", ERROR, f"{c['ref']}: {bi}A > 정격", w))
        part = library.get(c["part"])
        if part.data_status == "UNVERIFIED_SEED":
            out.append(F("PART_DATA_UNVERIFIED", WARN,
                         f"{c['ref']} ({c['part']}) 파라미터가 시드값 — 구매 부품 데이터시트로 검증 필요", w))
    for a in ir["assumptions"]:
        out.append(F("ASSUMPTION", INFO, f"{a['field']}={a['value']}: {a['reason']}"))
    return out


def _level_findings(p, vs, rt, rb, w):
    """분압기 전기 판정 (level_shift_divider, logic_module 공용). 저항값·넷 전압에서 재계산."""
    out = []
    tol = p["src_tol"]
    r1, r2, r_tol = rt["params"]["r_ohm"], rb["params"]["r_ohm"], max(rt["params"]["tolerance"], rb["params"]["tolerance"])
    lo, hi = divider_window(vs * (1 - tol), vs * (1 + tol), r1, r2, r_tol)
    if hi > p["sink_vmax_v"]:
        out.append(F("LEVEL_SINK_VMAX", ERROR,
                     f"최악 출력 {hi:.2f}V > 받는 쪽 최대 {p['sink_vmax_v']}V (받는 쪽 손상 위험)", w))
    if lo < p["sink_vih_min_v"]:
        out.append(F("LEVEL_SINK_VIH", ERROR,
                     f"최악 출력 {lo:.2f}V < High 인식 전압 {p['sink_vih_min_v']}V (High를 못 읽을 수 있음)", w))
    i_src = vs * (1 + tol) / (r1 + r2)
    if i_src > p["src_iout_max_a"]:
        out.append(F("LEVEL_SRC_CURRENT", ERROR,
                     f"보내는 쪽 부하 전류 {i_src * 1e3:.2f}mA > 한도 {p['src_iout_max_a'] * 1e3:.2f}mA", w))
    tr = rc_rise_time(r1, r2, p["sink_cin_f"])
    if tr > 0.1 / p["signal_max_hz"]:
        out.append(F("LEVEL_RISE_TIME", ERROR,
                     f"상승 시간 {tr * 1e9:.0f}ns > 신호 주기의 10% ({0.1 / p['signal_max_hz'] * 1e9:.0f}ns) "
                     "— 이 신호 속도에는 분압기가 맞지 않음", w))
    return out


def _logic_findings(ir, bid, p, w, V):
    """logic_module 판정: 핀 역할별 연결·전압을 IR의 연결과 부품 값에서 다시 계산한다."""
    out = []
    j, jh = _one(ir, bid, "J_MOD"), _one(ir, bid, "J_HOST")
    pins = sorted(p["pins"], key=lambda e: int(e["number"]))
    if not j or len(j["pins"]) + len(j["no_connect"]) != len(pins):
        return [F("MODULE_TOPOLOGY", ERROR, "모듈 커넥터 핀 수가 핀 목록과 다름", w)]
    signals = [e for e in pins if e["role"] in ("in", "out")]
    host_used, host_nets = [], []
    if signals:
        if not jh or len(jh["pins"]) != len(signals) + 1 or jh["pins"].get(str(len(signals) + 1)) != "GND":
            return [F("MODULE_TOPOLOGY", ERROR, "호스트 커넥터가 신호 핀 + 마지막 GND 구조가 아님", w)]
    elif jh:
        return [F("MODULE_TOPOLOGY", ERROR, "신호가 없는데 호스트 커넥터가 있음", w)]
    vcc_nets = []
    for k, e in enumerate(signals, 1):
        host_net = jh["pins"][str(k)]
        host_nets.append(host_net)
        num = e["number"]
        mod_net = j["pins"].get(num)
        if e["role"] == "in":
            if mod_net != host_net:
                out.append(F("MODULE_TOPOLOGY", ERROR, f"입력 핀 {num}이 호스트 신호 {k}에 직결되어 있지 않음", w))
                continue
            if e["host_voh_max_v"] > e["vmax_v"]:
                out.append(F("MODULE_IN_VMAX", ERROR,
                             f"핀 {num}: 호스트 출력 최대 {e['host_voh_max_v']}V > 모듈 입력 한계 {e['vmax_v']}V", w))
            if e["host_voh_min_v"] < e["vih_min_v"]:
                out.append(F("MODULE_IN_VIH", ERROR,
                             f"핀 {num}: 호스트 출력 최소 {e['host_voh_min_v']}V < 모듈 High 인식 {e['vih_min_v']}V", w))
        else:
            rt, rb = _one(ir, bid, f"R_TOP_{k}"), _one(ir, bid, f"R_BOT_{k}")
            if not (rt and rb and mod_net and rt["pins"]["1"] == mod_net and rt["pins"]["2"] == host_net
                    and rb["pins"]["1"] == host_net and rb["pins"]["2"] == "GND" and mod_net != host_net):
                out.append(F("MODULE_TOPOLOGY", ERROR, f"출력 핀 {num}의 분압 연결이 구조에 맞지 않음", w))
                continue
            pp = {"src_tol": e["voh_tol"], "src_iout_max_a": e["iout_max_a"],
                  "sink_vih_min_v": e["sink_vih_min_v"], "sink_vmax_v": e["sink_vmax_v"],
                  "signal_max_hz": e["signal_max_hz"], "sink_cin_f": e["sink_cin_f"]}
            out.extend(_level_findings(pp, V(mod_net), rt, rb, f"{w} (핀 {num})"))
    if len(set(host_nets)) != len(host_nets):
        out.append(F("MODULE_TOPOLOGY", ERROR, "서로 다른 호스트 신호가 같은 넷을 씀", w))
    for e in pins:
        num = e["number"]
        if e["role"] == "gnd" and j["pins"].get(num) != "GND":
            out.append(F("MODULE_TOPOLOGY", ERROR, f"접지 핀 {num}이 GND에 연결되지 않음", w))
        elif e["role"] == "nc" and num not in j["no_connect"]:
            out.append(F("MODULE_TOPOLOGY", ERROR, f"핀 {num}은 NC여야 함", w))
        elif e["role"] == "vcc":
            net = j["pins"].get(num)
            if net is None:
                out.append(F("MODULE_TOPOLOGY", ERROR, f"전원 핀 {num}이 연결되지 않음", w))
                continue
            v = V(net)
            if v is None or not (e["min_v"] <= v <= e["max_v"]):
                out.append(F("MODULE_SUPPLY_RANGE", ERROR,
                             f"핀 {num}: 전원 {v}V가 허용 {e['min_v']}~{e['max_v']}V 밖", w))
            if net not in vcc_nets:
                vcc_nets.append(net)
    for net in vcc_nets:
        if not any(c["pins"].get("1") == net and c["pins"].get("2") == "GND" for c in _comps(ir, block=bid, part="C")):
            out.append(F("DECOUPLING_MISSING", ERROR, f"전원 {net}에 디커플링 커패시터 없음", w))
    if not p["pin_order_verified"]:
        out.append(F("MODULE_PIN_ORDER_UNVERIFIED", WARN,
                     "모듈 핀 순서가 실제 기판에서 확인되지 않음 — 잘못되면 전원 핀 역접속 위험, 제작 전 확인 필요", w))
    return out


def has_error(findings) -> bool:
    return any(f["severity"] == ERROR for f in findings)
