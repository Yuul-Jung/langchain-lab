"""여러 조건이 섞인 부품 질문: 질문에서 조건을 뽑고, 후보 부품마다 카탈로그 값으로 조건 충족을 판정한다.

조건 종류(2026-11-14, 평가 전에 고정): 인터페이스 · 전압 · 채널 수 · 패키지 · 저전력 · 절연 · 둘째 기능(사전 개념).
판정은 카탈로그 값(이름·설명·키워드·풋프린트)만 쓴다. 모델 호출 없음.
  ✓ 근거 낱말이 있음 / ✗ 반대되는 값이 있음(예: 3.3V 를 물었는데 5V 고정) / ? 카탈로그에 정보 없음
카탈로그에는 MCU 의 대체 기능(CAN·USB 핀 기능 등)이 없다 — 그런 조건은 ? 로 남기고 답에 그렇다고 쓴다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

OK, NO, UNKNOWN = "✓", "✗", "?"


@dataclass
class Condition:
    family: str                 # interface · voltage · channels · package · low_power · isolated · function
    label: str                  # 화면에 보일 이름(예: 'I2C', '3.3V', '4채널', '승압')
    evidence: str = ""          # 근거를 찾는 정규식(대소문자 무시)
    value: float | None = None  # 전압·채널 수
    words: list[str] = field(default_factory=list)   # 검색어에 덧붙일 영어 낱말


# 인터페이스: (질문에서 찾는 정규식, 표시 이름, 본문 근거 정규식, 검색 낱말)
INTERFACES = [
    (r"(?<![A-Za-z])I2C|(?<![A-Za-z])IIC|아이투씨|아이스퀘어씨", "I2C", r"I2C|IIC|TWI|two-wire|SMBus", ["I2C"]),
    (r"(?<![A-Za-z])SPI(?![A-Za-z])", "SPI", r"(?<![A-Za-z])Q?SPI(?![A-Za-z])", ["SPI"]),
    (r"(?<![A-Za-z])UART|시리얼 통신|(?<![A-Za-z])RS-?232", "UART", r"UART|USART|RS-?232|serial", ["UART"]),
    (r"(?<![A-Za-z])CAN(?![A-Za-z])|캔 통신|캔통신", "CAN", r"(?<![A-Za-z])CAN(?![A-Za-z])|CAN-?FD", ["CAN"]),
    (r"(?<![A-Za-z])USB|유에스비", "USB", r"USB", ["USB"]),
    (r"이더넷|(?<![A-Za-z])ethernet|(?<![A-Za-z])ETH(?![A-Za-z])", "Ethernet", r"ethernet|10/100|PHY", ["Ethernet"]),
    (r"(?<![A-Za-z])RS-?485|(?<![A-Za-z])RS-?422", "RS485", r"RS-?485|RS-?422", ["RS485"]),
    (r"블루투스|(?<![A-Za-z])bluetooth|(?<![A-Za-z])BLE(?![A-Za-z])", "Bluetooth", r"bluetooth|BLE", ["Bluetooth"]),
    (r"와이파이|(?<![A-Za-z])wi-?fi", "WiFi", r"wi-?fi|802\.11", ["WiFi"]),
]
PACKAGES = ["SOT-23", "SOT-223", "SOT-89", "TO-220", "TO-92", "DIP", "SOIC", "SOP", "TSSOP", "MSOP", "QFN", "DFN", "BGA", "LQFP", "TQFP"]
LOW_POWER = (r"저전력|저 전력|low[- ]?power|초저전력", r"low[- ]?power|micro-?power|ultra[- ]?low|nano[- ]?power|low (?:quiescent|IQ)|low current")
ISOLATED = (r"절연", r"isolat")
GENERIC_WORDS = {"sensor", "driver", "ic", "module", "controller", "chip", "device", "interface", "converter", "regulator"}
CHANNEL_WORDS = {"single": 1, "dual": 2, "triple": 3, "quad": 4, "hex": 6, "octal": 8}


def parse(question: str, ontology=None, concept_ids: list[str] | None = None) -> list[Condition]:
    """질문 속 조건 목록. 첫째 개념(주 개념)은 조건이 아니라 검색 대상이므로, 둘째 이후 개념만 'function' 조건이 된다."""
    q = question
    out: list[Condition] = []
    for pat, label, ev, words in INTERFACES:
        if re.search(pat, q, re.I if label not in ("CAN",) else 0):
            out.append(Condition("interface", label, ev, words=words))
    for m in re.finditer(r"(?<![\d.])(\d{1,2}(?:\.\d)?)\s*[vV](?![A-Za-z])", q):
        v = float(m.group(1))
        out.append(Condition("voltage", f"{m.group(1)}V", value=v, words=[f"{m.group(1)}V"]))
    m = re.search(r"(\d{1,2})\s*(?:채널|ch(?![a-z])|channel)", q, re.I)
    if m:
        n = int(m.group(1))
        out.append(Condition("channels", f"{n}채널", value=n))
    for pkg in PACKAGES:
        if re.search(r"(?<![A-Za-z])" + re.escape(pkg).replace(r"\-", "-?"), q, re.I):
            out.append(Condition("package", pkg, r"(?<![A-Za-z])" + re.escape(pkg).replace(r"\-", "[-_ ]?"), words=[pkg]))
    if re.search(LOW_POWER[0], q, re.I):
        out.append(Condition("low_power", "저전력", LOW_POWER[1], words=["low power"]))
    if re.search(ISOLATED[0], q):
        out.append(Condition("isolated", "절연", ISOLATED[1], words=["isolated"]))
    if ontology is not None and concept_ids and len(concept_ids) > 1:
        for c in concept_ids[1:]:
            label = ontology.nodes[c]["label"]
            if any(re.search(pat, label, re.I) for pat, *_ in INTERFACES):
                continue                      # '와이파이'·'CAN 통신' 같은 개념은 이미 인터페이스 조건으로 잡힘
            kws = [ontology.nodes[n]["label"] for n in ontology.neighbors(c) if ontology.nodes[n].get("kind") == "keyword"]
            if not kws:                        # 키워드가 없는 개념은 그 분류의 대표 낱말(일반어 제외) 두 개로 근거를 찾는다
                kws = [w for n in ontology.neighbors(c) if ontology.nodes[n].get("kind") == "library"
                       for w in ontology.nodes[n].get("top_keywords", []) if w.lower() not in GENERIC_WORDS][:2]
            if kws:
                out.append(Condition("function", label,
                                     r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in kws) + r")(?![a-z0-9])", words=kws[:2]))
    # 같은 이름이 두 번 들어오지 않게(예: 'CAN' 이 인터페이스와 둘째 개념 양쪽)
    seen, uniq = set(), []
    for c in out:
        if c.label.lower() not in seen:
            seen.add(c.label.lower())
            uniq.append(c)
    return uniq


def _text(part: dict) -> str:
    return " ".join(str(part.get(k) or "") for k in ("name", "description", "keywords", "footprint"))


def _voltages(text: str) -> tuple[list[tuple[float, float]], list[float]]:
    """본문 속 전압 범위('2.5..16V', '1.8V-5.5V', '2.7 to 5.5V')와 단일 값('3.3V')."""
    ranges = [(float(a), float(b)) for a, b in
              re.findall(r"(\d+(?:\.\d+)?)\s*V?\s*(?:\.\.|-|–|to|~)\s*(\d+(?:\.\d+)?)\s*V(?![A-Za-z])", text)]
    singles = [float(x) for x in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*V(?![A-Za-z])", text)]
    return ranges, singles


def check(cond: Condition, part: dict) -> str:
    text = _text(part)
    if cond.family == "voltage":
        ranges, singles = _voltages(text)
        v = cond.value
        if any(abs(s - v) < 1e-6 for s in singles) or any(lo - 1e-6 <= v <= hi + 1e-6 for lo, hi in ranges):
            return OK
        return NO if (ranges or singles) else UNKNOWN
    if cond.family == "channels":
        nums = [int(x) for x in re.findall(r"(\d+)[- ]?(?:channel|ch)(?![a-z])", text, re.I)]
        nums += [n for w, n in CHANNEL_WORDS.items() if re.search(rf"\b{w}\b", text, re.I)]
        if cond.value in nums:
            return OK
        return NO if nums else UNKNOWN
    return OK if re.search(cond.evidence, text, re.I if cond.label != "CAN" else 0) else UNKNOWN


def score(conds: list[Condition], part: dict) -> tuple[int, dict]:
    """(✓ 수 − ✗ 수, {조건 이름: 판정})."""
    checks = {c.label: check(c, part) for c in conds}
    return sum(1 for v in checks.values() if v == OK) - sum(1 for v in checks.values() if v == NO), checks


def rank(conds: list[Condition], parts: list[dict]) -> list[dict]:
    """조건 점수가 높은 순(같으면 원래 검색 순서). 각 부품에 checks 를 붙인다."""
    scored = []
    for i, p in enumerate(parts):
        s, checks = score(conds, p)
        scored.append((-s, i, {**p, "checks": checks}))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [p for _, _, p in scored]
