"""IntentSpec: 사용자의 회로 '의도'를 담는 닫힌(closed) JSON 계약.

자연어 파서, LLM 어댑터, 비전 어댑터는 모두 이 형식만 출력할 수 있다.
KiCad 파일·부품 값·넷 연결은 여기에 들어가지 않는다 (그건 합성기의 책임).

파서 원칙
- 숫자 사양(전압/전류/주파수)을 인식했는데 용도를 분류하지 못하면 버리지 않고 BLOCKING 질문을 만든다.
- 기본값으로 채운 항목은 반드시 assumptions에 사유와 함께 기록한다.
"""
from __future__ import annotations

import re

SCHEMA_ID = "eda.intent/1"
LDO_VOUTS = (1.8, 2.5, 3.3, 5.0)
LED_COLORS = {"red": 2.0, "green": 2.1, "yellow": 2.1, "blue": 3.0, "white": 3.0}

_NUM = (int, float)


def _num(lo=None, hi=None, lo_open=False, allowed=None):
    def check(v):
        if isinstance(v, bool) or not isinstance(v, _NUM):
            return "숫자가 아님"
        if allowed is not None and not any(abs(v - a) < 1e-9 for a in allowed):
            return f"허용값 {allowed} 아님"
        if lo is not None and (v <= lo if lo_open else v < lo):
            return f"{lo} {'초과' if lo_open else '이상'}이어야 함"
        if hi is not None and v > hi:
            return f"{hi} 이하여야 함"
        return None
    return check


def _enum(*vals):
    return lambda v: None if v in vals else f"{vals} 중 하나여야 함"


def _bool(v):
    return None if isinstance(v, bool) else "bool이 아님"


def _str(v):
    return None if isinstance(v, str) and v else "비어있지 않은 문자열이어야 함"


_PIN_ROLES = {
    "vcc": {"rail": _str, "min_v": _num(0, 48, lo_open=True), "max_v": _num(0, 48, lo_open=True),
            "current_a": _num(0, 5, lo_open=True)},
    "gnd": {},
    # 호스트가 모듈 입력을 구동: 호스트 High 출력 범위가 모듈 입력 사양 안이어야 함
    "in": {"host_voh_min_v": _num(0, 48, lo_open=True), "host_voh_max_v": _num(0, 48, lo_open=True),
           "vih_min_v": _num(0, 48, lo_open=True), "vmax_v": _num(0, 48, lo_open=True)},
    # 모듈 출력이 호스트 입력을 구동: 받는 쪽 한계보다 높으면 분압 레벨 변환
    "out": {"voh_v": _num(0, 48, lo_open=True), "voh_tol": _num(0, 0.3),
            "iout_max_a": _num(0, 0.1, lo_open=True), "sink_vih_min_v": _num(0, 48, lo_open=True),
            "sink_vmax_v": _num(0, 48, lo_open=True), "signal_max_hz": _num(0, 1e7, lo_open=True),
            "sink_cin_f": _num(0, 1e-9, lo_open=True)},
    "nc": {"reason": _str},
}


def _pins_spec(v):
    """logic_module의 pins 배열 검증. 오류 문자열 또는 None."""
    if not isinstance(v, list) or not v:
        return "비어있지 않은 배열이어야 함"
    if len(v) > 20:
        return "핀은 20개까지"
    nums, roles = set(), []
    for i, e in enumerate(v):
        if not isinstance(e, dict) or "number" not in e or "role" not in e:
            return f"[{i}]: number, role 필수"
        spec = _PIN_ROLES.get(e["role"])
        if spec is None:
            return f"[{i}]: role은 {sorted(_PIN_ROLES)} 중 하나 (양방향 등은 미지원)"
        if not isinstance(e["number"], str) or not e["number"]:
            return f"[{i}]: number는 문자열"
        nums.add(e["number"])
        allowed = {"number", "role", "label"} | set(spec)
        for k in e:
            if k not in allowed:
                return f"[{i}]/{k}: 허용되지 않은 키"
        if "label" in e and not isinstance(e["label"], str):
            return f"[{i}]/label: 문자열"
        for k, chk in spec.items():
            if k not in e:
                return f"[{i}]/{k}: 필수 키 누락"
            err = chk(e[k])
            if err:
                return f"[{i}]/{k}: {err}"
        roles.append(e["role"])
    if sorted(nums) != sorted(str(i) for i in range(1, len(v) + 1)):
        return "핀 번호는 '1'부터 핀 개수까지 빠짐없이 한 번씩"
    if "vcc" not in roles or "gnd" not in roles:
        return "vcc와 gnd 핀이 각각 1개 이상 필요"
    return None


BLOCK_PARAMS = {
    "ldo": {"rail_in": _str, "vout_v": _num(allowed=LDO_VOUTS),
            "iout_max_a": _num(0, 1.0, lo_open=True)},
    "led_indicator": {"rail": _str, "color": _enum(*LED_COLORS),
                      "current_a": _num(0, 0.02, lo_open=True)},
    "blinker_555": {"rail": _str, "freq_hz": _num(0.01, 10000),
                    "color": _enum(*LED_COLORS),
                    "led_current_a": _num(0, 0.02, lo_open=True)},
    "lowside_switch": {"rail": _str, "load_current_a": _num(0, 100, lo_open=True),
                       "inductive": _bool, "control_v": _num(1.0, 24)},
    # 범용 레벨 변환(하향) 분압기: 특정 부품 이름 없이 수치 사양만 받는다
    "level_shift_divider": {"src_high_v": _num(0, 48, lo_open=True), "src_tol": _num(0, 0.3),
                            "src_iout_max_a": _num(0, 0.1, lo_open=True),
                            "sink_vih_min_v": _num(0, 48, lo_open=True),
                            "sink_vmax_v": _num(0, 48, lo_open=True),
                            "signal_max_hz": _num(0, 1e7, lo_open=True),
                            "sink_cin_f": _num(0, 1e-9, lo_open=True)},
    # 범용 로직 모듈: 핀 목록(역할 vcc/gnd/in/out/nc)과 핀별 수치 사양. 부품 이름·핀 개수에 의존하지 않는다.
    "logic_module": {"pins": lambda v: _pins_spec(v), "pin_order_verified": _bool},
}
TOP_KEYS = {"schema", "source", "power_input", "blocks", "assumptions",
            "questions", "unparsed"}


def validate_intent(intent) -> list:
    """닫힌 스키마 검증. 오류 문자열 목록 반환 (빈 목록이면 유효)."""
    errs = []
    if not isinstance(intent, dict):
        return ["intent는 object여야 함"]
    for k in intent:
        if k not in TOP_KEYS:
            errs.append(f"/{k}: 허용되지 않은 키")
    for k in TOP_KEYS:
        if k not in intent:
            errs.append(f"/{k}: 필수 키 누락")
    if errs:
        return errs
    if intent["schema"] != SCHEMA_ID:
        errs.append(f"/schema: {SCHEMA_ID} 이어야 함")
    src = intent["source"]
    if not isinstance(src, dict) or src.get("kind") not in ("text", "image", "manual", "llm"):
        errs.append("/source/kind: text|image|manual|llm")
    pi = intent["power_input"]
    if pi is not None:
        if not isinstance(pi, dict) or set(pi) != {"connector", "voltage_v"}:
            errs.append("/power_input: {connector, voltage_v} 만 허용")
        else:
            e = _enum("usb_c", "dc")(pi["connector"])
            if e:
                errs.append(f"/power_input/connector: {e}")
            e = _num(0, 48, lo_open=True)(pi["voltage_v"])
            if e:
                errs.append(f"/power_input/voltage_v: {e}")
            if pi.get("connector") == "usb_c" and pi.get("voltage_v") != 5.0:
                errs.append("/power_input: usb_c는 5.0V만 허용 (PD 협상 미지원)")
    blocks = intent["blocks"]
    if not isinstance(blocks, list):
        return errs + ["/blocks: 배열이어야 함"]
    seen = {}
    for i, b in enumerate(blocks):
        p = f"/blocks/{i}"
        if not isinstance(b, dict) or set(b) != {"id", "type", "params"}:
            errs.append(f"{p}: {{id, type, params}} 만 허용")
            continue
        if not re.fullmatch(r"B[0-9]{1,3}", str(b["id"])):
            errs.append(f"{p}/id: B<숫자> 형식")
        if b["id"] in seen:
            errs.append(f"{p}/id: 중복 {b['id']}")
        spec = BLOCK_PARAMS.get(b["type"])
        if spec is None:
            errs.append(f"{p}/type: 지원하지 않는 블록 {b['type']!r}")
            seen[b["id"]] = b["type"]
            continue
        params = b["params"]
        if not isinstance(params, dict):
            errs.append(f"{p}/params: object여야 함")
            continue
        for k in params:
            if k not in spec:
                errs.append(f"{p}/params/{k}: 허용되지 않은 키")
        for k, chk in spec.items():
            if k not in params:
                errs.append(f"{p}/params/{k}: 필수 키 누락")
                continue
            e = chk(params[k])
            if e:
                errs.append(f"{p}/params/{k}: {e}")
        for rk in ("rail", "rail_in"):
            if rk in params and isinstance(params[rk], str):
                r = params[rk]
                if r != "INPUT" and seen.get(r) != "ldo":
                    errs.append(f"{p}/params/{rk}: 'INPUT' 또는 앞서 정의된 ldo 블록 id여야 함")
        seen[b["id"]] = b["type"]
    if blocks and pi is None:
        errs.append("/power_input: 블록이 있으면 입력 전원이 필요함")
    for i, q in enumerate(intent["questions"]):
        if not isinstance(q, dict) or set(q) != {"id", "text", "blocking"}:
            errs.append(f"/questions/{i}: {{id, text, blocking}} 만 허용")
    for i, a in enumerate(intent["assumptions"]):
        if not isinstance(a, dict) or set(a) != {"field", "value", "reason"}:
            errs.append(f"/assumptions/{i}: {{field, value, reason}} 만 허용")
    if not isinstance(intent["unparsed"], list):
        errs.append("/unparsed: 배열이어야 함")
    return errs


def blocking_questions(intent) -> list:
    return [q for q in intent.get("questions", []) if q.get("blocking")]


# ---------------------------------------------------------------- 자연어 파서

_V_RE = re.compile(r"(\d+)[Vv](\d+)|(\d+(?:\.\d+)?)\s*[Vv](?![A-Za-z0-9])")
_I_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mA|A)(?![A-Za-z])")
_F_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kHz|Hz)(?![A-Za-z])", re.I)

_LOAD_KW = r"모터|motor|릴레이|relay|솔레노이드|solenoid|팬|fan|히터|heater|부하|load"
_INDUCTIVE_KW = r"모터|motor|릴레이|relay|솔레노이드|solenoid|팬|fan"
_CTRL_KW = r"MCU|마이컴|GPIO|로직|logic|신호|signal|제어|control"
_IN_AFTER = r"입력|input|전원|어댑터|adapter|supply|DC|에서|로부터|으로부터|in\b"
_OUT_AFTER = r"LDO|레귤|regulat|출력|output|레일|rail|으로|로\b|로\s|로$|로,"
_COLOR_KW = [("red", r"빨간|빨강|적색|red"), ("green", r"초록|녹색|green"),
             ("blue", r"파란|파랑|청색|blue"), ("yellow", r"노란|노랑|황색|yellow"),
             ("white", r"흰|하얀|백색|white")]


def _mentions(regex, text, conv):
    out = []
    for m in regex.finditer(text):
        out.append({"value": conv(m), "start": m.start(), "end": m.end(),
                    "raw": m.group(0), "used": False})
    return out


def _v_conv(m):
    if m.group(1):
        return float(f"{m.group(1)}.{m.group(2)}")
    return float(m.group(3))


def _after(text, m, n=10):
    return text[m["end"]:m["end"] + n].lstrip()


def _before(text, m, n=10):
    return text[max(0, m["start"] - n):m["start"]].rstrip()


def parse_text(text: str) -> dict:
    """규칙 기반 한/영 자연어 -> IntentSpec. 모호하면 질문을 만든다."""
    t = " ".join(text.split())
    low = t.lower()
    volts = _mentions(_V_RE, t, _v_conv)
    amps = _mentions(_I_RE, t, lambda m: float(m.group(1)) * (1e-3 if m.group(2) == "mA" else 1.0))
    freqs = _mentions(_F_RE, t, lambda m: float(m.group(1)) * (1e3 if m.group(2).lower() == "khz" else 1.0))

    assumptions, questions = [], []

    def ask(text_, blocking=True):
        questions.append({"id": f"Q{len(questions) + 1}", "text": text_, "blocking": blocking})

    def assume(field_, value, reason):
        assumptions.append({"field": field_, "value": value, "reason": reason})

    v_in = v_out = v_load = v_ctrl = None
    for m in volts:
        a, b = _after(t, m), _before(t, m)
        if re.match(_LOAD_KW, a, re.I):
            v_load, m["used"] = m["value"], True
        elif re.match(_CTRL_KW, a, re.I):
            v_ctrl, m["used"] = m["value"], True
        elif re.match(_IN_AFTER, a, re.I) or re.search(r"(from|입력|input)\s*:?$", b, re.I):
            if v_in is None or v_in == m["value"]:
                v_in, m["used"] = m["value"], True
        elif re.match(_OUT_AFTER, a, re.I) or re.search(r"(to|→|->)$", b, re.I):
            if v_out is None or v_out == m["value"]:
                v_out, m["used"] = m["value"], True

    has_usb = bool(re.search(r"usb", low))
    has_ldo_kw = bool(re.search(r"ldo|레귤레이터|레귤|regulator|강압|변환", low))
    has_led = bool(re.search(r"led|엘이디", low))
    has_blink = bool(re.search(r"깜빡|점멸|blink|flash|플래시", low))
    has_indicator = bool(re.search(r"(전원|power|상태|status)\s*(led|엘이디)|표시", low))
    has_load = bool(re.search(_LOAD_KW, low))
    inductive = bool(re.search(_INDUCTIVE_KW, low))

    # USB만 있고 분류 안 된 전압이 LDO 문맥이면 출력으로 본다
    if has_ldo_kw and v_out is None:
        free = [m for m in volts if not m["used"] and (v_in is None or m["value"] < v_in)]
        if len(free) == 1:
            v_out, free[0]["used"] = free[0]["value"], True

    power_input = None
    if has_usb:
        if v_in not in (None, 5.0):
            ask(f"USB-C 입력은 5V만 지원합니다. 입력 {v_in}V는 별도 DC 입력인가요?")
        power_input = {"connector": "usb_c", "voltage_v": 5.0}
    elif v_in is not None:
        power_input = {"connector": "dc", "voltage_v": v_in}

    blocks = []

    def add_block(type_, params):
        bid = f"B{len(blocks) + 1}"
        blocks.append({"id": bid, "type": type_, "params": params})
        return bid

    ldo_id = None
    if has_ldo_kw or v_out is not None:
        if v_out is None:
            ask("레귤레이터 출력 전압이 명시되지 않았습니다. 몇 V가 필요합니까?")
        elif not any(abs(v_out - a) < 1e-9 for a in LDO_VOUTS):
            ask(f"{v_out}V 출력 LDO는 라이브러리에 없습니다 (지원: {LDO_VOUTS}).")
        else:
            iout = None
            for m in amps:
                if not m["used"] and re.search(r"(ldo|레귤|출력|output|rail|레일)", _before(t, m, 16) + _after(t, m, 6), re.I) \
                        and not re.search(_LOAD_KW, _before(t, m, 12) + _after(t, m, 8), re.I):
                    iout, m["used"] = m["value"], True
                    break
            if iout is None:
                iout = 0.3
                assume("blocks.ldo.iout_max_a", iout, "출력 전류 미지정 — 300mA로 가정")
            ldo_id = add_block("ldo", {"rail_in": "INPUT", "vout_v": v_out, "iout_max_a": iout})

    def color():
        for name, kw in _COLOR_KW:
            if re.search(kw, low):
                return name
        assume("led.color", "red", "LED 색상 미지정 — 빨강(Vf≈2.0V)으로 가정")
        return "red"

    if has_blink:
        f = None
        for m in freqs:
            f, m["used"] = m["value"], True
            break
        if f is None:
            f = 1.0
            assume("blocks.blinker_555.freq_hz", f, "점멸 주파수 미지정 — 1Hz로 가정")
        add_block("blinker_555", {"rail": "INPUT", "freq_hz": f, "color": color(),
                                  "led_current_a": 0.005})
    if has_led and (not has_blink or has_indicator):
        rail = ldo_id or "INPUT"
        add_block("led_indicator", {"rail": rail, "color": color(), "current_a": 0.002})
        assume("blocks.led_indicator.current_a", 0.002, "표시용 LED 전류 2mA 가정")

    if has_load:
        i_load = None
        for m in amps:
            if not m["used"]:
                i_load, m["used"] = m["value"], True
                break
        if i_load is None:
            ask("부하(모터/릴레이 등) 전류가 명시되지 않았습니다. 최대 몇 A입니까?")
        if v_load is not None:
            if power_input is None:
                power_input = {"connector": "dc", "voltage_v": v_load}
                assume("power_input.voltage_v", v_load, "부하 전압을 입력 전원 전압으로 가정")
            elif abs(power_input["voltage_v"] - v_load) > 1e-9:
                ask(f"부하 전압 {v_load}V가 입력 전원 {power_input['voltage_v']}V와 다릅니다. "
                    "별도 부하 전원 입력이 필요합니까?")
        if v_ctrl is None:
            v_ctrl = 3.3
            assume("blocks.lowside_switch.control_v", 3.3, "제어 신호 전압 미지정 — 3.3V 로직으로 가정")
        if i_load is not None:
            add_block("lowside_switch", {"rail": "INPUT", "load_current_a": i_load,
                                         "inductive": inductive, "control_v": v_ctrl})

    if blocks and power_input is None:
        ask("입력 전원 전압과 커넥터(USB-C 5V 또는 DC 몇 V)가 필요합니다.")
    if not blocks and not questions:
        ask("인식 가능한 회로 블록이 없습니다. 지원: LDO, 전원/표시 LED, 555 점멸, 로우사이드 MOSFET 스위치.")

    unparsed = [m["raw"] for m in volts + amps + freqs if not m["used"]]
    for raw in unparsed:
        ask(f"사양 '{raw}'의 용도를 판단하지 못했습니다. 무엇에 대한 값입니까?")

    return {"schema": SCHEMA_ID, "source": {"kind": "text", "text": text},
            "power_input": power_input, "blocks": blocks,
            "assumptions": assumptions, "questions": questions, "unparsed": unparsed}
