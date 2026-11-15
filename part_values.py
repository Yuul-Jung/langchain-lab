"""부품 설명에서 '기능값'을 뽑아 기준 부품과 후보가 어긋나는지 본다 (기준 부품 고정 PARTS_ANCHOR_LOCK 에서만 쓴다).

기능값 = 부품이 내놓거나 구현하는 값. 같은 기능군 안에서도 이 값이 다르면 대체품이 아니다:
극성(NPN/PNP, N/P 채널, 양/음 전압), 고정 출력·기준 전압, 통신 방식, 무선 대역·발진 주파수, 재는 물리량, 논리 기능의 종류.
3차 판정에서 켬이 낸 틀린 부품의 가장 큰 덩어리가 이것이었다(고정 출력 −12V 의 자리에 −5V, NPN 의 자리에 PNP, I2C 의 자리에 SPI).

원칙: 카탈로그 글(이름·설명·키워드)에 **양쪽 모두 적혀 있고 서로 다를 때만** 어긋남으로 본다. 한쪽에라도 적혀 있지 않으면 모르는 것이다(빼지 않는다).
부품 목록을 두지 않고 글의 모양으로만 뽑는다. 모델 호출 없음.
"""
from __future__ import annotations

import re

# 통신 방식: (이름, 글에서 찾는 정규식). 설명의 표기가 제각각이라 흔한 변형을 함께 받는다
INTERFACES = [
    ("I2C", r"I[2²]C|IIC|(?<![A-Za-z])TWI(?![A-Za-z])|SMBus|two[- ]wire"),
    ("SPI", r"(?<![A-Za-z])Q?SPI(?![A-Za-z])"),
    ("UART", r"(?<![A-Za-z])US?ART(?![A-Za-z])|RS-?232|serial\s+port"),
    ("CAN", r"(?<![A-Za-z])CAN(?![A-Za-z])(?!\s+be)|CAN-?FD"),
    ("LIN", r"(?<![A-Za-z])LIN(?![A-Za-z])"),
    ("USB", r"(?<![A-Za-z])USB"),
    ("I2S", r"I[2²]S(?![A-Za-z])"),
    ("1-Wire", r"1-?wire|one-?wire"),
    ("RS485", r"RS-?485|RS-?422"),
    ("RGMII", r"RGMII"),
    ("MII", r"(?<![A-Za-z])R?MII(?![A-Za-z])"),
    ("Modbus", r"modbus"),
    ("PWM출력", r"PWM\s+output"),
    ("병렬", r"parallel\s+(?:interface|bus)|parallel$"),
    ("아날로그출력", r"analog(?:ue)?\s+output|ratiometric"),
]
# 재는 물리량
QUANTITIES = [
    ("온도", r"temperature|thermo|°C"), ("습도", r"humidity|%RH"), ("압력", r"pressure|barometr"),
    ("가속도", r"acceler|(?<![\d-])[69]-?\s*axis|IMU|motion"), ("자이로", r"gyro|(?<![\d-])[69]-?\s*axis|IMU"),
    ("지자기", r"magnet|compass|(?<![\d-])9-?\s*axis|hall"), ("빛", r"light|lux|ambient|colou?r|RGB|photo(?!acoustic)|UV"),
    ("거리", r"proximity|distance|time[- ]of[- ]flight|ToF|ranging"), ("전류", r"current\s+sens|current\s+monitor|shunt"),
    ("CO2", r"CO2|carbon\s+dioxide"), ("가스", r"(?<![A-Za-z])gas|VOC|air\s+quality"), ("먼지", r"particulate|PM2\.5|dust"),
    ("소리", r"microphone|sound"),
]
LOGIC = [("NAND", r"\bnand\b"), ("NOR", r"(?<![a-z])nor\b(?!\s*flash)"), ("XOR", r"\bxn?or\b"), ("AND", r"\band\s+gate|\binput\s+and\b"),
         ("OR", r"\bor\s+gate|\binput\s+or\b"), ("인버터", r"inverter|\bnot\s+gate"), ("버퍼", r"buffer|line\s+driver"),
         ("플립플롭", r"flip-?flop"), ("래치", r"latch"), ("카운터", r"counter"), ("시프트", r"shift\s+register"),
         ("디코더", r"decoder|demultiplexer"), ("먹스", r"(?<!de)multiplexer|\bmux\b"), ("인코더", r"encoder")]
FIXED_V = [r"fixed(?:\s+output)?\s*(?:voltage\s*)?(-?\d+(?:\.\d+)?)\s*V(?![A-Za-z])",      # Fixed Output 12V
           r"(-?\d+(?:\.\d+)?)\s*V\s+fixed",                                                # 3.3V fixed
           r"(?:reference|vref)[^,;]{0,24}?(-?\d+(?:\.\d+)?)\s*V(?![A-Za-z])",              # Voltage Reference 2.5V
           r"(-?\d+(?:\.\d+)?)\s*V[^,;]{0,16}?(?:voltage\s+)?reference"]                    # 2.5V Precision Voltage Reference
# 설명 맨 앞의 전압('12V, 3A SIMPLE SWITCHER …', '5V 3A Step-Down …')은 레귤레이터·전압 기준에서만 출력값으로 읽는다.
# 다른 부품에서는 정격일 수 있고('60V 15A N-Channel'), 범위('3.0V to 5.5V')는 전원 범위다
LEADING_V = r"^(-?\d+(?:\.\d+)?)\s*V(?!\s*(?:to|-|~|\.\.|/))[\s,]"
REGULATOR_FUNCTIONS = {"ldo", "switching_reg", "dcdc_module", "reference"}
FREQ = r"(\d+(?:\.\d+)?)\s*(k|M|G)Hz"


def _text(part: dict) -> str:
    return " ".join(str(part.get(k) or "") for k in ("description", "keywords"))


def values(part: dict, domain: str = "", function: str = "") -> dict[str, set]:
    """부품의 기능값 {속성: 값의 집합}. 글에 없으면 그 속성은 들어가지 않는다."""
    desc, text, name = str(part.get("description") or ""), _text(part), str(part.get("name") or "")
    low = text.lower()
    out: dict[str, set] = {}

    def put(key, vals):
        vals = set(vals)
        if vals:
            out[key] = vals
    put("극성", (["NPN"] if re.search(r"(?<![A-Za-z])NPN(?![A-Za-z])", text) else []) + (["PNP"] if re.search(r"(?<![A-Za-z])PNP(?![A-Za-z])", text) else []))
    put("채널", (["N"] if re.search(r"(?<![A-Za-z])N-?\s?(?:channel|ch(?![a-z])|mos)", text, re.I) else [])
        + (["P"] if re.search(r"(?<![A-Za-z])P-?\s?(?:channel|ch(?![a-z])|mos)", text, re.I) else []))
    put("전압 부호", (["음"] if re.search(r"\bnegative\b", low) else []) + (["양"] if re.search(r"\bpositive\b", low) else []))
    put("통신 방식", [n for n, rx in INTERFACES if re.search(rx, text, re.I if n not in ("CAN", "LIN") else 0)])
    fixed = {abs(float(m)) for rx in FIXED_V for m in re.findall(rx, desc, re.I)}
    if function in REGULATOR_FUNCTIONS:
        fixed |= {abs(float(m)) for m in re.findall(LEADING_V, desc)}
    if re.search(r"adjustable|variable|programmable\s+output", low):
        fixed = set()                          # 가변형은 값을 맞출 수 있으므로 고정값으로 비교하지 않는다
    put("고정 전압", fixed)
    if domain == "rf" or function in ("crystal", "oscillator", "rf_module", "antenna", "rf_filter"):
        mult = {"k": 0.001, "M": 1.0, "G": 1000.0}
        freqs = {round(float(v) * mult[u], 3) for v, u in re.findall(FREQ, text)}
        if domain == "rf" and function not in ("crystal", "oscillator"):
            freqs = {f for f in freqs if f >= 30}      # 무선 대역만(대역폭 500 kHz 같은 값은 뺀다)
        freqs |= {float(m) for m in re.findall(r"-(\d{3})(?:S\d|MHZ|M)(?![A-Za-z0-9])", name, re.I)}     # 이름 끝의 대역 표기(…-915S2)
        put("주파수(MHz)", freqs)
    if domain == "sensor":
        put("재는 것", [n for n, rx in QUANTITIES if re.search(rx, text, re.I)])
    if domain == "logic":
        put("논리 기능", [n for n, rx in LOGIC if re.search(rx, low)])
    return out


def conflicts(anchor: dict[str, set], cand: dict[str, set]) -> list[str]:
    """기준 부품과 후보의 기능값이 어긋나는 속성 이름. 양쪽 모두 적힌 속성만 본다.
    재는 것: 후보가 기준 부품이 재는 것을 모두 재야 한다(더 재는 것은 괜찮다). 나머지: 공통 값이 하나도 없으면 어긋남."""
    out = []
    for key, a in anchor.items():
        c = cand.get(key)
        if not c:
            continue
        if key == "재는 것":
            if not a <= c:
                out.append(key)
        elif not (a & c):
            out.append(key)
    return out


def shared(anchor: dict[str, set], cand: dict[str, set]) -> int:
    """기준 부품과 값이 맞는 속성의 수(후보 순서를 정할 때 쓴다)."""
    return sum(1 for key, a in anchor.items() if cand.get(key) and (a <= cand[key] if key == "재는 것" else bool(a & cand[key])))
