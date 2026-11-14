"""신뢰할 수 있는 부품 기록(S2): 값마다 출처·단위·조건·신뢰도를 붙이고, 출처끼리 다르면 자동으로 고르지 않는다.

한 값(Evidence):
  {"value": 원래 글자, "unit": "V"|"°C"|"pins"|None, "min": 수, "typ": 수, "max": 수, "conditions": 글자,
   "source": "datasheet"|"digikey"|"kicad", "source_ref": 출처 식별(쪽·MPN·lib_id), "retrieved_at": 날짜,
   "confidence": 0~1, "basis_rank": 3(datasheet) > 2(distributor=digikey) > 1(library=kicad)}
한 항목(Field): {"evidence": [Evidence...], "status": "agreed"|"single"|"conflict"|"unknown", "chosen": Evidence|None}
  - agreed: 출처 둘 이상이 허용 오차 안에서 같음 → chosen 은 basis_rank 가 가장 높은 것
  - single: 출처 하나뿐 → chosen 그 값(신뢰도는 출처 등급에 따름)
  - conflict: 출처끼리 다름 → chosen 없음(proposed — 사람이나 위임 검토가 정한다). 자동으로 고르지 않는다.
모든 부품에 같은 구조(특정 부품에 맞춘 규칙 없음). S3(전기적 제약)는 chosen 과 basis_rank 만 쓴다.
"""
from __future__ import annotations

import re

BASIS_RANK = {"datasheet": 3, "digikey": 2, "kicad": 1}
FIELDS = ("pin_count", "package", "supply_voltage", "operating_temperature", "category")
TOLERANCE = {"V": 0.05, "°C": 1.0, "pins": 0.0}          # 같은 값으로 보는 차이(전압은 비율, 온도는 °C, 핀은 0)

PACKAGE_FAMILIES = ["SOT-23", "SOT-223", "SOT-89", "SOT-363", "SC-70", "TO-220", "TO-92", "TO-263", "TO-252", "TO-3",
                    "PDIP", "DIP", "SOIC", "SSOP", "TSSOP", "MSOP", "VSSOP", "QFN", "VQFN", "WQFN", "DFN", "LQFP", "TQFP",
                    "QFP", "BGA", "LGA", "SON", "SOP", "PLCC", "ZIP", "SIP"]


def evidence(source, value, source_ref, retrieved_at, unit=None, lo=None, typ=None, hi=None, conditions="", confidence=None):
    return {"value": value, "unit": unit, "min": lo, "typ": typ, "max": hi, "conditions": conditions, "source": source,
            "source_ref": source_ref, "retrieved_at": retrieved_at,
            "confidence": confidence if confidence is not None else {3: 0.9, 2: 0.7, 1: 0.5}[BASIS_RANK[source]],
            "basis_rank": BASIS_RANK[source]}


# ---------- 글자 → 값 ----------
def parse_range(text: str, unit: str) -> tuple[float | None, float | None]:
    """'1.8V ~ 5.5V', '-40°C ~ 85°C (TA)', '2.7 V to 5.5 V', '3.3V' → (min, max)."""
    if not text or text.strip() in ("-", ""):
        return None, None
    u = re.escape(unit)
    nums = [float(x) for x in re.findall(rf"([-+]?\d+(?:\.\d+)?)\s*{u}", text)]
    if not nums:
        nums = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", text)]
    if not nums:
        return None, None
    return (min(nums), max(nums)) if len(nums) > 1 else (nums[0], nums[0])


def package_family(text: str) -> str | None:
    t = (text or "").upper().replace("_", "-")
    for fam in sorted(PACKAGE_FAMILIES, key=len, reverse=True):
        if re.search(r"(?<![A-Z])" + re.escape(fam).replace(r"\-", "-?") + r"(?![A-Z])", t):
            return {"PDIP": "DIP", "VQFN": "QFN", "WQFN": "QFN", "VSSOP": "MSOP"}.get(fam, fam)
    return None


def pins_from_package(text: str) -> int | None:
    """'8-SOIC (0.154", 3.90mm Width)' → 8, 'SOT-23-5' → 5, 'TO-220-3' → 3."""
    t = text or ""
    m = re.match(r"\s*(\d{1,3})-", t)
    if m:
        return int(m.group(1))
    tail = re.findall(r"-(\d{1,3})(?![\d.])", t)      # 'SOT-23-5' 는 마지막 '-5' 가 핀 수
    return int(tail[-1]) if len(tail) >= 2 or (tail and not re.search(r"SOT|TO|SC", t.upper())) else None


# ---------- 판정 ----------
def _same(a: dict, b: dict) -> bool:
    if a["unit"] in ("V", "°C"):
        if None in (a["min"], a["max"], b["min"], b["max"]):
            return False
        tol = TOLERANCE[a["unit"]]
        close = (lambda x, y: abs(x - y) <= tol * max(abs(x), abs(y), 1)) if a["unit"] == "V" else (lambda x, y: abs(x - y) <= tol)
        return close(a["min"], b["min"]) and close(a["max"], b["max"])
    if a["unit"] == "pins":
        return a["typ"] == b["typ"]
    return str(a["value"]).strip().upper() == str(b["value"]).strip().upper()


def resolve(evs: list[dict]) -> dict:
    evs = [e for e in evs if e and (e["value"] not in (None, "", "-"))]
    if not evs:
        return {"evidence": [], "status": "unknown", "chosen": None}
    if len(evs) == 1:
        return {"evidence": evs, "status": "single", "chosen": evs[0]}
    base = max(evs, key=lambda e: e["basis_rank"])
    if all(_same(base, e) for e in evs):
        return {"evidence": evs, "status": "agreed", "chosen": base}
    return {"evidence": evs, "status": "conflict", "chosen": None}      # proposed: 자동으로 고르지 않는다


# ---------- S3(eda_harness constraints) 입력으로 바꾸기 ----------
S3_SOURCE = {"datasheet": "datasheet", "digikey": "distributor", "kicad": "library"}


def to_constraint_record(rec: dict) -> dict:
    """부품 기록 → eda_harness constraints 입력 {"values": {field: [{"value", "source", "ref"}]}}.
    순위 매기기는 S3 가 한 번만 하도록, chosen 이 아니라 모든 근거를 출처와 함께 넘긴다(충돌도 그대로 전달)."""
    values: dict[str, list] = {}

    def add(field, value, ev):
        if value is not None:
            values.setdefault(field, []).append({"value": value, "source": S3_SOURCE[ev["source"]], "ref": ev["source_ref"]})
    for ev in rec["fields"].get("supply_voltage", {}).get("evidence", []):
        add("supply_min_v", ev["min"], ev); add("supply_max_v", ev["max"], ev)
    for ev in rec["fields"].get("abs_max_supply", {}).get("evidence", []):
        add("abs_max_supply_v", ev["max"], ev)
    for ev in rec["fields"].get("operating_temperature", {}).get("evidence", []):
        add("temp_min_c", ev["min"], ev); add("temp_max_c", ev["max"], ev)
    return {"lib_id": rec.get("lib_id"), "values": values}
