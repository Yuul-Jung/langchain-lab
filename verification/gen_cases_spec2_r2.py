#!/usr/bin/env python3
"""명세 2 2라운드 사례 생성기(결정적, 지어낸 값, 엔진을 쓰지 않음): 1c(R7)·1d(abs_max 위임 값, 설명용)·P(쌍별 덮기).

정의는 static_data/verification/spec2_round2.md. 모든 숫자는 Decimal(문자열). 정답 라벨은 저장하지 않는다(비교 때 고정 오라클로 재계산).
출력: data/verification/spec2-r2-{practice,sealed}.jsonl (입력만; 이 PC 전용). 사용: python3 verification/gen_cases_spec2_r2.py
"""
from __future__ import annotations

import hashlib
import itertools
import json
import random
import sys
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gen_cases_spec2 import BANDS, GRADES, S, EPS, limits, base  # noqa: E402

OUT = HERE.parent / "data" / "verification"
PHRASE = "spec2-profile-split-v2"
OLD_SEALED = {"high-industrial", "mid-automotive", "low-industrial", "high-automotive"}  # 1라운드 봉인(은퇴): 풀에서 제외
PROFILES = [f"{b}-{g}" for b in BANDS for g in GRADES]


def split():
    pool = [p for p in PROFILES if p not in OLD_SEALED]  # 한 번도 봉인이 아니었던 8개
    order = sorted(pool, key=lambda p: hashlib.sha256(f"{PHRASE}|{p}".encode()).hexdigest())
    sealed = set(order[:4])
    return sealed, order


EV_SUP = ["none", "ds_only", "dist_only", "lib_only", "ds_eq_dist", "ds_ne_dist", "dist_conflict", "delegated"]
EV_ABS = ["none", "ds_only", "dist_only", "lib_only", "dist_conflict"]  # 제외 쌍: 위임·일치·불일치 × abs_max
V_POS = ["below_min", "at_min", "inside", "at_max", "max_to_abs", "at_abs", "above_abs"]
T_POS = ["below", "at_min", "inside", "at_max", "above"]
PARAMS = ["s_min", "s_max", "s_abs", "t_min", "t_max", "v_pos", "t_pos"]
LEVELS = {"s_min": EV_SUP, "s_max": EV_SUP, "s_abs": EV_ABS, "t_min": EV_SUP, "t_max": EV_SUP, "v_pos": V_POS, "t_pos": T_POS}
SUPPLY_FIELDS, TEMP_FIELDS = {"s_min", "s_max", "s_abs"}, {"t_min", "t_max"}


def required_pairs():
    """덮을 쌍. 제외: 온도 필드 상태 × 전원 위치, 전원 필드 상태 × 온도 위치(서로 다른 입력)."""
    pairs = set()
    for a, b in itertools.combinations(PARAMS, 2):
        if (a in TEMP_FIELDS and b == "v_pos") or (a in SUPPLY_FIELDS and b == "t_pos"):
            continue
        for x in LEVELS[a]:
            for y in LEVELS[b]:
                pairs.add((a, x, b, y))
    return pairs


def covered_by(row):
    out = set()
    for a, b in itertools.combinations(PARAMS, 2):
        out.add((a, row[a], b, row[b]))
    return out


def pairwise_rows(seed="spec2-pairwise-r2"):
    """탐욕 쌍별 덮기(고정 씨앗). 반환 (행 목록, 제외한 쌍 수)."""
    rng = random.Random(seed)
    req = required_pairs()
    left = set(req)
    rows = []
    while left:
        best, best_n = None, -1
        for _ in range(400):
            row = {p: rng.choice(LEVELS[p]) for p in PARAMS}
            n = len(covered_by(row) & left)
            if n > best_n:
                best, best_n = row, n
        # 후보가 덜 덮으면 남은 쌍 하나를 강제로 넣어 진행을 보장
        a, x, b, y = sorted(left)[0]
        if best_n == 0:
            best = {p: rng.choice(LEVELS[p]) for p in PARAMS}
            best[a], best[b] = x, y
        rows.append(best)
        left -= covered_by(best)
    all_pairs = sum(len(LEVELS[a]) * len(LEVELS[b]) for a, b in itertools.combinations(PARAMS, 2))
    return rows, all_pairs - len(req)


def ev_values(state, true, delta):
    return {"none": [], "ds_only": [("datasheet", S(true))], "dist_only": [("distributor", S(true))], "lib_only": [("library", S(true))],
            "ds_eq_dist": [("datasheet", S(true)), ("distributor", S(true))], "ds_ne_dist": [("datasheet", S(true)), ("distributor", S(true + delta))],
            "dist_conflict": [("distributor", S(true)), ("distributor", S(true + EPS))], "delegated": [("delegated", S(true))]}[state]


def pair_case(profile, row):
    mn, mx, ab, tmin, tmax = limits(profile, "nominal")
    delta = (mx - mn) * D("0.1")
    f = {"supply_min_v": ev_values(row["s_min"], mn, delta), "supply_max_v": ev_values(row["s_max"], mx, delta), "abs_max_supply_v": ev_values(row["s_abs"], ab, delta),
         "temp_min_c": ev_values(row["t_min"], tmin, D("5")), "temp_max_c": ev_values(row["t_max"], tmax, D("5"))}
    v = {"below_min": mn - EPS, "at_min": mn, "inside": (mn + mx) / 2, "at_max": mx, "max_to_abs": (mx + ab) / 2, "at_abs": ab, "above_abs": ab + EPS}[row["v_pos"]]
    lo, hi = tmin + 10, tmax - 10
    lo, hi = {"below": (tmin - 1, hi), "at_min": (tmin, hi), "inside": (lo, hi), "at_max": (lo, tmax), "above": (lo, tmax + 1)}[row["t_pos"]]
    return f, v, (lo, hi)


def cases_for(profile, prows):
    out = []
    for width in ("nominal", "narrow"):
        mn, mx, ab, tmin, tmax = limits(profile, width)
        ta = (tmin + 10, tmax - 10)
        # 1c: R7 — 권장 안 × abs_max 없음 → 판정 불가
        for vname, v in (("at_min", mn), ("inside", (mn + mx) / 2), ("at_max", mx)):
            for src in ("datasheet", "distributor"):
                f = base(mn, mx, ab, tmin, tmax)
                f["abs_max_supply_v"] = []
                f["supply_min_v"] = [(src, S(mn))]
                out.append(("1c", {"width": width, "v_pos": vname, "min_src": src}, f, v, ta))
        # 1d(설명용): abs_max 가 위임 확인 값만 있음(R5: 받지 않음 → 없음 취급 → 판정 불가; 근거 약함)
        for vname, v in (("inside", (mn + mx) / 2), ("at_max", mx)):
            f = base(mn, mx, ab, tmin, tmax)
            f["abs_max_supply_v"] = [("delegated", S(ab))]
            out.append(("1d", {"width": width, "v_pos": vname}, f, v, ta))
    for i, row in enumerate(prows):
        f, v, ta = pair_case(profile, row)
        out.append(("P", {"row": i, **row}, f, v, ta))
    return out


def main():
    sealed, order = split()
    prows, excluded = pairwise_rows()
    left = required_pairs()
    for r in prows:
        left -= covered_by(r)
    rows = {"practice": [], "sealed": []}
    seen = set()
    for prof in PROFILES:
        if prof in OLD_SEALED:
            kind = "practice"  # 1라운드 봉인 프로필은 연습으로 취급(명세 2 §5 재생성)
        else:
            kind = "sealed" if prof in sealed else "practice"
        for cell, var, fields, v, ta in cases_for(prof, prows):
            key = json.dumps([prof, cell, {k: fields[k] for k in sorted(fields)}, S(v), [S(ta[0]), S(ta[1])]], sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            rows[kind].append({"id": f"{prof}:{cell}:{len(rows[kind]):04d}", "profile": prof, "cell": cell, "variant": var, "fields": fields, "v": S(v), "ta": [S(ta[0]), S(ta[1])]})
    OUT.mkdir(parents=True, exist_ok=True)
    print("고정 문구", PHRASE, "| 풀 8개 해시 순서:", order)
    print("봉인 4:", sorted(sealed), "| 쌍별 덮기 행", len(prows), "| 제외한 쌍", excluded, "| 덮이지 않은 필수 쌍", len(left))
    for kind, lst in rows.items():
        path = OUT / f"spec2-r2-{kind}.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in lst) + "\n", encoding="utf-8")
        cnt = {}
        for r in lst:
            cnt[r["cell"]] = cnt.get(r["cell"], 0) + 1
        print(kind, len(lst), "입력 sha256", hashlib.sha256(path.read_bytes()).hexdigest(), cnt)


if __name__ == "__main__":
    main()
