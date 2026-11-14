#!/usr/bin/env python3
"""자동 추출한 데이터시트 값과 DigiKey 값이 겹치는 빈도와 일치율 (읽기 전용, 숫자만 출력).

문서 → 부품(lib_id)은 내려받기 목록(manifest*.json)과 정답 파일(gold*.jsonl)로 잇는다.
필드마다: 둘 다 값이 있는 경우(겹침) 중 DigiKey 값이 추출 후보 안에 있으면 일치.
  .venv/bin/python scripts/crosscheck-extracted.py --records data/parts_records/records.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import datasheet_evidence as de  # noqa: E402
import part_record  # noqa: E402

FIELDS = ("supply_min_v", "supply_max_v", "temp_min_c", "temp_max_c")


def doc_map() -> dict[str, str]:
    m: dict[str, str] = {}
    base = ROOT / "data" / "datasheet_corpus" / "downloaded"
    for name in ("manifest.json", "manifest2.json"):
        p = base / name
        if p.exists():
            for it in json.loads(p.read_text(encoding="utf-8"))["items"]:
                if it.get("file"):
                    m[it["file"]] = f'{it["library"]}:{it["part"]}'
    for g in ("gold.jsonl",):
        p = ROOT / "data" / "parts_gold" / g
        for line in p.read_text(encoding="utf-8").splitlines():
            if '"lib_id"' in line:
                r = json.loads(line)
                m[r["datasheet"]] = r["lib_id"]
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=Path, required=True)
    args = ap.parse_args()
    recs = {}
    for line in args.records.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            c = part_record.to_constraint_record(r) if "values" not in r else r
            recs[c["lib_id"]] = c
    roots = [Path.home() / "work_datasheets", ROOT / "data" / "datasheet_corpus" / "downloaded"]
    stat = {f: {"both": 0, "agree": 0, "differ": 0, "only_extracted": 0, "only_digikey": 0} for f in FIELDS}
    docs = 0
    for fn, lib in doc_map().items():
        rec = recs.get(lib)
        path = next((h for r in roots for h in r.rglob(fn)), None)
        if rec is None or path is None:
            continue
        try:
            ev = de.evidence(path)["values"]
        except Exception:
            continue
        docs += 1
        for f in FIELDS:
            ext = {round(e["value"], 4) for e in ev.get(f, [])}
            dk = {round(e["value"], 4) for e in (rec["values"].get(f) or []) if e["source"] == "distributor"}
            s = stat[f]
            if ext and dk:
                s["both"] += 1
                s["agree" if dk & ext else "differ"] += 1
            elif ext:
                s["only_extracted"] += 1
            elif dk:
                s["only_digikey"] += 1
    print("문서(부품 기록과 이어진 것):", docs)
    for f, s in stat.items():
        print(f, json.dumps(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
