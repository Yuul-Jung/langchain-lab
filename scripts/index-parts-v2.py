#!/usr/bin/env python3
"""부품 카탈로그를 새 ES 인덱스 kicad_parts_v2(낱말 + 임베딩)에 색인한다. v1·문서 인덱스는 건드리지 않는다.
임베딩은 scripts/eval-parts-embedding.py 가 만든 캐시(parts-embed.npz)를 쓴다(LM Studio 호출 없음).
이미 있으면 --recreate 를 줘야 지우고 다시 만든다."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kicad_parts, rag_search, settings  # noqa: E402

INDEX = "kicad_parts_v2"
CACHE = ROOT / "data" / "eval" / "graph-results" / "parts-embed.npz"


def body() -> dict:
    b = kicad_parts.es_index_body()
    b["settings"].update({"number_of_shards": 1, "number_of_replicas": 0})   # 단일 노드: 복제본 없음(yellow 방지)
    b["mappings"]["properties"]["embedding"] = {"type": "dense_vector", "dims": settings.EMBEDDING_DIMS,
                                                "index": True, "similarity": "cosine"}
    b["mappings"]["properties"]["review_status"] = {"type": "keyword"}
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true")
    args = ap.parse_args()
    from elasticsearch import helpers
    parts = kicad_parts.default_catalog()
    z = np.load(CACHE, allow_pickle=False)
    if list(z["ids"]) != [p["lib_id"] for p in parts]:
        raise SystemExit("임베딩 캐시가 카탈로그와 다릅니다. scripts/eval-parts-embedding.py 로 다시 만드세요.")
    mat = z["mat"]
    es = rag_search.es_client()
    if es.indices.exists(index=INDEX):
        if not args.recreate:
            raise SystemExit(f"{INDEX} 가 이미 있습니다. 다시 만들려면 --recreate")
        es.indices.delete(index=INDEX)
    es.indices.create(index=INDEX, **body())

    def actions():
        for i, p in enumerate(parts):
            yield {"_index": INDEX, "_id": p["lib_id"],
                   "_source": {**p, "embedding": mat[i].tolist(), "review_status": "proposed"}}
    ok, errors = helpers.bulk(es, actions(), raise_on_error=False, chunk_size=200, request_timeout=120)
    es.indices.refresh(index=INDEX)
    print(f"색인 {ok}개 · 오류 {len(errors)}개 → {INDEX}")


if __name__ == "__main__":
    main()
