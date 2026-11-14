"""데이터시트 원문에서 전기적 값 후보를 뽑는다 (인용·쪽수 포함, 결정적).

뽑는 값: 권장 전원 최소/최대(supply_min_v/supply_max_v), 절대 최대 전원(abs_max_supply_v),
동작 온도 최소/최대(temp_min_c/temp_max_c). 부품 이름은 보지 않고 표 머리·낱말 규칙만 쓴다.

자동으로 뽑은 값은 사람이 확인한 데이터시트 값이 아니다. 그래서 출처를 'extracted'로 둔다.
  - eda_harness constraints 에서는 유통사(distributor)와 같은 신뢰 단계로 다룬다 →
    둘이 같으면 그 값을 쓰고, 다르면 고르지 않고 충돌(CONFLICT)이 된다(서로 검산).
  - 사람이 인용문을 보고 확인하면 source 를 'datasheet'로 올린다(별도 승인 단계).
한 쪽에 같은 필드 후보가 여러 개면(등급별 표 등) 모두 남긴다 — 고르지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

NUM = r"[−–-]?\s?\d+(?:\.\d+)?"
DASH = r"[−–-]"
SUPPLY_LABEL = (r"(?:supply\s+voltage(?:\s+range)?|power\s+supply(?:\s+voltage)?|operating\s+supply\s+voltage|"
                r"\bV\s?CC\b|\bV\s?DD\b|\bV\s?S\b|\bV\+|\bVIN\b|input\s+voltage)")
ABS_HEAD = re.compile(r"absolute\s+maximum\s+ratings", re.I)
REC_HEAD = re.compile(r"recommended\s+operating\s+conditions|operating\s+conditions|electrical\s+characteristics|"
                      r"dc\s+characteristics", re.I)
TEMP_LABEL = re.compile(r"(?:operating(?:\s+free[- ]air)?\s+temperature(?:\s+range)?|ambient\s+temperature|\bT\s?A\b|TOPR)",
                        re.I)
# 'a to b V', 'a V to b V', 'a ~ b V'
RANGE_V = re.compile(rf"({NUM})\s?V?\s*(?:to|~|…|\.\.|{DASH}{{1}}(?=\s?\+?\d))\s*\+?({NUM})\s?V\b", re.I)
# 표 행: 라벨 뒤 MIN (TYP) MAX 숫자 + 단위 V
ROW_V = re.compile(rf"({NUM})\s+(?:({NUM})\s+)?({NUM})\s?V\b")
RANGE_C = re.compile(rf"({NUM})\s?°?\s?C?\s*(?:to|~|…|{DASH}(?=\s?\+?\d))\s*\+?({NUM})\s?°\s?C|({NUM})\s+({NUM})\s+°C",
                     re.I)
WINDOW = 140          # 라벨 뒤 몇 글자 안에서 값을 찾는지


def _f(s: str) -> float:
    return float(s.replace("−", "-").replace("–", "-").replace(" ", ""))


def _quote(text: str, a: int, b: int) -> str:
    return " ".join(text[max(0, a - 20):min(len(text), b + 20)].split())


def page_texts(path: Path) -> dict[int, str]:
    import document_pipeline as dp
    out: dict[int, str] = {}
    for s in dp.extract_sections(Path(path)):
        p = s.get("page")
        if p:
            out[p] = out.get(p, "") + "\n" + s["text"]
    return out


def candidates_from_pages(pages: dict[int, str], max_page: int | None = None) -> list[dict]:
    """쪽별 텍스트 → 후보 목록 [{field, value, page, quote, rule}]. 같은 값·같은 쪽 중복은 하나로."""
    out, seen = [], set()

    def add(field, value, page, quote, rule):
        key = (field, round(value, 4), page)
        if key not in seen:
            seen.add(key)
            out.append({"field": field, "value": value, "page": page, "quote": quote, "rule": rule})

    for page in sorted(pages):
        if max_page is not None and page > max_page:
            continue
        text = pages[page]
        # 절대 최대: 'Absolute Maximum Ratings' 머리 뒤 구간의 전원 라벨
        for h in ABS_HEAD.finditer(text):
            seg_end = h.end() + 1800
            for lab in re.finditer(SUPPLY_LABEL, text[h.end():seg_end], re.I):
                a = h.end() + lab.end()
                win = text[a:a + WINDOW]
                # 표 행 'MIN MAX 단위'(예: '-0.5 7 V'): 절대 최대는 두 번째(상한). 하한을 상한으로 읽지 않는다.
                m = re.match(rf"[^0-9−–-]{{0,40}}?({NUM})\s+\+?({NUM})\s?V\b", win)
                if m and _f(m.group(2)) > _f(m.group(1)) and _f(m.group(2)) > 1:
                    add("abs_max_supply_v", _f(m.group(2)), page, _quote(text, a, a + m.end()), "abs:row")
                    break
                m = RANGE_V.search(win[:60])
                if m and _f(m.group(2)) > _f(m.group(1)) and _f(m.group(2)) > 1:
                    add("abs_max_supply_v", _f(m.group(2)), page, _quote(text, a, a + m.end()), "abs:range")
                    break
                m = re.match(rf"[^0-9−–-]{{0,40}}?\+?({NUM})\s?V\b", win)
                if m and _f(m.group(1)) > 1:
                    add("abs_max_supply_v", _f(m.group(1)), page, _quote(text, a, a + m.end()), "abs:single")
                    break
        # 권장 범위: 권장 동작 조건·전기적 특성 머리가 있는 쪽의 전원 라벨 + MIN (TYP) MAX
        if REC_HEAD.search(text) or re.search(r"\bMIN\b.*\bMAX\b", text):
            for lab in re.finditer(SUPPLY_LABEL, text, re.I):
                before = text[max(0, lab.start() - 300):lab.start()]
                if ABS_HEAD.search(before):
                    continue                      # 절대 최대 표 안의 행은 권장 범위가 아님
                win = text[lab.end():lab.end() + WINDOW]
                m = RANGE_V.search(win[:60])
                if m:
                    lo, hi = _f(m.group(1)), _f(m.group(2))
                else:
                    m = ROW_V.search(win[:80])
                    if not m:
                        continue
                    lo, hi = _f(m.group(1)), _f(m.group(3))
                if 0 < lo < hi <= 100:
                    q = _quote(text, lab.start(), lab.end() + m.end())
                    add("supply_min_v", lo, page, q, "rec:row")
                    add("supply_max_v", hi, page, q, "rec:row")
        # 동작 온도
        for lab in TEMP_LABEL.finditer(text):
            win = text[lab.end():lab.end() + WINDOW]
            m = RANGE_C.search(win)
            if not m:
                continue
            lo, hi = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            lo, hi = _f(lo), _f(hi)
            if -80 <= lo < hi <= 200:
                q = _quote(text, lab.start(), lab.end() + m.end())
                add("temp_min_c", lo, page, q, "temp")
                add("temp_max_c", hi, page, q, "temp")
    return out


def evidence(path: Path, ref: str | None = None) -> dict:
    """constraints 입력 형식: {"values": {field: [{"value", "source": "extracted", "ref", "page", "quote"}]}}."""
    vals: dict[str, list] = {}
    for c in candidates_from_pages(page_texts(path)):
        vals.setdefault(c["field"], []).append({"value": c["value"], "source": "extracted", "ref": ref or Path(path).name,
                                                "page": c["page"], "quote": c["quote"]})
    return {"values": vals}
