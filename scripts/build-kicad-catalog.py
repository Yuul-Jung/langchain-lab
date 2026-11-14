#!/usr/bin/env python3
"""KiCad 심볼 라이브러리에서 부품 목록을 만들어 data/kicad_catalog/catalog.jsonl 에 저장한다 (읽기 전용 작업).

사용법: .venv/bin/python scripts/build-kicad-catalog.py [--index] [심볼 폴더]
  --index  목록을 Elasticsearch의 별도 인덱스(kicad_parts_v1)에 새로 만든다(있으면 지우고 다시 만듦).
심볼 폴더를 생략하면 Flatpak으로 설치된 KiCad 라이브러리 확장 패키지에서 찾는다.
결과는 data/ 아래에만 저장되고 GitHub에 올라가지 않는다.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kicad_parts  # noqa: E402

OUT = ROOT / "data" / "kicad_catalog" / "catalog.jsonl"


def find_symbol_dir() -> Path:
    out = subprocess.run(["flatpak", "info", "--user", "--show-location", "org.kicad.KiCad.Library.Symbols"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("KiCad 심볼 라이브러리를 찾지 못했습니다. 폴더를 직접 지정하세요.")
    return Path(out.stdout.strip()) / "files" / "symbols"


def index_parts(parts: list) -> None:
    from elasticsearch import helpers
    import rag_search
    es = rag_search.es_client()
    index = kicad_parts.ES_PARTS_INDEX
    if es.indices.exists(index=index):
        es.indices.delete(index=index)
    es.indices.create(index=index, **kicad_parts.es_index_body())
    ok, errors = helpers.bulk(es, kicad_parts.es_bulk_actions(parts, index), raise_on_error=False)
    es.indices.refresh(index=index)
    print(f"색인 {ok}개 · 오류 {len(errors)}개 → {index}")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--index"]
    folder = Path(args[0]) if args else find_symbol_dir()
    parts = kicad_parts.load_catalog(folder)
    kicad_parts.save_catalog(parts, OUT)
    with_fp = sum(1 for p in parts if p["footprint"])
    with_ds = sum(1 for p in parts if p["datasheet"])
    if "--index" in sys.argv:
        index_parts(parts)
    print(f"부품 {len(parts)}개 · 풋프린트 연결 {with_fp}개 · 데이터시트 링크 {with_ds}개 → {OUT}")


if __name__ == "__main__":
    main()
