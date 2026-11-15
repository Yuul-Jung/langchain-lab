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


# ---- 기준 부품 고정(PARTS_ANCHOR_LOCK)에서만 쓰는 '분명히 어긋남' 판정. 위의 check·rank(서비스의 조건 표시)는 건드리지 않는다.
SMD_WORDS = (r"(?<![A-Za-z])(?:SOT-?\d+|SOIC|SOP|SSOP|TSSOP|MSOP|QFN|DFN|BGA|LGA|LQFP|TQFP|QFP|SOD-?\d+|DPAK|D2PAK|TO-?252|TO-?263|WLCSP|SC-?70|SMD|SMT)"
             r"|표면\s*실장")
THT_WORDS = r"(?<![A-Za-z])(?:P?DIP|SIP|TO-?92|TO-?220|TO-?247|TO-?126|TO-?3(?!\d)|TO-?99|DO-?35|DO-?41|THT)|through[- ]?hole|axial|radial|스루\s*홀"
MOUNT = {"표면 실장": (SMD_WORDS, THT_WORDS), "스루홀": (THT_WORDS, SMD_WORDS)}


def parse_mount(question: str) -> list[Condition]:
    """실장 형태 조건(표면 실장·스루홀). 둘 다 있거나 없으면 빈 목록."""
    smd = re.search(r"(?<![A-Za-z])(?:SMD|SMT)(?![A-Za-z])|표면\s*실장", question, re.I)
    tht = re.search(r"스루\s*홀|쓰루\s*홀|through[- ]?hole|(?<![A-Za-z])THT(?![A-Za-z])|삽입\s*실장|삽입형|브레드\s*보드", question, re.I)
    if bool(smd) == bool(tht):
        return []
    label = "표면 실장" if smd else "스루홀"
    return [Condition("mount", label, MOUNT[label][0])]


def _lock_text(part: dict) -> str:
    return " ".join(str(part.get(k) or "") for k in ("name", "description", "keywords", "footprint", "footprint_filters"))


SAME_PACKAGE = [{"SOP", "SOIC"}, {"DIP"}]         # 같은 것으로 보는 패키지 이름(SOP 와 SOIC 는 같은 계열로 부른다)
# 후보의 글에서 '다른 패키지'로 알아볼 이름(질문에서 조건으로 뽑는 PACKAGES 보다 넓다. 서비스의 조건 표시는 PACKAGES 만 쓴다)
KNOWN_PACKAGES = PACKAGES + ["TSOP", "SSOP", "VSSOP", "QSOP", "QFP", "LGA", "PLCC", "SON", "WLCSP", "SIP", "TO-247", "TO-252", "TO-263", "TO-3",
                             "SOD-123", "SOD-323", "DO-41", "DO-35", "SC-70"]
SUPPLY_WORDS = re.compile(r"전원|동작|입력|구동|공급|에서\s*(?:쓸|쓰|사용|돌)|supply|operat|input|vcc|vdd|logic|로직", re.I)


def is_supply_voltage(question: str) -> bool:
    """질문의 전압이 전원·동작 전압이라고 밝혔는가(출력·기준 전압이면 후보를 거르는 데 쓰지 않는다)."""
    return bool(SUPPLY_WORDS.search(question)) and not re.search(r"출력|기준\s*전압|output|reference", question, re.I)


def _package_re(name: str) -> str:
    return r"(?<![A-Za-z])" + ("P?DIP" if name == "DIP" else re.escape(name).replace(r"\-", "[-_ ]?"))


def contradicts(cond: Condition, part: dict) -> bool:
    """후보의 글이 조건과 어긋나는 값을 분명히 적고 있는가. 적혀 있지 않으면(알 수 없으면) False."""
    text = _lock_text(part)
    if cond.family == "package":
        same = next((g for g in SAME_PACKAGE if cond.label in g), {cond.label})
        if any(re.search(_package_re(p), text, re.I) for p in same):
            return False
        return any(re.search(_package_re(p), text, re.I) for p in KNOWN_PACKAGES if p not in same)
    if cond.family == "mount":
        mine, other = MOUNT[cond.label]
        return not re.search(mine, text, re.I) and bool(re.search(other, text, re.I))
    if cond.family == "voltage":
        ranges, singles = _voltages(text)
        if any(abs(x - cond.value) < 1e-6 for x in singles) or any(lo - 1e-6 <= cond.value <= hi + 1e-6 for lo, hi in ranges):
            return False                    # 글에 그 값이 그대로 있거나 범위 안이면 어긋남이 아니다
        return bool(ranges)                 # 범위가 적혀 있는데 그 밖일 때만 어긋남
    return False


# ---- 패키지의 핀 수 (3차 판정: QFN-28 을 물었는데 QFN-36·48 을 답한 것이 '조건과 어긋남'의 대부분이었다)
PIN_FAMILIES = ("DIP", "SOIC", "SOP", "TSSOP", "MSOP", "QFN", "DFN", "BGA", "LQFP", "TQFP")


def package_pins(text: str, label: str) -> set[int]:
    """글에 그 패키지 이름과 함께 적힌 핀 수(QFN-28 → 28, SOT-23-6 → 6). 크기 표기(3.9x4.9mm)나 노출 패드(1EP)는 핀 수로 읽지 않는다."""
    if label == "SOT-23":
        return {int(x) for x in re.findall(r"(?<![A-Za-z])SOT[-_ ]?23[-_ ]?(\d)(?!\d)", text, re.I)}
    if label not in PIN_FAMILIES:
        return set()
    family = "P?DIP" if label == "DIP" else ("(?:SOP|SOIC)" if label in ("SOP", "SOIC") else re.escape(label))
    return {int(x) for x in re.findall(r"(?<![A-Za-z])" + family + r"[-_* ]{0,2}(\d{1,3})(?![\d.]|x|mm|ep)", text, re.I)}


def pin_mismatch(cond: Condition, question: str, part: dict) -> bool:
    """질문이 패키지의 핀 수까지 적었고 후보의 글에도 같은 패키지의 핀 수가 적혀 있는데 서로 다른가. 한쪽이라도 적혀 있지 않으면 False."""
    if cond.family != "package":
        return False
    want, have = package_pins(question, cond.label), package_pins(_lock_text(part), cond.label)
    return bool(want) and bool(have) and not (want & have)


# ---- 카탈로그(KiCad 라이브러리 값)로는 확인할 수 없는 조건: 후보를 거르는 데 쓰지 않고, 답에 확인하지 못했다고 밝힌다
UNVERIFIABLE = [
    (r"차량용|자동차용|전장용|오토모티브|automotive|AEC-?Q\d+", "차량용 등급"),
    (r"RoHS|무연|lead[- ]?free|할로겐\s*프리|REACH", "환경 규제 대응(RoHS 등)"),
    (r"산업용|industrial|군용|military|우주용|의료용|확장\s*온도|온도\s*등급", "사용 등급·온도 등급"),
    (r"(?:다른|같은|동일)\s*(?:회사|제조사|메이커|벤더|브랜드)|세컨드\s*소스|second\s+source|(?:another|different|same)\s+(?:vendor|manufacturer|maker|brand)", "제조사"),
    (r"핀\s*(?:투\s*핀|호환|배열(?:이|도)?\s*(?:같|동일))|pin[- ]?(?:to[- ]?pin|compatible)|drop-?in|그대로\s*(?:끼|꽂|교체|바꿔)|바꿔\s*끼", "핀 호환"),
    (r"가격|저렴|싼|값이|단가|cheap|low[- ]?cost|price", "가격"),
    (r"재고|수급|구하기\s*쉬운|납기|in\s+stock|availab|리드\s*타임|단종\s*아닌|양산\s*중", "재고·수급"),
]


def unverifiable(question: str) -> list[str]:
    """질문에 든, 카탈로그로는 확인할 수 없는 조건의 이름 목록."""
    return [label for pat, label in UNVERIFIABLE if re.search(pat, question, re.I)]


# ---- 비교 조건("X보다 전류를 더 많이", "higher voltage than X"): 기준 부품의 수치와 후보의 수치를 견준다 (기준 부품 고정에서만)
COMPARE_ATTRS = [("전류", r"전류|current|\bamps?\b", r"(\d+(?:\.\d+)?)\s*(m|u|µ|μ)?A(?![A-Za-z])", {"m": 1e-3, "u": 1e-6, "µ": 1e-6, "μ": 1e-6}),
                 ("전압", r"전압|내압|voltage", r"(\d+(?:\.\d+)?)\s*(m|k)?V(?![A-Za-z])", {"m": 1e-3, "k": 1e3})]
_MORE = r"더\s*(?:많|크|큰|높|세|센)|higher|more|larger|bigger|greater|(?:많이|크게|높게)|(?:큰|높은|센)\s"
_LESS = r"더\s*(?:적|작|낮)|lower|less|smaller|(?:적게|작게|낮게)|(?:작은|낮은)\s"


def parse_compare(question: str) -> dict | None:
    """질문의 비교 조건 {'attr': '전류'·'전압'·None(다루지 못하는 속성), 'more': True·False}. 비교 표현이 없으면 None."""
    m = re.search(r"보다|than", question, re.I)
    if not m:
        return None
    seg = question[max(0, m.start() - 30):m.end() + 40]
    more, less = re.search(_MORE, seg, re.I), re.search(_LESS, seg, re.I)
    if bool(more) == bool(less):
        return None
    attr = next((name for name, words, _rx, _mult in COMPARE_ATTRS if re.search(words, seg, re.I)), None)
    return {"attr": attr, "more": bool(more)}


def attr_value(part: dict, attr: str) -> float | None:
    """부품 설명에 적힌 그 속성의 가장 큰 수치(기본 단위). 없으면 None."""
    for name, _words, rx, mult in COMPARE_ATTRS:
        if name == attr:
            vals = [float(v) * mult.get(u, 1.0) for v, u in re.findall(rx, str(part.get("description") or ""))]
            return max(vals) if vals else None
    return None

