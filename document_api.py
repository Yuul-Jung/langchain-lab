"""Document management API. Bound to the existing loopback-only FastAPI app."""
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from document_pipeline import (
    ALLOWED_RELATIONS, MAX_BYTES, UPLOAD_DIR, _index_chunks, _write_catalog,
    extract_sections, get_document, ingest_file, list_documents, make_chunks,
    analyze_document, propose_relations, learning_sequence,
    search_uploaded, IndexingFailure, diagnose_failure, DOCUMENT_INDEX,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=15)
    document_id: str | None = None


class ReviewRequest(BaseModel):
    approve_classification: bool = False
    approve_learning_sequence: bool = False
    approved_relation_indices: list[int] = Field(default_factory=list, max_length=150)


def _load(document_id):
    try:
        return get_document(document_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="문서를 찾지 못했습니다.")


@router.get("")
def documents_list():
    return {"documents": list_documents()}


@router.get("/health/status")
def indexing_health():
    """Read-only check of ES credentials and embedding model; no secrets returned."""
    from rag_search import es_client, embed_query
    result = {
        "elasticsearch": {"ok": False, "code": "NOT_CHECKED"},
        "embedding": {"ok": False, "code": "NOT_CHECKED"},
        "document_index": DOCUMENT_INDEX,
    }
    try:
        es = es_client()
        es.info()
        result["elasticsearch"] = {"ok": True, "code": "CONNECTED"}
    except Exception as exc:
        issue = diagnose_failure(exc, "es_connection")
        result["elasticsearch"] = {"ok": False, "code": issue.code, "hint": issue.hint}
    try:
        values = embed_query("문서 색인 연결 진단")
        result["embedding"] = {
            "ok": len(values) == 2560,
            "code": "READY" if len(values) == 2560 else "EMBEDDING_DIMENSION",
        }
    except Exception as exc:
        issue = diagnose_failure(exc, "embedding")
        result["embedding"] = {"ok": False, "code": issue.code, "hint": issue.hint}
    return result


@router.get("/{document_id}")
def document_detail(document_id: str):
    return {"document": _load(document_id)}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    use_ai: bool = Form(True),
    index: bool = Form(True),
):
    # Read at most 8 MB + 1 byte. Do not trust client-provided Content-Length.
    try:
        body = await file.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="파일은 최대 8MB까지 허용됩니다.")
        try:
            return ingest_file(file.filename or "", body, use_ai=use_ai, index=index)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except IndexingFailure as exc:
            raise HTTPException(status_code=503, detail={
                "code": exc.code, "phase": exc.phase, "hint": exc.hint,
                "message": "문서 구조화는 보존되었습니다. 색인 실패 원인을 확인한 뒤 재등록하세요.",
            }) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="문서 처리 실패. 로컬 서버 로그와 문서 목록의 상태를 확인하세요.",
            ) from exc
    finally:
        await file.close()


@router.post("/search")
def search_documents_api(request: SearchRequest):
    try:
        return {"results": search_uploaded(
            request.query, limit=request.limit, document_id=request.document_id,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="검색 엔진 또는 임베딩 모델 연결 실패") from exc


@router.post("/{document_id}/reindex")
def reindex_document(document_id: str):
    """Retry only this document, never modify the legacy RAG lab index."""
    meta = _load(document_id)
    if meta.get("index_status") == "indexed":
        return {"document_id": document_id, "index_status": "indexed",
                "chunk_count": meta["chunk_count"], "already_indexed": True}
    ext = meta["format"]
    stored = UPLOAD_DIR / f"{document_id}{ext}"
    if not stored.is_file():
        raise HTTPException(status_code=404, detail="문서 원본 파일을 찾지 못했습니다.")
    try:
        sections = extract_sections(stored)
        chunks = make_chunks(sections)
        _index_chunks(meta, chunks)
        meta["index_status"] = "indexed"
        meta.pop("index_error", None)
        _write_catalog(meta)
        return {"document_id": document_id, "index_status": "indexed",
                "chunk_count": len(chunks)}
    except Exception as exc:
        issue = diagnose_failure(exc, "reindex")
        meta["index_status"] = "failed"
        meta["index_error"] = {"code": issue.code, "phase": issue.phase, "hint": issue.hint}
        _write_catalog(meta)
        raise HTTPException(status_code=503, detail={
            "code": issue.code, "phase": issue.phase, "hint": issue.hint,
            "message": "기존 원본 파일과 분석 결과는 보존됩니다.",
        }) from exc


@router.post("/{document_id}/reanalyze")
def reanalyze_document(document_id: str):
    """Refresh proposed classification without touching original PDF or vector index.

    Old human approvals are invalidated when new analysis is proposed.
    Previously indexed chunks remain searchable, with their original provenance.
    """
    meta = _load(document_id)
    stored = UPLOAD_DIR / f'{document_id}{meta["format"]}'
    if not stored.is_file():
        raise HTTPException(status_code=404, detail="저장된 원본 파일을 찾지 못했습니다.")
    try:
        sections = extract_sections(stored)
        # Existing indexed documents must keep their chunk IDs until a separate
        # reindex/migration step. Do not silently modify indexed section structure.
        old_sections = meta.get("sections", [])
        same_ids = [s["id"] for s in sections] == [s["id"] for s in old_sections]
        same_count = len(sections) == len(old_sections)
        if meta.get("index_status") == "indexed" and not (same_ids and same_count):
            # Analyze original stored sections only; heading migration requires reindex.
            from pypdf import PdfReader
            if meta["format"] == ".pdf":
                reader = PdfReader(str(stored))
                sections = []
                for old in old_sections:
                    page_no = old.get("page")
                    if page_no and 1 <= page_no <= len(reader.pages):
                        text = (reader.pages[page_no - 1].extract_text() or "").strip()
                    else:
                        text = ""
                    sections.append({
                        **old, "text": text,
                    })
            else:
                raise HTTPException(status_code=409, detail="원본 절 구조가 변경되었습니다. 재구조화 마이그레이션이 필요합니다.")
        classification = analyze_document(sections, meta["filename"], use_ai=True)
        relations = propose_relations(sections, classification["concepts"])
        sequence = learning_sequence(sections, relations)
        meta["classification"] = classification
        meta["relations"] = relations
        meta["learning_sequence"] = sequence
        meta["analysis_updated_at"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
        _write_catalog(meta)
        return {"document": meta, "structure_changed": False}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="분석 실패: 로컬 서비스 로그를 확인하세요.") from exc


@router.post("/{document_id}/review")
def review_document(document_id: str, body: ReviewRequest):
    """Approve proposals explicitly; source-extracted order and text are immutable."""
    meta = _load(document_id)
    indexes = body.approved_relation_indices
    if len(set(indexes)) != len(indexes) or any(
        i < 0 or i >= len(meta["relations"]) for i in indexes
    ):
        raise HTTPException(status_code=400, detail="관계 번호가 유효하지 않습니다.")
    if body.approve_classification:
        meta["classification"]["review_status"] = "approved"
    if body.approve_learning_sequence:
        meta["learning_sequence"]["review_status"] = "approved"
    for index in indexes:
        relation = meta["relations"][index]
        if relation.get("type") not in ALLOWED_RELATIONS:
            raise HTTPException(status_code=400, detail="지원하지 않는 관계 유형입니다.")
        if relation.get("provenance") != "source_extracted":
            relation["review_status"] = "approved"
    _write_catalog(meta)
    return {"document": meta}
