#!/usr/bin/env python3
"""데이터시트 값 확인의 위임 검토: 가린 시트 만들기 · 위임 확인 가져오기 · 추출기와 비교 (data/datasheet_review/).

역할을 나눈 이유: 추출기와 화면을 만든 세션이 확인까지 하면 한 세션이 추출자와 확인자를 겸한다.
그래서 확인은 추출기를 쓰지 않은 세션이 가린 시트로 하고, 추출기와의 비교는 만든 쪽이 나중에 한다.
- 시트에는 문서·쪽수·항목·인용문만 있다(추출기의 값·표시 없음, 순서 섞음). 인용문 안에 숫자가 있으므로
  이 확인은 판단이라기보다 읽기를 잰다. 두 Claude 세션은 사각지대를 공유하므로 위임 확인은 사람 등급이 아니다.
- 절대 최대 전원은 사람만 확인하므로 시트에 넣지 않는다.
- 가져오기는 approver 를 "delegated: …" 로 고정한다(화면의 클릭이 아님). 읽을 수 없으면 value 를 null(확인 불가)로 쓴다.
- '다름'(disputed)은 우리가 풀지 않고 사용자 대기 목록으로 보낸다.

  .venv/bin/python scripts/delegated-review.py blind  --out data/datasheet_review/blind_sheet.jsonl
  .venv/bin/python scripts/delegated-review.py import --file data/datasheet_review/delegated_jung29.jsonl --approver "delegated: jung-29"
  .venv/bin/python scripts/delegated-review.py compare
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import datasheet_review as dr  # noqa: E402

SEED = "delegated-review-2026-11-15"


def short_id(key: str) -> str:
    return hashlib.sha1((SEED + key).encode()).hexdigest()[:10]


def candidates() -> list[dict]:
    return dr._jsonl(dr.CANDIDATES)


def cmd_blind(out: Path) -> int:
    rows = [c for c in candidates() if c["field"] not in dr.HUMAN_ONLY]
    random.Random(SEED).shuffle(rows)
    sheet = [{"id": short_id(dr.key_of(c["doc"], c["field"], c["value"], c["page"])), "doc": c["doc"],
              "page": c["page"], "ask": dr.FIELD_LABEL[c["field"]], "quote": c["quote"], "value": None, "note": ""}
             for c in rows]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in sheet) + "\n", encoding="utf-8")
    print(f"가린 시트 {len(sheet)}개 → {out} (값 칸 value 에 읽은 숫자를, 읽을 수 없으면 null 로)")
    return 0


def cmd_import(path: Path, approver: str) -> int:
    if not approver.startswith("delegated:"):
        print("approver 는 'delegated:' 로 시작해야 합니다(사람 등급은 이 도구로 만들 수 없음).", file=sys.stderr)
        return 2
    by_id = {short_id(dr.key_of(c["doc"], c["field"], c["value"], c["page"])): dr.key_of(c["doc"], c["field"], c["value"], c["page"])
             for c in candidates() if c["field"] not in dr.HUMAN_ONLY}
    n = bad = 0
    for r in dr._jsonl(path):
        k = by_id.get(r.get("id"))
        v = r.get("value")
        if k is None or not (v is None or isinstance(v, (int, float))) or isinstance(v, bool):
            bad += 1
            continue
        dr.record(k, v, note=str(r.get("note", "")), approver=approver)
        n += 1
    print(f"가져옴 {n}개 · 건너뜀 {bad}개")
    return 0


def cmd_compare() -> int:
    dec = dr.latest(dr._jsonl(dr.DECISIONS))
    out = {"confirmed": 0, "disputed": 0, "unclear": 0}
    disputed = []
    for d in dec.values():
        if not str(d["approver"]).startswith("delegated:"):
            continue
        out[d["outcome"]] += 1
        if d["outcome"] == "disputed":
            disputed.append((d["doc"], d["field"], d["page"], d["extracted_value"], d["reviewer_value"]))
    print(json.dumps(out, ensure_ascii=False))
    for x in disputed:
        print("다름(사용자 대기):", x)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("blind")
    b.add_argument("--out", type=Path, default=dr.DIR / "blind_sheet.jsonl")
    i = sub.add_parser("import")
    i.add_argument("--file", type=Path, required=True)
    i.add_argument("--approver", required=True)
    sub.add_parser("compare")
    a = ap.parse_args()
    if a.cmd == "blind":
        return cmd_blind(a.out)
    if a.cmd == "import":
        return cmd_import(a.file, a.approver)
    return cmd_compare()


if __name__ == "__main__":
    sys.exit(main())
