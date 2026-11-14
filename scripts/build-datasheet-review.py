#!/usr/bin/env python3
"""데이터시트에서 자동 추출한 값 후보를 확인 화면용 목록으로 만든다 (data/datasheet_review/candidates.jsonl).

문서 폴더의 PDF마다 datasheet_evidence 로 후보(값·쪽수·인용문)를 뽑는다. 암호 PDF·추출 실패는 건너뛴다.
결과에는 데이터시트 인용문이 들어 있으므로 data/ 아래(git 밖)에만 둔다.

  .venv/bin/python scripts/build-datasheet-review.py --src data/datasheet_corpus/downloaded --src ~/work_datasheets
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import datasheet_evidence as de  # noqa: E402
import datasheet_review as dr  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", action="append", type=Path, required=True)
    args = ap.parse_args()
    dr.DIR.mkdir(parents=True, exist_ok=True)
    rows, skipped = [], 0
    for src in args.src:
        for pdf in sorted(Path(src).expanduser().rglob("*")):
            if pdf.suffix.lower() != ".pdf":
                continue
            try:
                cands = de.candidates_from_pages(de.page_texts(pdf))
            except Exception:
                skipped += 1
                continue
            for c in cands:
                rows.append({"doc": pdf.name, "field": c["field"], "value": c["value"], "page": c["page"],
                             "quote": c["quote"]})
    dr.CANDIDATES.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"후보 {len(rows)}개 · 건너뜀 {skipped}개 → {dr.CANDIDATES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
