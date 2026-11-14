"""Elasticsearch 없이 search_uploaded 와 같은 순서로 검색하는 평가용 대용품 (읽기 전용).

ES 가 내려가 있을 때(2026-11-14 01:15 OOM) 평가를 이어가기 위한 것이다. 운영 코드가 아니다.
- uploads/ 의 원본을 다시 추출해 청크를 만든다 (카탈로그·색인은 건드리지 않는다).
  카탈로그의 chunk_count 와 같은지 확인해, 다르면 그 문서는 경고한다.
- 벡터 후보(코사인 상위 SEARCH_POOL) + 낱말 후보(wildcard 대신 부분 문자열 일치)를 합치고 rerank_by_terms 로 정렬한다.
- 청크 임베딩은 LM Studio 로 한 번 계산해 캐시한다 (data/eval/graph-results/offline-index.pkl).
"""
from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import document_pipeline as dp
import settings
from rag_search import embed_query

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "eval" / "graph-results" / "offline-index.pkl"


def _unit(v):
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


class OfflineIndex:
    def __init__(self):
        self.chunks: list[dict] = []
        self.warnings: list[str] = []
        cache = pickle.loads(CACHE.read_bytes()) if CACHE.is_file() else {}
        dirty = False
        for meta_path in sorted((ROOT / "data" / "document_catalog").glob("*.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stored = dp.UPLOAD_DIR / f'{meta["document_id"]}{meta["format"]}'
            chunks = dp.make_chunks(dp.extract_sections(stored))
            if len(chunks) != meta.get("chunk_count"):
                self.warnings.append(f'{meta["document_id"][:6]}: 청크 {len(chunks)}개 ≠ 카탈로그 {meta.get("chunk_count")}개')
            for c in chunks:
                key = hashlib.sha256(c["text"].encode()).hexdigest()
                if key not in cache:
                    cache[key] = embed_query(c["text"])
                    dirty = True
                self.chunks.append({**c, "document_id": meta["document_id"], "filename": meta["filename"],
                                    "provenance": "source_extracted", "embedding": cache[key]})
        if dirty:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_bytes(pickle.dumps(cache))

    def search(self, query: str, limit: int = 5):
        qv = embed_query(query)
        scored = []
        for c in self.chunks:
            hit = {k: v for k, v in c.items() if k != "embedding"}
            hit["score"] = dp.cosine_score(qv, c["embedding"])
            scored.append(hit)
        pool = max(dp.SEARCH_POOL, limit)
        hits = sorted(scored, key=lambda h: -h["score"])[:pool]
        if settings.SEARCH_TERM_WEIGHT > 0:
            terms = dp.query_terms(query)[:dp.LEXICAL_TERMS_MAX]
            if terms:
                lowered = []
                for h in scored:
                    text = h["text"].lower()
                    n = sum(any(f.lower() in text for f in dp._term_forms(t)) for t in terms)
                    if n:
                        lowered.append((n, h))
                lowered.sort(key=lambda x: -x[0])
                hits = dp.merge_candidates(hits, [h for _, h in lowered[:pool]])
        return dp.rerank_by_terms(hits, query, settings.SEARCH_TERM_WEIGHT)[:limit]
