#!/usr/bin/env python3
"""부품 데이터 출처의 오차가 회로 판정을 얼마나 틀리게 하는지 잰다 (S1 → S3, 읽기 전용).

정답: 데이터시트 원문에서 확인한 값(data/parts_gold/gold.jsonl, 봉인)으로 내린 판정.
예측: 다른 출처의 부품 기록(예: DigiKey·KiCad, part_record.to_constraint_record 형식)으로 내린 판정.
같은 동작점 격자(전원 전압 × 주변 온도)에서 두 판정을 비교한다. 판정은 eda_harness constraints 가 내린다.

지표(실행 전에 정함):
  - 위반 재현율   = 정답이 '위반'인 동작점 중 예측도 '위반(ERROR)'인 비율
  - 위반 정밀도   = 예측이 '위반'인 동작점 중 정답도 '위반'인 비율 (값 없음·충돌로 막힌 것은 따로 셈)
  - 위험한 통과   = 정답은 위반인데 예측은 통과 — 0이어야 한다 (가장 중요)
  - 막힘 비율     = 예측이 값 없음·충돌로 판정하지 못한 동작점 비율 (안전하지만 쓸 수 없음)
  - 값 오차       = 필드마다 |예측 출처 값 − 정답 값|, 일치율

  .venv/bin/python scripts/eval-constraints.py --records data/parts_records/records.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eda_harness"))
from edaharness import constraints as cs  # noqa: E402

GOLD = ROOT / "data" / "parts_gold" / "gold.jsonl"
RAILS = (1.8, 2.5, 3.3, 5.0, 9.0, 12.0, 15.0, 24.0)
TEMPS = ((0, 70), (-40, 85), (-40, 125))
BLOCK_CODES = {"MISSING", "CONFLICT"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]


def gold_records(path: Path = GOLD) -> dict[str, dict]:
    out = {}
    for r in read_jsonl(path):
        if "lib_id" in r:
            out[r["lib_id"]] = {"values": {f: [{"value": v["value"], "source": "datasheet"}] for f, v in r["values"].items()}}
    return out


def restrict(record: dict, fields) -> dict:
    """정답에 있는 필드만 남긴다 — 정답이 모르는 필드로 예측을 채점하지 않는다."""
    return {"values": {k: v for k, v in (record.get("values") or {}).items() if k in fields}}


def evaluate(gold: dict[str, dict], pred: dict[str, dict], exclude_sources=()) -> dict:
    tp = fp = tn = danger = blocked = blocked_viol = 0
    value_rows = []
    for lib_id, g in gold.items():
        fields = set(g["values"])
        p = pred.get(lib_id)
        p = restrict(p, fields) if p else {"values": {}}
        if exclude_sources:
            p = {"values": {k: [e for e in v if e["source"] not in exclude_sources] for k, v in p["values"].items()}}
        for f in sorted(fields):
            r = cs.resolve(p, f)
            value_rows.append({"lib_id": lib_id, "field": f, "gold": g["values"][f][0]["value"], "pred": r["value"],
                               "status": r["status"], "source": r["source"]})
        temps = TEMPS if {"temp_min_c", "temp_max_c"} & fields else (None,)
        for rail in RAILS:
            for temp in temps:
                gt = _partial_verdict(g, rail, temp, fields)
                pv = _partial_verdict(p, rail, temp, fields)
                if pv == "blocked":
                    blocked += 1
                    blocked_viol += gt == "violation"
                elif gt == "violation":
                    tp += pv == "violation"
                    danger += pv == "pass"
                else:
                    fp += pv == "violation"
                    tn += pv == "pass"
    viol = tp + danger + blocked_viol
    ok_vals = [r for r in value_rows if r["status"] == "ok"]
    exact = sum(1 for r in ok_vals if abs(r["pred"] - r["gold"]) <= 1e-6 * max(1, abs(r["gold"])))
    return {"points": tp + fp + tn + danger + blocked,
            "violation_recall": round(tp / viol, 3) if viol else None,
            "violation_precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "dangerous_pass": danger, "blocked": blocked, "blocked_violations": blocked_viol,
            "tp": tp, "fp": fp, "tn": tn,
            "values_total": len(value_rows), "values_available": len(ok_vals), "values_exact": exact,
            "values_conflict": sum(1 for r in value_rows if r["status"] == "conflict"),
            "value_rows": value_rows}


GROUPS = {"supply": {"supply_min_v", "supply_max_v", "abs_max_supply_v"}, "temp": {"temp_min_c", "temp_max_c"}}


def evaluate_by_rule(gold: dict[str, dict], pred: dict[str, dict], exclude_sources=()) -> dict:
    """규칙 묶음(전원·온도)을 따로 채점한다 — 한 묶음의 값 없음이 다른 묶음의 틀린 값을 가리지 않게(11-15 측정 보완)."""
    out = {}
    for name, gfields in GROUPS.items():
        g2 = {k: {"values": {f: v for f, v in r["values"].items() if f in gfields}} for k, r in gold.items()}
        g2 = {k: r for k, r in g2.items() if r["values"]}
        p2 = {k: {"values": {f: v for f, v in (r.get("values") or {}).items() if f in gfields}} for k, r in pred.items()}
        res = evaluate(g2, p2, exclude_sources)
        res.pop("value_rows")
        out[name] = res
    return out


def _partial_verdict(record: dict, rail: float, temp, fields) -> str:
    """정답에 있는 필드에 해당하는 규칙만으로 판정(없는 필드의 MISSING 은 세지 않음)."""
    f = cs.check_operating_point(record, rail, temp)
    f = [x for x in f if x["field"] in fields]
    if any(x["severity"] == "ERROR" and x["code"] in BLOCK_CODES for x in f):
        return "blocked"
    return "pass" if not any(x["severity"] == "ERROR" for x in f) else "violation"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=Path, required=True, help="부품 기록(jsonl, lib_id + values 형식 또는 part_record 형식)")
    ap.add_argument("--gold", type=Path, default=GOLD)
    ap.add_argument("--exclude-source", action="append", default=[], help="이 출처 값은 빼고 잰다(예: datasheet)")
    ap.add_argument("--rows", action="store_true", help="필드별 값 비교 표도 출력")
    args = ap.parse_args()
    gold = gold_records(args.gold)
    pred = {}
    for r in read_jsonl(args.records):
        if "values" not in r:
            sys.path.insert(0, str(ROOT))
            import part_record
            r = part_record.to_constraint_record(r)
        if r.get("lib_id") in gold:
            pred[r["lib_id"]] = r
    res = evaluate(gold, pred, tuple(args.exclude_source))
    rows = res.pop("value_rows")
    print(f"정답 부품 {len(gold)}개 중 기록 있음 {len(pred)}개")
    print(json.dumps(res, ensure_ascii=False))
    print("규칙 묶음별:", json.dumps(evaluate_by_rule(gold, pred, tuple(args.exclude_source)), ensure_ascii=False))
    if args.rows:
        for r in rows:
            print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
