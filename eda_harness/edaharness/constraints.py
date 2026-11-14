"""부품 값 기록 -> 전기적 제약 -> 동작점 판정 (결정적, fail-closed).

부품 하나의 값은 여러 출처에서 올 수 있다. 값마다 출처와 신뢰 단계를 붙여 둔다.
  source = datasheet(제조사 데이터시트 원문) | distributor(유통사 API 값, 예: DigiKey) | library(심볼 라이브러리)
  신뢰 단계: datasheet > distributor > library
같은 필드에 여러 값이 있으면 가장 높은 단계의 값을 쓴다. 같은 단계 안에서 값이 다르면 고르지 않고
충돌(CONFLICT)로 판정한다 — 사람이 확인하기 전에는 그 필드를 제약으로 쓰지 않는다.

판정은 부품 이름을 보지 않는다. 필드 이름과 숫자만 본다(어떤 부품에도 같은 코드).
  - 근거 값이 없으면 ERROR(MISSING) — 통과로 치지 않는다.
  - datasheet 가 아닌 값으로 내린 판정은 WARN(UNVERIFIED_BASIS)을 함께 남긴다.
"""
from __future__ import annotations

SOURCES = {"datasheet": 3, "distributor": 2, "library": 1}
FIELDS = {
    "supply_min_v": "권장 전원 최소(V)",
    "supply_max_v": "권장 전원 최대(V)",
    "abs_max_supply_v": "절대 최대 전원(V)",
    "temp_min_c": "동작 온도 최소(°C)",
    "temp_max_c": "동작 온도 최대(°C)",
}
REL_TOL = 1e-6      # 같은 값으로 보는 허용 오차(표기 차이 4.5 vs 4.50)


class ConstraintError(Exception):
    pass


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def resolve(record: dict, field: str) -> dict:
    """record = {"values": {field: [{"value", "source", "ref"?}, ...]}} → 해결된 값 한 개.

    반환: {"status": "ok"|"missing"|"conflict", "value", "source", "candidates"}"""
    if field not in FIELDS:
        raise ConstraintError(f"알 수 없는 필드: {field}")
    cands = []
    for c in (record.get("values") or {}).get(field) or []:
        if not isinstance(c, dict) or not _num(c.get("value")) or c.get("source") not in SOURCES:
            raise ConstraintError(f"{field}: 값은 숫자 value 와 source({tuple(SOURCES)})가 있어야 함")
        cands.append(c)
    if not cands:
        return {"status": "missing", "value": None, "source": None, "candidates": []}
    top = max(SOURCES[c["source"]] for c in cands)
    best = [c for c in cands if SOURCES[c["source"]] == top]
    v0 = float(best[0]["value"])
    if any(abs(float(c["value"]) - v0) > REL_TOL * max(1.0, abs(v0)) for c in best[1:]):
        return {"status": "conflict", "value": None, "source": best[0]["source"], "candidates": best}
    return {"status": "ok", "value": v0, "source": best[0]["source"], "candidates": cands}


def disagreements(record: dict) -> list[dict]:
    """출처끼리 값이 다른 필드(단계가 달라도) — 오차 측정과 검토 목록용."""
    out = []
    for field in FIELDS:
        cands = (record.get("values") or {}).get(field) or []
        vals = {(c["source"], float(c["value"])) for c in cands if _num(c.get("value"))}
        if len({v for _, v in vals}) > 1:
            out.append({"field": field, "values": sorted(vals)})
    return out


def check_operating_point(record: dict, rail_v: float, temp_c: tuple[float, float] | None = None) -> list[dict]:
    """부품을 전원 rail_v(V), 주변 온도 범위 temp_c=(최저, 최고)에서 쓸 때의 판정 목록.

    각 항목: {"severity": ERROR|WARN, "code", "field", "msg"}. ERROR 가 없으면 이 조건에서 통과."""
    if not _num(rail_v) or rail_v < 0:
        raise ConstraintError("rail_v 는 0 이상의 숫자여야 함")
    out = []

    def need(field):
        r = resolve(record, field)
        if r["status"] == "missing":
            out.append({"severity": "ERROR", "code": "MISSING", "field": field,
                        "msg": f"{FIELDS[field]} 근거 값이 없어 판정할 수 없음"})
            return None
        if r["status"] == "conflict":
            out.append({"severity": "ERROR", "code": "CONFLICT", "field": field,
                        "msg": f"{FIELDS[field]}: 같은 신뢰 단계의 값이 서로 다름 → 사람 확인 필요"})
            return None
        if r["source"] != "datasheet":
            out.append({"severity": "WARN", "code": "UNVERIFIED_BASIS", "field": field,
                        "msg": f"{FIELDS[field]} = {r['value']:g} 은 {r['source']} 값(데이터시트 미확인)"})
        return r["value"]

    lo, hi, amax = need("supply_min_v"), need("supply_max_v"), need("abs_max_supply_v")
    if lo is not None and hi is not None and lo > hi:
        out.append({"severity": "ERROR", "code": "BAD_RANGE", "field": "supply_min_v",
                    "msg": f"권장 전원 범위가 뒤집힘({lo:g} > {hi:g})"})
    if amax is not None and rail_v > amax:
        out.append({"severity": "ERROR", "code": "ABS_MAX_EXCEEDED", "field": "abs_max_supply_v",
                    "msg": f"전원 {rail_v:g}V 가 절대 최대 {amax:g}V 를 넘음(손상 위험)"})
    if lo is not None and rail_v < lo:
        out.append({"severity": "ERROR", "code": "BELOW_RECOMMENDED", "field": "supply_min_v",
                    "msg": f"전원 {rail_v:g}V 가 권장 최소 {lo:g}V 보다 낮음"})
    if hi is not None and rail_v > hi:
        out.append({"severity": "ERROR", "code": "ABOVE_RECOMMENDED", "field": "supply_max_v",
                    "msg": f"전원 {rail_v:g}V 가 권장 최대 {hi:g}V 보다 높음"})
    if temp_c is not None:
        tmin, tmax = temp_c
        if not (_num(tmin) and _num(tmax)) or tmin > tmax:
            raise ConstraintError("temp_c 는 (최저, 최고) 숫자 쌍이어야 함")
        pmin, pmax = need("temp_min_c"), need("temp_max_c")
        if pmin is not None and tmin < pmin:
            out.append({"severity": "ERROR", "code": "TEMP_BELOW", "field": "temp_min_c",
                        "msg": f"주변 최저 {tmin:g}°C 가 부품 최소 {pmin:g}°C 보다 낮음"})
        if pmax is not None and tmax > pmax:
            out.append({"severity": "ERROR", "code": "TEMP_ABOVE", "field": "temp_max_c",
                        "msg": f"주변 최고 {tmax:g}°C 가 부품 최대 {pmax:g}°C 보다 높음"})
    return out


def passes(findings: list[dict]) -> bool:
    return not any(f["severity"] == "ERROR" for f in findings)
