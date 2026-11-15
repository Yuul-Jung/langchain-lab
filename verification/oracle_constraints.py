"""명세 2 표 오라클: 규칙 문장(static_data/verification/spec2_rules.md R1~R9)만으로 판정한다.

엔진(edaharness, constraints.py)을 import 하지 않는다(test_oracle_constraints.py 가 AST 로 점검한다).
입력의 값은 모두 지어낸 것이어야 한다(실제 부품 값 금지).
값 = (단계, 숫자). 단계: human, delegated, datasheet, distributor, library.
결과 = (판정, 경고 집합, 이유) — 판정은 'violation' | 'unknown' | 'pass'. 이유 = {"violation": 경계 집합, "unknown": 경계 집합}.
숫자는 int/Decimal/문자열만 받아 Decimal 로 비교한다(float 거부: 경계값을 부동소수로 만들지 않기 위해).
"""
from __future__ import annotations

from decimal import Decimal

# R1: 높을수록 우선. 사람·위임 확인은 데이터시트 단계의 값이다.
_RANK = {"human": 3, "delegated": 3, "datasheet": 3, "distributor": 2, "library": 1}
_REL_TOL = Decimal("1e-6")  # R2 3판
FIELDS = ("supply_min_v", "supply_max_v", "abs_max_supply_v", "temp_min_c", "temp_max_c")
VIOLATION, UNKNOWN, PASS = "violation", "unknown", "pass"


def _num(x) -> Decimal:
    if isinstance(x, bool) or isinstance(x, float):
        raise ValueError(f"float/bool 숫자 금지(문자열·int·Decimal 사용): {x!r}")
    try:
        d = Decimal(str(x))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"숫자가 아님: {x!r}") from e
    if not d.is_finite():  # NaN·Infinity 는 비교가 항상 거짓이라 위험한 통과가 될 수 있음
        raise ValueError(f"유한한 숫자가 아님: {x!r}")
    return d


def resolve_field(name: str, values: list[tuple[str, float]]) -> tuple[str, Decimal | None, set[str]]:
    """필드 확정. 반환 (상태, 값, 경고). 상태: 'value' | 'none' | 'conflict'."""
    warns: set[str] = set()
    vals = []
    for tier, num in values:
        if tier not in _RANK:
            raise ValueError(f"알 수 없는 출처 단계: {tier}")  # 'extracted' 등은 입력 오류
        if name == "abs_max_supply_v" and tier == "delegated":
            continue  # R5: 절대 최대는 위임 확인 값을 받지 않는다(없음 취급)
        vals.append((tier, _num(num)))
    if not vals:
        return "none", None, warns
    top = max(_RANK[t] for t, _ in vals)
    top_nums = [n for t, n in vals if _RANK[t] == top]
    if any(t == "delegated" and _RANK[t] == top for t, _ in vals):
        warns.add("DELEGATED_CONFIRMATION")  # R5
    lo, hi = min(top_nums), max(top_nums)  # R2(3판): 대칭 규칙, 순서 무관
    scale = max(Decimal(1), max(abs(n) for n in top_nums))
    if hi - lo > _REL_TOL * scale:
        return "conflict", None, warns
    # 확정 값: 위험 방향으로 보수적(하한 필드는 최대, 상한 필드는 최소)
    return "value", (hi if name in ("supply_min_v", "temp_min_c") else lo), warns  # R3: 낮은 단계 값은 무시


def judge(case: dict) -> tuple[str, set[str], dict[str, set[str]]]:
    """case = {'fields': {필드: [(단계, 숫자), ...]}, 'v': 전압, 'ta': (Ta_lo, Ta_hi)}."""
    f, warns = {}, set()
    for name in FIELDS:
        st, val, w = resolve_field(name, case["fields"].get(name, []))
        f[name] = (st, val)
        warns |= w
    if case.get("v") is None or case.get("ta") is None:  # R0
        raise ValueError("동작점 V·Ta 가 없음")
    v = _num(case["v"])
    ta_lo, ta_hi = _num(case["ta"][0]), _num(case["ta"][1])
    if ta_lo > ta_hi:
        raise ValueError("Ta_lo > Ta_hi")
    viol: set[str] = set()
    unk: set[str] = set()

    def edge(name: str, bad) -> None:  # 경계별 판정(R6·R8): 값이 있으면 비교, 없음/충돌이면 판정 불가
        st, val = f[name]
        if st != "value":
            unk.add(name)
        elif bad(val):
            viol.add(name)

    edge("supply_min_v", lambda x: v < x)
    edge("supply_max_v", lambda x: v > x)
    edge("abs_max_supply_v", lambda x: v > x)
    edge("temp_min_c", lambda x: ta_lo < x)
    edge("temp_max_c", lambda x: ta_hi > x)
    why = {"violation": viol, "unknown": unk}
    if viol:  # R9: 위반 > 판정 불가 > 통과
        return VIOLATION, warns, why
    return (UNKNOWN if unk else PASS), warns, why
