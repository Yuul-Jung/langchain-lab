"""부품 설명에서 '기능값'을 뽑아 기준 부품과 후보가 어긋나는지 본다 (기준 부품 고정 PARTS_ANCHOR_LOCK 에서만 쓴다).

기능값 = 부품이 내놓거나 구현하는 값. 같은 기능군 안에서도 이 값이 다르면 대체품이 아니다:
극성(NPN/PNP, N/P 채널, 양/음 전압), 고정 출력·기준 전압, 통신 방식, 무선 대역·발진 주파수, 재는 물리량, 논리 기능의 종류.
3차 판정에서 켬이 낸 틀린 부품의 가장 큰 덩어리가 이것이었다(고정 출력 −12V 의 자리에 −5V, NPN 의 자리에 PNP, I2C 의 자리에 SPI).

원칙
- 카탈로그 설명에 **양쪽 모두 적혀 있고 겹치는 값이 하나도 없을 때만** 어긋남으로 본다. 한쪽에라도 적혀 있지 않으면 모르는 것이다(빼지 않는다).
- 낱말은 낱말 경계로 찾는다(maximum 속의 IMU, industrial 속의 dust 를 읽지 않게). 주파수는 범위끼리 겹치는지로 본다.
- 정격(견디는 한계)을 고정 출력으로 읽지 않는다: 출력이라고 밝힌 글만, 설명 맨 앞 전압은 레귤레이터에서 24V 이하일 때만.
- 부품 목록을 두지 않고 글의 모양으로만 뽑는다. 모델 호출 없음.
(2026-11-15 동료 검토 반영: 재는 것의 부분집합 규칙이 맞는 후보 4만여 쌍을 뺐고, 범위 주파수·정격 전압을 잘못 읽는 곳이 있었다.)
"""
from __future__ import annotations

import re

W = r"(?<![A-Za-z])"          # 낱말 앞 경계(영문자가 바로 앞에 오지 않음)
E = r"(?![A-Za-z])"           # 낱말 뒤 경계

INTERFACES = [
    ("I2C", r"I[2²]C|IIC|" + W + r"TWI" + E + r"|SMBus|two[- ]wire"),
    ("SPI", W + r"Q?SPI" + E),
    ("UART", W + r"US?ART" + E + r"|RS-?232|serial\s+port"),
    ("CAN", W + r"CAN" + E + r"(?!\s+be)|CAN-?FD"),
    ("LIN", W + r"LIN" + E),
    ("USB", W + r"USB"),
    ("I2S", r"I[2²]S" + E),
    ("1-Wire", r"1-?wire|one-?wire"),
    ("RS485", r"RS-?485|RS-?422"),
    ("RGMII", r"RGMII"),
    ("MII", W + r"R?MII" + E),
    ("Modbus", r"modbus"),
    ("PWM출력", r"PWM\s+output"),
    ("병렬", r"parallel\s+(?:interface|bus)"),
    ("아날로그출력", r"analog(?:ue)?\s+output|ratiometric"),
]
# 재는 물리량(센서). 보정·차폐·동작 범위를 말하는 글은 재는 것이 아니다
QUANTITIES = [
    ("온도", W + r"temperature(?!\s*(?:compensat|range|coefficient|drift|stable|grade))|thermo(?:meter|couple|pile)|thermistor"),
    ("습도", r"humidity|%\s?RH"), ("압력", r"pressure|baromet"),
    ("가속도", r"acceler|" + W + r"IMU" + E + r"|(?<![\d-])[69]-?\s*axis"), ("자이로", r"gyro|" + W + r"IMU" + E + r"|(?<![\d-])[69]-?\s*axis"),
    ("지자기", r"magnetometer|compass|magnetic\s+(?:field\s+)?sens|(?<![\d-])9-?\s*axis"),
    ("빛", W + r"light" + E + r"|" + W + r"lux" + E + r"|ambient\s+light|colou?r\s+sens|" + W + r"RGB" + E + r"|photo(?:diode|transistor|detector)|"
          + r"(?<![A-Za-z0-9])UV" + E + r"(?!\s*lock)"),
    ("거리", r"proximity|distance|time[- ]of[- ]flight|" + W + r"ToF" + E + r"|ranging"),
    ("전류", r"current\s+(?:sens|monitor|shunt)|shunt\s+monitor"),
    ("CO2", r"CO2|carbon\s+dioxide"), ("가스", W + r"gas" + E + r"|" + W + r"VOC" + E + r"|air\s+quality"),
    ("먼지", r"particulate|PM2\.5|" + W + r"dust" + E), ("소리", r"microphone|" + W + r"sound" + E),
]
LOGIC = [("NAND", r"\bnand\b"), ("NOR", r"(?<![a-z])nor\b(?!\s*flash)"), ("XNOR", r"\bxnor\b"), ("XOR", r"\bxor\b"),
         ("AND", r"\band\s+gate|\binput\s+and\b"), ("OR", r"\bor\s+gate|\binput\s+or\b"), ("인버터", r"inverter|\bnot\s+gate"),
         ("버퍼", r"buffer|line\s+driver"), ("플립플롭", r"flip-?flop"), ("래치", r"latch"), ("카운터", r"counter"), ("시프트", r"shift\s+register"),
         ("디코더", r"decoder|demultiplexer"), ("먹스", r"(?<!de)multiplexer|\bmux\b"), ("인코더", r"encoder")]
NUM = r"(-?\d+(?:\.\d+)?)"
FIXED_OUT = [r"fixed(?:\s+output)?\s*(?:voltage\s*)?" + NUM + r"\s*V(?![A-Za-z])",        # Fixed Output 12V
             NUM + r"\s*V\s+(?:fixed\s+)?(?:output|out)(?![a-z])",                             # 3.3V fixed output, 2.85V output ('20V Fixed LDO' 의 20V 는 정격)
             r"output\s*(?:voltage\s*)?(?:of\s*)?" + NUM + r"\s*V(?![A-Za-z])(?!\s*(?:to|-|~|\.\.))"]   # output voltage 5V
LEADING_V = r"^" + NUM + r"\s*V(?!\s*(?:to|-|~|\.\.|/))[\s,](?!\s*(?:input|vin|max|wide))"   # '12V, 3A SIMPLE SWITCHER …', '5V 3A Step-Down …'
REFERENCE_V = [r"(?:reference|vref)[^,;]{0,24}?" + NUM + r"\s*V(?![A-Za-z])(?!\s*(?:to|-|~|\.\.))", NUM + r"\s*V[^,;]{0,16}?(?:voltage\s+)?reference"]
REGULATOR_FUNCTIONS = {"ldo", "switching_reg", "dcdc_module"}
MAX_LEADING_OUTPUT = 24.0        # 설명 맨 앞 전압이 이보다 크면 입력 정격일 가능성이 높다('60V, 0.6A stepdown')
POINT_FREQ_FUNCTIONS = {"crystal", "oscillator", "rf_filter", "rf_module"}     # 주파수가 한 값으로 정해지는 부품(나머지 RF 부품은 범위로 견준다)
FREQ_RANGE = r"(?:(DC)|(\d+(?:\.\d+)?)\s*(k|M|G)?(?:Hz)?)\s*(?:-|–|to|~|\.\.)\s*(\d+(?:\.\d+)?)\s*(k|M|G)Hz"
FREQ_POINT = r"(\d+(?:\.\d+)?)\s*(k|M|G)Hz"
MULT = {"k": 0.001, "M": 1.0, "G": 1000.0}


def _frequencies(desc: str, name: str, function: str) -> set[tuple[float, float]]:
    """글의 주파수를 (아래, 위) MHz 범위로. 한 값은 (값, 값)."""
    out, rest = set(), desc
    for m in re.finditer(FREQ_RANGE, desc):
        dc, lo, lo_unit, hi, hi_unit = m.groups()
        top = float(hi) * MULT[hi_unit]
        out.add((0.0 if dc else float(lo) * MULT[lo_unit or hi_unit], top))
        rest = rest.replace(m.group(), " ")
    if function in POINT_FREQ_FUNCTIONS or not out:
        points = {round(float(v) * MULT[u], 3) for v, u in re.findall(FREQ_POINT, rest)}
        points |= {float(m) for m in re.findall(r"-(\d{3})(?:S\d|MHZ|M)(?![A-Za-z0-9])", name, re.I)}     # 이름 끝의 대역 표기(…-915S2)
        if function not in ("crystal", "oscillator"):
            points = {p for p in points if p >= 30}          # 무선 대역만(대역폭 500 kHz 같은 값은 뺀다)
        out |= {(p, p) for p in points}
    return out


def values(part: dict, domain: str = "", function: str = "") -> dict[str, set]:
    """부품의 기능값 {속성: 값의 집합}. 설명에 없으면 그 속성은 들어가지 않는다. 키워드 칸은 통신 방식·극성에만 쓴다(덧붙은 낱말이 많다)."""
    desc, name = str(part.get("description") or ""), str(part.get("name") or "")
    text = desc + " " + str(part.get("keywords") or "")
    low = desc.lower()
    out: dict[str, set] = {}

    def put(key, vals):
        vals = set(vals)
        if vals:
            out[key] = vals
    put("극성", (["NPN"] if re.search(W + "NPN" + E, text) else []) + (["PNP"] if re.search(W + "PNP" + E, text) else []))
    put("채널", (["N"] if re.search(W + r"N-?\s?(?:channel|ch(?![a-z])|mos)", text, re.I) else [])
        + (["P"] if re.search(W + r"P-?\s?(?:channel|ch(?![a-z])|mos)", text, re.I) else []))
    put("통신 방식", [n for n, rx in INTERFACES if re.search(rx, text, re.I if n not in ("CAN", "LIN") else 0)])
    if function in REGULATOR_FUNCTIONS or function == "reference":
        put("전압 부호", (["음"] if re.search(r"\bnegative\b", low) else []) + (["양"] if re.search(r"\bpositive\b", low) else []))
        fixed = {abs(float(m)) for rx in FIXED_OUT for m in re.findall(rx, desc, re.I)}
        if function in REGULATOR_FUNCTIONS:
            if not fixed:                      # 출력이라고 밝힌 값이 없을 때만 설명 맨 앞 전압을 출력으로 읽는다
                fixed = {abs(float(m)) for m in re.findall(LEADING_V, desc, re.I) if abs(float(m)) <= MAX_LEADING_OUTPUT}
        else:
            fixed |= {abs(float(m)) for rx in REFERENCE_V for m in re.findall(rx, desc, re.I)}
        if re.search(r"adjustable|variable|programmable\s+output", low):
            fixed = set()                      # 가변형은 값을 맞출 수 있으므로 고정값으로 비교하지 않는다
        put("고정 전압", fixed)
    if domain == "rf" or function in ("crystal", "oscillator"):
        put("주파수(MHz)", _frequencies(desc, name, function))
    if domain == "sensor":
        put("재는 것", [n for n, rx in QUANTITIES if re.search(rx, desc, re.I)])
    if domain == "logic":
        put("논리 기능", [n for n, rx in LOGIC if re.search(rx, low)])
    return out


def _overlap(key: str, a: set, c: set) -> bool:
    if key == "주파수(MHz)":
        return any(lo1 <= hi2 and lo2 <= hi1 for lo1, hi1 in a for lo2, hi2 in c)
    return bool(a & c)


def conflicts(anchor: dict[str, set], cand: dict[str, set], ignore: tuple[str, ...] = ()) -> list[str]:
    """기준 부품과 후보의 기능값이 어긋나는 속성 이름. 양쪽 모두 적혀 있고 겹치는 값이 하나도 없을 때만.
    ignore: 질문이 그 값을 바꿔 달라고 한 속성(예: '출력 전압이 더 높은')은 견주지 않는다."""
    return [key for key, a in anchor.items() if key not in ignore and cand.get(key) and not _overlap(key, a, cand[key])]


def shared(anchor: dict[str, set], cand: dict[str, set]) -> int:
    """기준 부품의 값을 후보가 모두 갖춘 것이 확인된 속성의 수(후보 순서를 정할 때 쓴다). 재는 것은 기준 부품이 재는 것을 다 재야 센다."""
    n = 0
    for key, a in anchor.items():
        c = cand.get(key)
        if not c:
            continue
        if key == "주파수(MHz)":
            n += _overlap(key, a, c)
        elif key == "재는 것":
            n += a <= c
        else:
            n += bool(a & c)
    return n
