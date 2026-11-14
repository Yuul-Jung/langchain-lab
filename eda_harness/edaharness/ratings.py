"""승인된 부품 정보(신호 사양) -> 레벨 변환 블록 입력.

부품 이름이 아니라 신호 핀의 수치 사양만 읽는다. 각 수치는 근거(basis)와 함께 적혀 있어야 한다.
  basis = datasheet(데이터시트에 적힌 값) | derived(다른 값에서 유도) | assumed(가정)
수치가 없거나 근거가 없으면 만들지 않고 RatingsError로 거절한다 (fail-closed).
datasheet가 아닌 값은 모두 assumptions에 사유와 함께 남는다.
"""
from __future__ import annotations

BASES = ("datasheet", "derived", "assumed")
SRC_KEYS = {"voh_v": "High 출력 전압(V)", "voh_tol": "High 출력 전압 오차(비율)",
            "iout_max_a": "출력 구동 전류 한도(A)"}
SINK_KEYS = {"vih_min_v": "High 인식 최소 전압(V)", "vmax_v": "견디는 최대 입력 전압(V)",
             "cin_f": "입력 용량(F)"}


class RatingsError(Exception):
    pass


def _get(part, pin, keys, role):
    sig = (part.get("signals") or {}).get(pin)
    if not isinstance(sig, dict):
        raise RatingsError(f"{role} 부품 '{part.get('name', '?')}'에 핀 {pin}의 signals 사양이 없음")
    out, assumptions = {}, []
    for k, label in keys.items():
        e = sig.get(k)
        if not isinstance(e, dict) or "value" not in e:
            raise RatingsError(f"{role} {pin}: {label}({k}) 값이 없음")
        v = e["value"]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise RatingsError(f"{role} {pin}: {k}는 숫자여야 함")
        if e.get("basis") not in BASES:
            raise RatingsError(f"{role} {pin}: {k}의 근거(basis)는 {BASES} 중 하나여야 함")
        out[k] = float(v)
        if e["basis"] != "datasheet":
            assumptions.append({"field": f"{role}.{pin}.{k}", "value": v,
                                "reason": f"[{e['basis']}] {e.get('note') or '사유 미기재'} (미검증)"})
    return out, assumptions


def level_link_block(src_part, src_pin, sink_part, sink_pin, signal_max_hz, block_id="B1"):
    """(블록, assumptions) 반환. 블록은 intent.BLOCK_PARAMS['level_shift_divider'] 형식."""
    if isinstance(signal_max_hz, bool) or not isinstance(signal_max_hz, (int, float)) or signal_max_hz <= 0:
        raise RatingsError("signal_max_hz는 양수여야 함")
    s, a1 = _get(src_part, src_pin, SRC_KEYS, "보내는 쪽")
    k, a2 = _get(sink_part, sink_pin, SINK_KEYS, "받는 쪽")
    block = {"id": block_id, "type": "level_shift_divider",
             "params": {"src_high_v": s["voh_v"], "src_tol": s["voh_tol"],
                        "src_iout_max_a": s["iout_max_a"],
                        "sink_vih_min_v": k["vih_min_v"], "sink_vmax_v": k["vmax_v"],
                        "signal_max_hz": float(signal_max_hz), "sink_cin_f": k["cin_f"]}}
    a3 = [{"field": "signal_max_hz", "value": signal_max_hz,
           "reason": "사용자/설계자가 지정한 최대 신호 속도"}]
    return block, a1 + a2 + a3


ROLES = ("vcc", "gnd", "in", "out", "nc")
SUPPLY_KEYS = {"min_v": "전원 최소(V)", "max_v": "전원 최대(V)", "current_a": "전원 전류(A)"}
IN_KEYS = {"vih_min_v": "입력 High 인식 최소(V)", "vmax_v": "입력 허용 최대(V)"}
HOST_OUT_KEYS = {"voh_min_v": "호스트 출력 High 최소(V)", "voh_max_v": "호스트 출력 High 최대(V)"}


def _flat(entries, keys, role):
    """{key: {value,basis,note}} 묶음을 검사해 (값, 가정 목록)으로."""
    out, ass = {}, []
    for k, label in keys.items():
        e = (entries or {}).get(k)
        if not isinstance(e, dict) or "value" not in e:
            raise RatingsError(f"{role}: {label}({k}) 값이 없음")
        v = e["value"]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise RatingsError(f"{role}: {k}는 숫자여야 함")
        if e.get("basis") not in BASES:
            raise RatingsError(f"{role}: {k}의 근거(basis)는 {BASES} 중 하나여야 함")
        out[k] = float(v)
        if e["basis"] != "datasheet":
            ass.append({"field": f"{role}.{k}", "value": v,
                        "reason": f"[{e['basis']}] {e.get('note') or '사유 미기재'} (미검증)"})
    return out, ass


def logic_module_block(module, connections, block_id="B1"):
    """모듈 사양 + 연결 정보 -> logic_module 블록. 모듈 이름·핀 개수·핀 이름에 의존하지 않는다.

    module: {"name", "pin_order_verified", "pins": [{"number","name","role"}],
             "supply": {핀이름: {min_v,max_v,current_a}}, "signals": {핀이름: 신호 사양}}
      - role은 데이터에 명시되어야 한다 (이름으로 추측하지 않음): vcc|gnd|in|out|nc
    connections: {핀이름: 설계자가 정하는 연결}
      - vcc: {"rail": "INPUT" 또는 ldo 블록 id}
      - in : {"host_out": {"voh_min_v", "voh_max_v"}}      호스트가 그 핀을 구동
      - out: {"sink_part", "sink_pin", "signal_max_hz"}    그 핀이 호스트 입력을 구동
      - nc : {"reason": "..."}
    """
    pins_in = module.get("pins")
    if not isinstance(pins_in, list) or not pins_in:
        raise RatingsError("모듈 핀 목록이 없음")
    ass, pins = [], []
    for e in pins_in:
        name, num, role = str(e.get("name", "")), str(e.get("number", "")), e.get("role")
        if role not in ROLES:
            raise RatingsError(f"핀 {name or num}: role이 {ROLES} 중 하나여야 함 (이름으로 추측하지 않음): {role!r}")
        ent = {"number": num, "role": role, "label": name}
        conn = connections.get(name, {})
        who = f"모듈 핀 {name}"
        if role == "vcc":
            if "rail" not in conn:
                raise RatingsError(f"{who}: connections에 rail 필요")
            sp, a = _flat((module.get("supply") or {}).get(name), SUPPLY_KEYS, who)
            ent.update({"rail": conn["rail"], "min_v": sp["min_v"], "max_v": sp["max_v"],
                        "current_a": sp["current_a"]})
            ass += a
        elif role == "in":
            if "host_out" not in conn:
                raise RatingsError(f"{who}: connections에 host_out 필요")
            sg, a1 = _flat((module.get("signals") or {}).get(name), IN_KEYS, who)
            ho, a2 = _flat(conn["host_out"], HOST_OUT_KEYS, f"{who}를 구동하는 호스트 출력")
            ent.update({"host_voh_min_v": ho["voh_min_v"], "host_voh_max_v": ho["voh_max_v"],
                        "vih_min_v": sg["vih_min_v"], "vmax_v": sg["vmax_v"]})
            ass += a1 + a2
        elif role == "out":
            for k in ("sink_part", "sink_pin", "signal_max_hz"):
                if k not in conn:
                    raise RatingsError(f"{who}: connections에 {k} 필요")
            blk, a = level_link_block(module, name, conn["sink_part"], conn["sink_pin"], conn["signal_max_hz"], block_id)
            q = blk["params"]
            ent.update({"voh_v": q["src_high_v"], "voh_tol": q["src_tol"], "iout_max_a": q["src_iout_max_a"],
                        "sink_vih_min_v": q["sink_vih_min_v"], "sink_vmax_v": q["sink_vmax_v"],
                        "signal_max_hz": q["signal_max_hz"], "sink_cin_f": q["sink_cin_f"]})
            ass += a
        elif role == "nc":
            if not str(conn.get("reason", "")).strip():
                raise RatingsError(f"{who}: NC는 reason이 필요")
            ent["reason"] = conn["reason"]
        pins.append(ent)
    verified = module.get("pin_order_verified") is True
    if not verified:
        ass.append({"field": "모듈.pin_order_verified", "value": False,
                    "reason": "핀 순서를 실제 기판에서 확인하지 못함 (미검증)"})
    return {"id": block_id, "type": "logic_module",
            "params": {"pins": pins, "pin_order_verified": verified}}, ass
