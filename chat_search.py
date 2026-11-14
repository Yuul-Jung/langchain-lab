"""(추가) 채팅 RAG 모드의 검색 대상 선택: 업로드 문서 · 제1장 실습 문장 · 둘 다.

2026-11-12까지 채팅 RAG는 제1장 실습 인덱스(문장 3개)만 검색해서, 업로드한 문서에 대한
질문에도 '모터 과열·날씨' 문장이 근거로 나왔다. 이제 기본값은 업로드 문서 인덱스다.

CHAT_RAG_SOURCE (.env)
  documents : 업로드 문서(langchain_documents_v1)  ← 기본값. 문서가 없으면 실습 문장으로 대체
  lab       : 제1장 실습 문장(langchain_embedding_lab)만
  both      : 둘 다 검색해 점수순으로 합침 (두 인덱스 모두 cosine 유사도라 점수 비교 가능)

검색 함수는 인자로 받아서, 서버 없이 테스트할 수 있게 한다.
"""
from __future__ import annotations

SOURCES = ("documents", "lab", "both")
MAX_QUERY = 2000  # search_uploaded 의 검색어 길이 한도


def from_uploaded(hit: dict) -> dict:
    """업로드 문서 검색 결과 → 채팅 근거 형식."""
    return {
        "id": hit.get("chunk_id") or hit.get("document_id", ""),
        "score": hit.get("score"),
        "text": hit.get("text", ""),
        "snippet": hit.get("snippet"),
        "source": "documents",
        "document_id": hit.get("document_id"),
        "filename": hit.get("filename"),
        "title": hit.get("title"),
        "page": hit.get("page"),
        # 자동 모드의 처리 방식 판단에 쓰는 신호 (질문 낱말이 본문에 실제로 있었는가)
        "matched_terms": hit.get("matched_terms"),
        "vector_score": hit.get("vector_score"),
    }


def from_lab(hit: dict) -> dict:
    """제1장 실습 문장 검색 결과 → 채팅 근거 형식."""
    return {"id": hit.get("id"), "score": hit.get("score"), "text": hit.get("text", ""),
            "source": "lab", "document_id": None, "filename": None, "title": "제1장 실습 문장",
            "page": None}


def search_for_chat(query: str, source: str, *, search_uploaded, search_lab, limit: int = 4) -> list[dict]:
    """설정한 대상에서 검색해 점수 높은 순으로 최대 limit 개를 돌려준다."""
    if source not in SOURCES:
        raise ValueError(f"CHAT_RAG_SOURCE 는 {', '.join(SOURCES)} 중 하나여야 합니다: {source}")
    query = query[:MAX_QUERY]
    found = []
    if source in ("documents", "both"):
        found += [from_uploaded(h) for h in search_uploaded(query, limit=limit)]
    if source == "lab" or source == "both" or (source == "documents" and not found):
        found += [from_lab(h) for h in search_lab(query, limit=min(limit, 3))]
    found.sort(key=lambda h: h["score"] or 0, reverse=True)
    return found[:limit]


def label(source: dict) -> str:
    """근거 하나의 출처 표시: '문서명 · p.3' / '제1장 실습 문장'."""
    name = source.get("filename") or source.get("title") or "문서"
    return f"{name} · p.{source['page']}" if source.get("page") else name


def format_context(sources: list[dict]) -> str:
    """답변 모델에 넘길 참고 문서 목록."""
    return "\n".join(f"[자료 {i}] ({label(s)}) {s['text']}" for i, s in enumerate(sources, 1))
