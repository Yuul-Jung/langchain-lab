#!/usr/bin/env python3
"""Read-only pipeline audit: keep document bodies, filenames, IDs and credentials private.

Usage:
  .venv/bin/python scripts/evaluate-pipeline.py
  .venv/bin/python scripts/evaluate-pipeline.py --query "UART 16배 오버샘플링"
  .venv/bin/python scripts/evaluate-pipeline.py --query "..." --expected "UART" --expected "FPGA"

The expected options evaluate substring presence in top-k retrieved chunks; this
is a small regression probe, NOT factual accuracy or RAG answer validation.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from document_pipeline import (
    UPLOAD_DIR, extract_sections, get_document, list_documents,
    make_chunks, search_uploaded,
)


def extraction_report(meta):
    doc_id = meta["document_id"]
    original = UPLOAD_DIR / (doc_id + (meta.get("format") or ""))
    if not original.is_file():
        return {"source": "MISSING"}
    try:
        sections = extract_sections(original)
        chunks = make_chunks(sections)
        lengths = [len(s["text"]) for s in sections]
        return {
            "source": "OK", "sections_extracted": len(sections),
            "chunks_generated": len(chunks),
            "characters_extracted": sum(lengths),
            "min_section_chars": min(lengths), "max_section_chars": max(lengths),
            "page_only_titles": sum(
                str(s["title"]).startswith("PDF ") and str(s["title"]).endswith("쪽")
                for s in sections
            ),
            "inferred_heading_count": sum(
                s.get("provenance") == "rule_inferred" for s in sections
            ),
            "zero_length_chunks": sum(not c["text"].strip() for c in chunks),
        }
    except Exception as exc:
        # No filename or exception body: document contents/paths may be private.
        return {"source": "ERROR", "error_type": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser(description="Private, read-only 4-stage RAG audit")
    parser.add_argument("--query", help="One non-sensitive search query")
    parser.add_argument("--expected", action="append", default=[],
                        help="Expected keyword in top-k retrieved text (repeatable)")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    if args.expected and not args.query:
        parser.error("--expected requires --query")
    if args.top_k < 1 or args.top_k > 15:
        parser.error("--top-k must be 1..15")

    docs = list_documents()
    counts = Counter(str(d.get("index_status", "unknown")) for d in docs)
    print("=== LangChain Lab: pipeline evaluation (read only) ===")
    print("1. 문서 전처리 / 청크 검증")
    print("Document count:", len(docs), "Index states:", dict(sorted(counts.items())))
    for index, listing in enumerate(docs, 1):
        try:
            full = get_document(listing["document_id"])
            analysis = extraction_report(full)
            print(f"  문서 {index}: " + json.dumps({
                "stored_sections": full.get("section_count"),
                "stored_chunks": full.get("chunk_count"),
                "classification_method": (full.get("classification") or {}).get("method"),
                "index_status": full.get("index_status"),
                "failure_code": (full.get("index_error") or {}).get("code"),
                "extraction_now": analysis,
            }, ensure_ascii=False))
        except (OSError, ValueError, KeyError) as exc:
            print(f"  문서 {index}: 메타데이터 읽기 실패 ({type(exc).__name__})")

    print("2. 임베딩 / 검색")
    if args.query:
        try:
            hits = search_uploaded(args.query, limit=args.top_k)
            print("  Search OK; hits:", len(hits))
            for rank, item in enumerate(hits, 1):
                print(f"  rank={rank} score={item.get('score')} "
                      f"page={item.get('page')} chars={len(item.get('text') or '')}")
            for expected in args.expected:
                found = any(expected.casefold() in str(h.get("text", "")).casefold()
                            for h in hits)
                print("  expected term matched:", "YES" if found else "NO")
            print("  Note: keyword matches do not establish answer correctness.")
        except Exception as exc:
            print("  Search ERROR:", type(exc).__name__)
            print("  Use the existing /api/documents/health/status for connection codes.")
    else:
        print("  SKIPPED: use --query to test the live embedding and Elasticsearch path.")

    print("3. 답변 생성")
    print("  NOT TESTED: this script does not invoke an LLM or grade factual accuracy.")
    print("  For factual assessment use reference Q&A and source attribution.")
    print("Safety: no data/index modification; document texts and names not printed.")


if __name__ == "__main__":
    main()
