#!/usr/bin/env python3
"""한·영 다리 4단계(위임 2단계 검토) 준비: 독립 검토용 블라인드 시트와 합의 결과 쓰기.

  --blind   : data/ontology/bridge_review_blind.jsonl — 검토자(71)용. 영어·한국어 짝과 출처 빈도만(자동 판정은 숨김).
  --consensus <검토 파일>: 자동 판정 '권고 승인' 이고 검토 'OK' 인 짝만 approved 로 data/ontology/bridge_approvals.jsonl 끝에 덧붙인다.
     검토 파일 줄 형식: {"en", "ko", "verdict": "OK"|"의심"|"오류", "fix_ko"(선택), "reason"}
승인자 표기는 사람 승인과 구분한다: "delegated: jung-29 + 71 (사용자 위임)".
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PH = ROOT / "data" / "ontology" / "bridge_phrases.jsonl"
BLIND = ROOT / "data" / "ontology" / "bridge_review_blind.jsonl"
APPROVALS = ROOT / "data" / "ontology" / "bridge_approvals.jsonl"
APPROVER = "delegated: jung-29 + 71 (사용자 위임: '한영낱말 다리를 만들 수 있는 프레임워크')"


def rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind", action="store_true")
    ap.add_argument("--consensus", default="")
    args = ap.parse_args()
    data = rows(PH)
    if args.blind:
        with BLIND.open("w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps({"en": r["en"], "ko": r.get("ko", ""), "df_kicad": r.get("df_kicad"),
                                    "df_datasheet": r.get("df_datasheet")}, ensure_ascii=False) + "\n")
        print(f"블라인드 시트 {len(data)}줄 → {BLIND.relative_to(ROOT)}")
    if args.consensus:
        review = {(r["en"], r.get("ko", "")): r for r in rows(Path(args.consensus)) if "en" in r}   # 머리말 줄은 건너뜀
        n = 0
        with APPROVALS.open("a", encoding="utf-8") as f:
            for r in data:
                v = review.get((r["en"], r.get("ko", "")))
                ok = r.get("auto") == "권고 승인" and v and v.get("verdict") == "OK"
                f.write(json.dumps({"en": r["en"], "ko": r.get("ko", ""), "decision": "approved" if ok else "proposed",
                                    "approver": APPROVER if ok else "-", "date": date.today().isoformat(),
                                    "reason": "자동 확인 권고 승인 + 독립 검토 OK" if ok else
                                    f"자동 {r.get('auto')} / 검토 {v.get('verdict') if v else '없음'}",
                                    "evidence": {"phrases_sha256": sha(PH), "review_sha256": sha(Path(args.consensus))}},
                                   ensure_ascii=False) + "\n")
                n += ok
        print(f"합의 승인 {n}개 / {len(data)}개 → {APPROVALS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
