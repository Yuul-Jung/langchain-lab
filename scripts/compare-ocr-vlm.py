#!/usr/bin/env python3
"""제3장 — VLM 요약의 영문 식별자를 Tesseract OCR 원문과 대조 (읽기 전용).

사용 예:
  .venv/bin/python scripts/compare-ocr-vlm.py 115 116 117
  .venv/bin/python scripts/compare-ocr-vlm.py 115 --engines psm3 psm6

입력 : <work-dir>/vlm_result/page_0115_v02.json
       <work-dir>/ocr_compare/<engine>/page_0115.txt
출력 : <work-dir>/vlm_result/compare_ocr_vlm.md

VLM 결과 파일의 verified 값은 변경하지 않는다. 판정은 사람이 원본 이미지로 확인한다.
한글 문장은 비교하지 않는다(OCR 품질 편차가 커서 식별자만 대조).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vlm_ocr import compare_page, render_markdown  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="OCR ↔ VLM 식별자 대조 보고서")
    ap.add_argument("pages", nargs="+", type=int)
    ap.add_argument("--work-dir", type=Path, default=Path.home() / "pdf_recovery_work")
    ap.add_argument("--engines", nargs="+", default=["psm3", "psm6"])
    ap.add_argument("--tag", default="v02")
    args = ap.parse_args()

    work = args.work_dir.expanduser()
    results = {}
    for n in args.pages:
        vlm_p = work / "vlm_result" / f"page_{n:04d}_{args.tag}.json"
        if not vlm_p.is_file():
            print(f"[{n}] 건너뜀 — VLM 결과 없음: {vlm_p.name}")
            continue
        vlm = json.loads(vlm_p.read_text(encoding="utf-8"))["content"]
        ocr = {}
        for eng in args.engines:
            p = work / "ocr_compare" / eng / f"page_{n:04d}.txt"
            ocr[eng] = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        res = compare_page(vlm, ocr)
        results[n] = res
        ok = sum(r["confirmed"] for r in res["rows"])
        print(f"[{n}] VLM 식별자 {len(res['rows'])}개 — 확인 {ok}, "
              f"의심 {len(res['rows']) - ok} / VLM 누락 후보 {len(res['missed'])}개")

    if not results:
        print("대조할 페이지가 없습니다.")
        return 1
    out = work / "vlm_result" / "compare_ocr_vlm.md"
    out.write_text(render_markdown(results, args.engines), encoding="utf-8")
    print(f"\n보고서 저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
