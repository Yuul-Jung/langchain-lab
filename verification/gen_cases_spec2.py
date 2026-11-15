#!/usr/bin/env python3
"""명세 2 위험 칸 6개(1a·1b·2·3·4·5)의 사례 생성기 (결정적, 지어낸 값, 엔진을 쓰지 않음).

정의는 static_data/verification/spec2_cell_plan.md (2판) 를 따른다. 모든 숫자는 Decimal(문자열).
출력: data/verification/spec2-risk-{practice,sealed}.jsonl (이 PC 전용, 커밋하지 않음). 정답은 오라클(oracle_constraints.py)이 계산.
사용: python3 verification/gen_cases_spec2.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from oracle_constraints import judge  # noqa: E402

OUT = HERE.parent / "data" / "verification"
BANDS = {"low": (D("1.62"), D("1.98"), D("2.5")), "mid": (D("3.0"), D("5.5"), D("6.5")), "high": (D("9"), D("36"), D("40"))}
GRADES = {"commercial": (D("0"), D("70")), "industrial": (D("-40"), D("85")), "automotive": (D("-40"), D("125")), "military": (D("-55"), D("125"))}
SEALED = {"high-industrial", "mid-automotive", "low-industrial", "high-automotive"}  # spec2_cell_plan.md 분할 결과
EPS = D("0.01")
S = lambda x: str(x)  # noqa: E731


def limits(profile: str, width: str):
    band, grade = profile.split("-")
    mn, mx, ab = BANDS[band]
    tmin, tmax = GRADES[grade]
    if width == "narrow":  # 권장 폭을 안쪽으로 5%(전원), 10 °C(온도)
        span = mx - mn
        mn, mx = mn + span * D("0.05"), mx - span * D("0.05")
        tmin, tmax = tmin + 10, tmax - 10
    return mn, mx, ab, tmin, tmax


def base(mn, mx, ab, tmin, tmax):
    return {"supply_min_v": [("datasheet", S(mn))], "supply_max_v": [("datasheet", S(mx))], "abs_max_supply_v": [("datasheet", S(ab))],
            "temp_min_c": [("datasheet", S(tmin))], "temp_max_c": [("datasheet", S(tmax))]}


def cases_for(profile: str):
    out = []
    for width in ("nominal", "narrow"):
        mn, mx, ab, tmin, tmax = limits(profile, width)
        ta = (tmin + 10, tmax - 10)
        mid_v = (mn + mx) / 2
        # 1a: abs_max 없음/유통사만 × 절대 최대 초과, supply_max 확정
        for state in ("none", "distributor"):
            for dname, d in (("eps", EPS), ("x0.1", ab * D("0.1")), ("x0.5", ab * D("0.5"))):
                f = base(mn, mx, ab, tmin, tmax)
                f["abs_max_supply_v"] = [] if state == "none" else [("distributor", S(ab))]
                out.append(("1a", {"width": width, "abs_state": state, "excess": dname}, f, ab + d, ta))
        # 1b: abs_max 없음 × supply_max 없음, V 는 절대 최대 초과
        for src in ("datasheet", "distributor"):
            for dname, d in (("eps", EPS), ("x0.1", ab * D("0.1")), ("x0.5", ab * D("0.5"))):
                f = base(mn, mx, ab, tmin, tmax)
                f["abs_max_supply_v"] = []
                f["supply_max_v"] = []
                f["supply_min_v"] = [(src, S(mn))]
                out.append(("1b", {"width": width, "min_src": src, "excess": dname}, f, ab + d, ta))
    # 2: 전원 필드 같은 단계 충돌 × 전원 위치 7 (폭 nominal 고정)
    mn, mx, ab, tmin, tmax = limits(profile, "nominal")
    pos = {"below_min": mn - EPS, "at_min": mn, "inside": (mn + mx) / 2, "at_max": mx, "max_to_abs": (mx + ab) / 2, "at_abs": ab, "above_abs": ab + EPS}
    for fld in ("supply_min_v", "supply_max_v", "abs_max_supply_v"):
        true = {"supply_min_v": mn, "supply_max_v": mx, "abs_max_supply_v": ab}[fld]
        for pname, v in pos.items():
            f = base(mn, mx, ab, tmin, tmax)
            f[fld] = [("distributor", S(true)), ("distributor", S(true + EPS))]  # 같은 단계(유통사) 값이 다름 → 충돌(데이터시트 없음)
            out.append(("2", {"conflict_field": fld, "position": pname}, f, v, (tmin + 10, tmax - 10)))
    # 3: 위임 확인 × 권장 범위 밖
    for width in ("nominal", "narrow"):
        mn, mx, ab, tmin, tmax = limits(profile, width)
        ta = (tmin + 10, tmax - 10)
        mid_v = (mn + mx) / 2
        for fld in ("supply_min_v", "supply_max_v", "temp_min_c", "temp_max_c"):
            for deg, k in (("small", D("1")), ("large", D("5"))):
                f = base(mn, mx, ab, tmin, tmax)
                v, t = mid_v, ta
                true = {"supply_min_v": mn, "supply_max_v": mx, "temp_min_c": tmin, "temp_max_c": tmax}[fld]
                f[fld] = [("delegated", S(true))]
                if fld == "supply_min_v": v = mn - EPS * k
                elif fld == "supply_max_v": v = mx + EPS * k
                elif fld == "temp_min_c": t = (tmin - k, ta[1])
                else: t = (ta[0], tmax + k)
                out.append(("3", {"width": width, "delegated_field": fld, "degree": deg}, f, v, t))
    # 4: 데이터시트≠유통사 × 경계 (데이터시트가 이김)
    mn, mx, ab, tmin, tmax = limits(profile, "nominal")
    for edge, true in (("min", mn), ("max", mx)):
        for off_name, off in (("minus_eps", -EPS), ("at", D(0)), ("plus_eps", EPS)):
            for dist in ("wider", "narrower"):
                f = base(mn, mx, ab, tmin, tmax)
                delta = (mx - mn) * D("0.1")
                if edge == "min":
                    dv = true - delta if dist == "wider" else true + delta
                    f["supply_min_v"] = [("datasheet", S(true)), ("distributor", S(dv))]
                else:
                    dv = true + delta if dist == "wider" else true - delta
                    f["supply_max_v"] = [("datasheet", S(true)), ("distributor", S(dv))]
                out.append(("4", {"edge": edge, "offset": off_name, "distributor": dist}, f, true + off, (tmin + 10, tmax - 10)))
    # 5: 온도 한쪽만 있음 × 없는 쪽 방향으로 벗어난 동작점
    for width in ("nominal", "narrow"):
        mn, mx, ab, tmin, tmax = limits(profile, width)
        for side in ("min", "max"):
            for deg, k in (("1C", D("1")), ("5C", D("5")), ("20C", D("20"))):
                f = base(mn, mx, ab, tmin, tmax)
                if side == "min":
                    f["temp_min_c"] = []
                    t = (tmin - k, tmax - 10)
                else:
                    f["temp_max_c"] = []
                    t = (tmin + 10, tmax + k)
                out.append(("5", {"width": width, "missing_side": side, "degree": deg}, f, (mn + mx) / 2, t))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = {"practice": [], "sealed": []}
    seen = set()
    for band in BANDS:
        for grade in GRADES:
            prof = f"{band}-{grade}"
            split = "sealed" if prof in SEALED else "practice"
            for cell, var, fields, v, ta in cases_for(prof):
                key = json.dumps([prof, cell, var, {k: fields[k] for k in sorted(fields)}, S(v), [S(ta[0]), S(ta[1])]], sort_keys=True)
                if key in seen:
                    continue  # 중복(프로필·칸·변형·값이 모두 같음) 제외
                seen.add(key)
                case = {"fields": fields, "v": S(v), "ta": [S(ta[0]), S(ta[1])]}
                res, warns, why = judge(case)
                rows[split].append({"id": f"{prof}:{cell}:{len(rows[split]):04d}", "profile": prof, "cell": cell, "variant": var, **case,
                                    "oracle": {"verdict": res, "warnings": sorted(warns), "violation": sorted(why["violation"]), "unknown": sorted(why["unknown"])}})
    for split, lst in rows.items():
        path = OUT / f"spec2-risk-{split}.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in lst) + "\n", encoding="utf-8")
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        cnt = {}
        paths = {}
        for r in lst:
            cnt[r["cell"]] = cnt.get(r["cell"], 0) + 1
            paths.setdefault(r["cell"], set()).add((r["oracle"]["verdict"], tuple(r["oracle"]["violation"]), tuple(r["oracle"]["unknown"])))
        print(split, len(lst), "sha256", h)
        for c in sorted(cnt):
            print("  칸", c, "사례", cnt[c], "서로 다른 규칙 경로(판정·이유 조합)", len(paths[c]))


if __name__ == "__main__":
    main()
