#!/usr/bin/env python3
"""제3장 — 페이지 이미지를 LM Studio 비전 모델(Qwen3-VL)로 분석해 JSON으로 저장.

사용 예:
  .venv/bin/python scripts/vlm-analyze-pages.py 115 116 117
  .venv/bin/python scripts/vlm-analyze-pages.py 118 --work-dir ~/pdf_recovery_work

입력 : <work-dir>/ocr_compare/images/page_0115.png
출력 : <work-dir>/vlm_result/page_0115_v02.json   (verified=false 로 저장)

- 이미 결과가 있는 페이지는 건너뛴다(덮어쓰지 않음).
- 한 페이지가 실패해도 다음 페이지를 계속 처리한다.
- 실패 시 LM Studio 응답 본문과 조치 안내를 함께 출력한다.
- 사전 조건: qwen3-vl-4b 를 컨텍스트 16384 이상으로 로드
    lms load qwen3-vl-4b --context-length 16384
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vlm_ocr import (DEFAULT_BASE_URL, DEFAULT_MODEL, build_payload,  # noqa: E402
                     call_vlm, image_data_uri)


def main() -> int:
    ap = argparse.ArgumentParser(description="페이지 이미지 → VLM 요약 JSON")
    ap.add_argument("pages", nargs="+", type=int, help="페이지 번호 (예: 115 116 117)")
    ap.add_argument("--work-dir", type=Path, default=Path.home() / "pdf_recovery_work")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--tag", default="v02", help="출력 파일 접미사 (page_0115_<tag>.json)")
    args = ap.parse_args()

    img_dir = args.work_dir.expanduser() / "ocr_compare" / "images"
    out_dir = args.work_dir.expanduser() / "vlm_result"
    out_dir.mkdir(parents=True, exist_ok=True)

    failed = 0
    for n in args.pages:
        img = img_dir / f"page_{n:04d}.png"
        out = out_dir / f"page_{n:04d}_{args.tag}.json"
        if out.exists():
            print(f"[{n}] 건너뜀 — 결과 이미 있음: {out.name}")
            continue
        if not img.is_file():
            print(f"[{n}] 건너뜀 — 이미지 없음: {img}")
            failed += 1
            continue

        payload = build_payload(image_data_uri(img), model=args.model,
                                max_tokens=args.max_tokens)
        t0 = time.time()
        try:
            res = call_vlm(payload, base_url=args.base_url)
        except RuntimeError as exc:
            print(f"[{n}] ❌ {exc}")
            failed += 1
            continue
        elapsed = round(time.time() - t0, 1)

        record = {"model": args.model, "image": str(img), "elapsed_seconds": elapsed,
                  "finish_reason": res["finish_reason"], "verified": False,
                  "content": res["content"]}
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        warn = "  ⚠ 답변 잘림(length) — --max-tokens 증가 필요" if res["finish_reason"] == "length" else ""
        print(f"[{n}] ✅ {elapsed}초 → {out.name}{warn}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
