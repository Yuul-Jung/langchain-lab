#!/usr/bin/env python3
"""한 폴더의 문서를 서비스와 떨어진 별도 인덱스·별도 보관함에 넣는다 (평가·비교용).

서비스 화면의 문서 목록(data/document_catalog)과 기존 인덱스는 건드리지 않는다.
같은 처리(document_pipeline.ingest_file: 추출·청크·임베딩)를 쓰되 보관 위치와 인덱스 이름만 바꾼다.
원본 문서와 추출 내용은 이 PC에만 둔다(data/ 는 git 밖, 커밋·공유 금지).

  .venv/bin/python scripts/ingest-folder.py --src ~/work_datasheets --index langchain_datasheets_v1 \
      --store data/datasheet_corpus            # 넣기 (이미 넣은 같은 파일은 건너뜀)
  .venv/bin/python scripts/ingest-folder.py --store data/datasheet_corpus --list    # 넣은 목록
지우기: 인덱스 삭제 + --store 폴더 삭제.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import document_pipeline as dp  # noqa: E402

PDF_MAGIC = b"%PDF"


def point_to(store: Path, index: str) -> None:
    """document_pipeline 의 보관 위치·인덱스 이름을 이 프로세스 안에서만 바꾼다."""
    store = store.resolve()
    dp.CATALOG_DIR = store / "catalog"
    dp.UPLOAD_DIR = store / "originals"
    dp.DOCUMENT_INDEX = index


def candidates(src: Path) -> list[Path]:
    """지원 확장자 파일 + 확장자가 없지만 내용이 PDF인 파일(.pdf 로 다룸)."""
    out = []
    for p in sorted(src.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix.lower() in dp.ALLOWED_EXTENSIONS:
            out.append(p)
        elif not p.suffix and p.read_bytes()[:4] == PDF_MAGIC:
            out.append(p)
    return out


def upload_name(p: Path) -> str:
    return p.name if p.suffix else p.name + ".pdf"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path)
    ap.add_argument("--index", default="langchain_datasheets_v1")
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-ai", action="store_true", help="모델 분석 없이 규칙 분류만(빠름)")
    args = ap.parse_args()
    if args.index == dp.settings.ES_DOCUMENT_INDEX:
        print("서비스 인덱스와 같은 이름은 쓸 수 없습니다.", file=sys.stderr)
        return 2
    point_to(args.store, args.index)
    if args.list:
        for d in dp.list_documents():
            print(d.get("index_status"), d.get("chunk_count"), d.get("filename"))
        return 0
    if not args.src or not args.src.is_dir():
        print("--src 폴더가 필요합니다.", file=sys.stderr)
        return 2
    ok = dup = fail = 0
    for p in candidates(args.src.expanduser()):
        try:
            r = dp.ingest_file(upload_name(p), p.read_bytes(), use_ai=not args.no_ai, index=True)
            if r["duplicate"]:
                dup += 1
            else:
                ok += 1
                print("넣음", r["document"]["chunk_count"], "청크 ·", p.name)
        except Exception as exc:  # 한 파일 실패가 전체를 멈추지 않게
            fail += 1
            print("실패", p.name, type(exc).__name__, str(exc)[:120])
    print(f"넣음 {ok} · 중복 {dup} · 실패 {fail} · 인덱스 {args.index}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
