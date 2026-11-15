#!/usr/bin/env python3
"""명세 2 대조 실행기: 오라클 정답과 엔진(edaharness.constraints)의 판정을 비교한다. 엔진 import 는 이 파일에만 있다.

사용: .venv/bin/python verification/compare_spec2.py practice|sealed [--show N]
봉인(sealed)은 오라클·엔진 고정 뒤 한 번만(사전 등록 순서) 돌린다. 출력: 화면 + data/verification/compare-<split>-<시각>.md (이 PC 전용).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "eda_harness"))
sys.path.insert(0, str(HERE))
from oracle_constraints import judge as oracle_judge  # noqa: E402
from edaharness import constraints as eng  # noqa: E402

VIOL = {"ABS_MAX_EXCEEDED": "abs_max_supply_v", "BELOW_RECOMMENDED": "supply_min_v", "ABOVE_RECOMMENDED": "supply_max_v",
        "TEMP_BELOW": "temp_min_c", "TEMP_ABOVE": "temp_max_c", "BAD_RANGE": "supply_min_v"}
UNK = {"MISSING", "CONFLICT"}


def to_record(fields: dict) -> dict:
    vals = {}
    for name, lst in fields.items():
        out = []
        for tier, num in lst:
            if tier in ("human", "delegated", "datasheet"):
                c = {"value": float(num), "source": "datasheet"}
                if tier == "delegated":
                    c["tier"] = "delegated"
            else:
                c = {"value": float(num), "source": tier}
            out.append(c)
        vals[name] = out
    return {"values": vals}


def run_engine(fields: dict, v: str, ta: list[str]):
    findings = eng.check_operating_point(to_record(fields), float(v), (float(ta[0]), float(ta[1])))
    viol = {VIOL[f["code"]] for f in findings if f["code"] in VIOL}
    unk = {f["field"] for f in findings if f["code"] in UNK}
    warns = {f["code"] for f in findings if f["code"] == "DELEGATED_CONFIRMATION"}
    verdict = "violation" if viol else ("unknown" if unk else "pass")
    return verdict, viol, unk, warns


def oracle_label(r: dict) -> dict:
    """저장된 라벨 대신 고정된 오라클로 입력에서 다시 계산한다."""
    res, warns, why = oracle_judge({"fields": r["fields"], "v": r["v"], "ta": r["ta"]})
    return {"verdict": res, "warnings": sorted(warns), "violation": sorted(why["violation"]), "unknown": sorted(why["unknown"])}


def safe_engine(fields, v, ta):
    try:
        return run_engine(fields, v, ta)
    except Exception:  # noqa: BLE001 — 예외·형식 불일치는 '엔진 오류'로 센다(통과도 일치도 아님)
        return None


def classify(o: dict, e) -> str:
    if e is None:
        return "엔진 오류"
    ev, eviol, eunk, ewarn = e
    ov = o["verdict"]
    if ov == "pass" and ev == "unknown":
        return "과잉 차단"
    if ov in ("violation", "unknown") and ev == "pass":
        return "위험한 통과"
    if ev == "violation" and ov in ("pass", "unknown"):
        return "거짓 위반"
    if ov == "violation" and ev == "unknown":
        return "놓친 위반"
    if ov == "pass" and ev == "violation":
        return "거짓 위반"
    if ov != ev:
        return "기타 불일치"
    if set(o["violation"]) != eviol or set(o["unknown"]) != eunk:
        return "이유 불일치"
    return "일치"


def properties(r: dict) -> list[str]:
    """성질 시험(엔진만 사용). 위반한 성질 이름 목록."""
    bad = []
    fields, v, ta = r["fields"], r["v"], r["ta"]
    base = run_engine(fields, v, ta)[0]
    # (a) 같은 증거의 순서를 바꿔도 같음
    rev = {k: list(reversed(lst)) for k, lst in fields.items()}
    if run_engine(rev, v, ta)[0] != base:
        bad.append("순서")
    # (b) 낮은 단계(라이브러리) 값을 더해도 판정이 안 바뀜(필드의 최상위 단계가 라이브러리가 아닐 때)
    for k, lst in fields.items():
        if lst and any(t != "library" for t, _ in lst):
            f2 = copy.deepcopy(fields)
            f2[k] = f2[k] + [["library", "0.0001"]]
            if run_engine(f2, v, ta)[0] != base:
                bad.append(f"낮은단계:{k}")
    # (c) 값이 빠지면 통과가 되지 않음
    if base != "pass":
        pass
    for k, lst in fields.items():
        if lst:
            f2 = copy.deepcopy(fields)
            f2[k] = []
            if run_engine(f2, v, ta)[0] == "pass":
                bad.append(f"빠짐:{k}")
    # (d) 방향별 단조성: 상한 이상에서 올려도, 하한 미만에서 내려도 위반이 통과로 바뀌지 않음
    if base == "violation":
        from decimal import Decimal as D
        up = run_engine(fields, str(D(v) + D("0.5")), ta)[0]
        dn = run_engine(fields, str(D(v) - D("0.5")), ta)[0]
        viol_codes = run_engine(fields, v, ta)[1]
        if ("supply_max_v" in viol_codes or "abs_max_supply_v" in viol_codes) and up == "pass":
            bad.append("단조-상한")
        if "supply_min_v" in viol_codes and dn == "pass":
            bad.append("단조-하한")
    # (e) 안전 방향으로 한계를 좁히면 통과는 위반으로만 바뀌고, 비통과는 통과가 되지 않는다(값이 하나인 데이터시트 필드만)
    from decimal import Decimal as D
    narrow = {"supply_max_v": D("-0.01"), "supply_min_v": D("0.01"), "temp_max_c": D("-1"), "temp_min_c": D("1")}
    for k, dv in narrow.items():
        lst = fields.get(k) or []
        if len(lst) == 1 and lst[0][0] == "datasheet":
            f2 = copy.deepcopy(fields)
            f2[k] = [["datasheet", str(D(lst[0][1]) + dv)]]
            nb = run_engine(f2, v, ta)[0]
            if base != "pass" and nb == "pass":
                bad.append(f"좁히기:{k}")
            if base == "pass" and nb == "unknown":
                bad.append(f"좁히기-판정불가:{k}")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=["practice", "sealed"])
    ap.add_argument("--set", choices=["risk", "r2"], default="risk")
    ap.add_argument("--show", type=int, default=5)
    a = ap.parse_args()
    ap_path = ROOT / "data" / "verification" / f"spec2-{a.set}-{a.split}.jsonl"
    import hashlib
    rows = [json.loads(l) for l in ap_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows:
        r.pop("oracle", None)  # 저장된 라벨은 쓰지 않는다
        r["oracle"] = oracle_label(r)
    inp = hashlib.sha256("\n".join(json.dumps({k: r[k] for k in ("id", "profile", "cell", "variant", "fields", "v", "ta")}, sort_keys=True, ensure_ascii=False) for r in rows).encode()).hexdigest()
    lab = hashlib.sha256("\n".join(json.dumps([r["id"], r["oracle"]], sort_keys=True) for r in rows).encode()).hexdigest()
    print("입력 sha256", inp, "| 오라클 라벨 sha256", lab)
    per_cell = defaultdict(Counter)
    prop_bad = Counter()
    ex = defaultdict(list)
    for r in rows:
        e = safe_engine(r["fields"], r["v"], r["ta"])
        cl = classify(r["oracle"], e)
        per_cell[r["cell"]][cl] += 1
        if cl != "일치" and len(ex[cl]) < a.show:
            ex[cl].append({"id": r["id"], "variant": r["variant"], "oracle": r["oracle"], "engine": (None if e is None else {"verdict": e[0], "violation": sorted(e[1]), "unknown": sorted(e[2]), "warnings": sorted(e[3])})})
        if e is not None and ((r["oracle"]["warnings"] and not e[3]) or (e[3] and not r["oracle"]["warnings"])):
            per_cell[r["cell"]]["경고 불일치"] += 1
        for p in properties(r):
            prop_bad[p.split(":")[0]] += 1
    lines = [f"# 명세 2 대조 — {a.split} ({len(rows)}개, {datetime.now():%Y-%m-%d %H:%M})", ""]
    total = Counter()
    for c in sorted(per_cell):
        total.update(per_cell[c])
        lines.append(f"- 칸 {c}: " + ", ".join(f"{k} {v}" for k, v in per_cell[c].most_common()))
    lines += ["", "합계: " + ", ".join(f"{k} {v}" for k, v in total.most_common()), "성질 위반: " + (", ".join(f"{k} {v}" for k, v in prop_bad.most_common()) or "0"), ""]
    for k, lst in ex.items():
        lines.append(f"## 예 — {k}")
        lines += [json.dumps(x, ensure_ascii=False) for x in lst]
    out = "\n".join(lines)
    print(out)
    (ROOT / "data" / "verification" / f"compare-{a.set}-{a.split}-{datetime.now():%Y%m%d-%H%M}.md").write_text(out + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
