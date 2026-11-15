#!/usr/bin/env python3
"""탐색용 무작위 대조(봉인 아님): 오라클과 엔진을 무작위 입력으로 비교해 생성기가 덮지 못한 영역을 찾는다. 사용: python3 verification/fuzz_spec2.py [N] [seed]"""
import random, sys
from collections import Counter
from decimal import Decimal as D
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_spec2 as cmp
from oracle_constraints import judge

N = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
rng = random.Random(sys.argv[2] if len(sys.argv) > 2 else "fuzz-v1")
TIERS = ["datasheet", "distributor", "library", "delegated"]
FIELDS = ["supply_min_v", "supply_max_v", "abs_max_supply_v", "temp_min_c", "temp_max_c"]
TOL = len(sys.argv) > 3 and sys.argv[3] == "tol"  # 허용 폭 t 의 0.9·1.0·1.1 배 섭동, 값 3개 이상, 순서 임의
TINY = len(sys.argv) > 3 and sys.argv[3] == "tiny"  # ±1e-7 섭동 포함(R2 허용 오차 경계 탐색)
BASE = {"supply_min_v": D("3.0"), "supply_max_v": D("5.5"), "abs_max_supply_v": D("6.5"), "temp_min_c": D("-40"), "temp_max_c": D("85")}


def vals(field):
    n = rng.choice([2, 3, 3, 4]) if TOL else rng.choice([0, 0, 1, 1, 1, 2, 2, 3])
    out = []
    for _ in range(n):
        t = rng.choice(TIERS)
        if TOL:
            tt = D("0.000001") * max(D(1), abs(BASE[field]))
            v = BASE[field] + tt * rng.choice([D(0), D("0.9"), D("-0.9"), D("0.5"), D("1.1"), D("-1.1"), D("1")])
            out.append((rng.choice(TIERS[:2] if rng.random() < 0.7 else TIERS), str(v)))
            continue
        v = BASE[field] + rng.choice([D(0), D(0), D(0), D("0.01"), D("-0.01"), D("0.5"), D("-1"), D("1")] + ([D("0.0000001"), D("-0.0000001"), D("0.0000002")] if TINY else []))
        out.append((t, str(v)))
    return out


cnt, ex = Counter(), {}
for i in range(N):
    fields = {f: vals(f) for f in FIELDS}
    v = BASE["supply_min_v"] + rng.choice([D("-1"), D("-0.01"), D(0), D("1"), D("2.5"), D("3"), D("3.5"), D("4")])
    if v < 0:
        v = D(0)
    lo = D("-40") + rng.choice([D(-5), D(0), D(5), D(20)]); hi = lo + rng.choice([D(0), D(10), D(60), D(100)])
    row = {"fields": fields, "v": str(v), "ta": [str(lo), str(hi)]}
    # 엔진 입력은 float·tier 규칙: 'delegated' 는 datasheet+tier
    o_ok = True
    try:
        res, warns, why = judge(row)
        o = {"verdict": res, "warnings": sorted(warns), "violation": sorted(why["violation"]), "unknown": sorted(why["unknown"])}
    except ValueError:
        o_ok = False
    e = cmp.safe_engine({k: [list(x) for x in lst] for k, lst in fields.items()}, str(v), [str(lo), str(hi)])
    if not o_ok:
        cnt["오라클 입력 오류"] += 1
        continue
    c = cmp.classify(o, e)
    cnt[c] += 1
    if c != "일치" and len(ex.setdefault(c, [])) < 3:
        ex[c].append((row, o, e))
print(dict(cnt))
for k, lst in ex.items():
    print("==", k)
    for row, o, e in lst:
        print(" 입력", {f: row["fields"][f] for f in FIELDS if row["fields"][f]}, "V", row["v"], "Ta", row["ta"])
        print("  오라클", o, "| 엔진", None if e is None else (e[0], sorted(e[1]), sorted(e[2]), sorted(e[3])))
