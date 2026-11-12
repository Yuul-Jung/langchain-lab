#!/usr/bin/env python3
"""평가 세트로 문서 검색 품질 채점 — 읽기 전용 (색인·문서를 바꾸지 않음).

평가 세트: data/eval/questions.jsonl (GitHub에 올라가지 않음, 한 줄에 질문 하나)
  {"id": "q01", "question": "...", "document_id": "064340...", "pages": [3, 4],
   "answer": "정답 요약", "keywords": ["핵심어"], "status": "draft"}
  - document_id 는 앞 6자리만 써도 된다. pages 는 근거가 있는 원본 PDF 쪽 번호.
  - status: draft(초안, 사람 검토 전) · approved(검토 완료)

채점: 질문을 실제 임베딩·검색(업로드 문서 인덱스 전체)에 넣고,
  정답 문서의 정답 쪽이 상위 몇 위에 나왔는지 본다.
  - hit@1, hit@k: 1위 / 상위 k개 안에 정답 쪽이 있는 질문 비율
  - MRR: 정답이 처음 나온 순위의 역수 평균 (1위=1.0, 2위=0.5, 없음=0)
  - keyword@k: 상위 k개 본문에 keywords 중 하나라도 있는 비율 (보조 지표)
  - 평균 결과 수, 정밀도: 점수 컷오프(SEARCH_SCORE_MARGIN) 적용 후 실제로 보여 주는 결과 개수와
    그중 정답 쪽의 비율. "관련 없는 쪽이 너무 많이 따라 나온다"를 재는 지표다.
이 점수는 검색 단계만 본다. 답변 생성의 정확성은 채점하지 않는다.

한 단어 검색: data/eval/keywords.txt (선택, 한 줄에 낱말 하나, # 은 주석)가 있으면
  각 낱말로 검색해 결과 본문에 그 낱말이 실제로 들어 있는 비율을 함께 본다.
  벡터 검색만 쓰면 한 단어 검색에서 그 낱말이 없는 쪽이 위로 올라오기 쉽다.

출력에는 문서 본문·파일명을 넣지 않는다. 결과는 data/eval/results/ 에 저장하고
직전 결과와 순위가 달라진 질문을 보여 준다.

사용:
  .venv/bin/python scripts/run-eval.py                 # 전체 질문
  .venv/bin/python scripts/run-eval.py --k 10          # 상위 10개까지 채점
  .venv/bin/python scripts/run-eval.py --only-approved # 검토 완료 질문만
  .venv/bin/python scripts/run-eval.py --margin 0      # 컷오프 없이 (상위 k개 그대로)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

QUESTIONS = ROOT / "data" / "eval" / "questions.jsonl"
KEYWORDS = ROOT / "data" / "eval" / "keywords.txt"
RESULTS = ROOT / "data" / "eval" / "results"
STATUSES = {"draft", "approved"}


def load_questions(path, known_ids=()):
    """질문 파일을 읽고 형식을 검사한다. 문제가 있으면 줄 번호와 함께 ValueError."""
    items, seen = [], set()
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{n}번째 줄: JSON 형식 오류 ({exc.msg})") from exc
        for key in ("id", "question", "document_id", "pages"):
            if not item.get(key):
                raise ValueError(f"{n}번째 줄: '{key}' 항목이 비어 있습니다.")
        if item["id"] in seen:
            raise ValueError(f"{n}번째 줄: 질문 id '{item['id']}'가 중복입니다.")
        seen.add(item["id"])
        if not all(isinstance(p, int) and p > 0 for p in item["pages"]):
            raise ValueError(f"{n}번째 줄: pages 는 1 이상의 쪽 번호 목록이어야 합니다.")
        item.setdefault("status", "draft")
        if item["status"] not in STATUSES:
            raise ValueError(f"{n}번째 줄: status 는 draft 또는 approved 입니다.")
        if known_ids:
            matches = [d for d in known_ids if d.startswith(item["document_id"])]
            if len(matches) != 1:
                raise ValueError(f"{n}번째 줄: document_id '{item['document_id']}'와 맞는 문서가 "
                                 f"{len(matches)}개입니다 (정확히 1개여야 함).")
            item["document_id"] = matches[0]
        items.append(item)
    if not items:
        raise ValueError("질문이 하나도 없습니다.")
    return items


def score_question(item, hits, k):
    """검색 결과(hits: document_id·page·text)로 질문 하나를 채점한다."""
    pages = set(item["pages"])
    rank = next((i for i, h in enumerate(hits[:k], 1)
                 if h.get("document_id") == item["document_id"] and h.get("page") in pages), None)
    doc_rank = next((i for i, h in enumerate(hits[:k], 1)
                     if h.get("document_id") == item["document_id"]), None)
    keywords = [w.lower() for w in item.get("keywords") or []]
    keyword_hit = None if not keywords else any(
        w in (h.get("text") or "").lower() for h in hits[:k] for w in keywords)
    shown = hits[:k]
    relevant = sum(1 for h in shown
                   if h.get("document_id") == item["document_id"] and h.get("page") in pages)
    return {"id": item["id"], "status": item["status"], "rank": rank, "doc_rank": doc_rank,
            "returned": len(shown), "relevant": relevant,
            "top1_page": hits[0].get("page") if hits else None,
            "top1_same_doc": bool(hits) and hits[0].get("document_id") == item["document_id"],
            "keyword_hit": keyword_hit}


def summarize(results, k):
    n = len(results)
    with_kw = [r for r in results if r["keyword_hit"] is not None]
    return {
        "questions": n, "k": k,
        "hit@1": round(sum(r["rank"] == 1 for r in results) / n, 3),
        f"hit@{k}": round(sum(r["rank"] is not None for r in results) / n, 3),
        "mrr": round(sum(1 / r["rank"] for r in results if r["rank"]) / n, 3),
        "doc@1": round(sum(r["top1_same_doc"] for r in results) / n, 3),
        f"keyword@{k}": round(sum(r["keyword_hit"] for r in with_kw) / len(with_kw), 3) if with_kw else None,
        "avg_results": round(sum(r["returned"] for r in results) / n, 2),
        "precision": round(sum(r["relevant"] / r["returned"] for r in results if r["returned"]) / n, 3),
    }


def score_keyword(term, hits):
    """한 단어 검색 채점: 결과 중 그 낱말이 본문(띄어쓰기·대소문자 무시)에 있는 비율."""
    flat = ["".join((h.get("text") or "").split()).lower() for h in hits]
    has = [term.lower() in t for t in flat]
    return {"returned": len(hits), "containing": sum(has),
            "top1_contains": bool(has) and has[0]}


def summarize_keywords(rows):
    n = len(rows)
    return {"keywords": n,
            "avg_results": round(sum(r["returned"] for r in rows) / n, 2),
            "containing_rate": round(sum(r["containing"] / r["returned"] for r in rows if r["returned"]) / n, 3),
            "top1_contains": round(sum(r["top1_contains"] for r in rows) / n, 3)}


def compare(previous, results):
    """직전 결과와 비교해 순위가 바뀐 질문 목록 (id, 이전 순위, 지금 순위)."""
    before = {r["id"]: r["rank"] for r in previous.get("results", [])}
    return [(r["id"], before[r["id"]], r["rank"]) for r in results
            if r["id"] in before and before[r["id"]] != r["rank"]]


def main():
    parser = argparse.ArgumentParser(description="평가 세트로 문서 검색 채점 (읽기 전용)")
    parser.add_argument("--questions", default=str(QUESTIONS))
    parser.add_argument("--k", type=int, default=5, help="상위 몇 개까지 채점할지 (기본 5)")
    parser.add_argument("--only-approved", action="store_true", help="검토 완료(approved) 질문만")
    parser.add_argument("--no-save", action="store_true", help="결과 파일을 저장하지 않음")
    parser.add_argument("--margin", type=float, default=None,
                        help="점수 컷오프 폭 (기본: 설정값 SEARCH_SCORE_MARGIN, 0 이면 끔)")
    args = parser.parse_args()

    import settings
    from document_pipeline import list_documents, search_uploaded, trim_by_margin

    margin = settings.SEARCH_SCORE_MARGIN if args.margin is None else args.margin

    known = [d["document_id"] for d in list_documents()]
    try:
        items = load_questions(args.questions, known)
    except (OSError, ValueError) as exc:
        print("평가 세트를 읽지 못했습니다:", exc)
        return 2
    if args.only_approved:
        items = [i for i in items if i["status"] == "approved"]
        if not items:
            print("검토 완료(approved) 질문이 없습니다.")
            return 2

    results = []
    for item in items:
        hits = trim_by_margin(search_uploaded(item["question"], limit=args.k), margin)
        results.append(score_question(item, hits, args.k))

    print(f"점수 컷오프 폭: {margin} (1위 점수에서 이 폭 안의 결과만 채점)")
    print(f"{'id':6s} {'상태':8s} {'정답 순위':>8s} {'문서 순위':>8s} 1위 쪽  결과 수(정답)  키워드")
    for r in results:
        kw = "-" if r["keyword_hit"] is None else ("있음" if r["keyword_hit"] else "없음")
        print(f"{r['id']:6s} {r['status']:8s} {str(r['rank'] or '없음'):>8s} "
              f"{str(r['doc_rank'] or '없음'):>8s} {str(r['top1_page']):>5s}  "
              f"{r['returned']}({r['relevant']})          {kw}")
    summary = summarize(results, args.k)
    print("\n요약:", json.dumps(summary, ensure_ascii=False))
    keyword_summary = None
    if KEYWORDS.is_file():
        words = [w.strip() for w in KEYWORDS.read_text(encoding="utf-8").splitlines()
                 if w.strip() and not w.lstrip().startswith("#")]
        if words:
            rows = [score_keyword(w, trim_by_margin(search_uploaded(w, limit=args.k), margin)) for w in words]
            keyword_summary = summarize_keywords(rows)
            print("한 단어 검색:", json.dumps(keyword_summary, ensure_ascii=False))
    drafts = sum(r["status"] == "draft" for r in results)
    if drafts:
        print(f"주의: {drafts}개 질문이 초안(draft)입니다. 사람이 정답·쪽을 확인하기 전 점수는 참고용입니다.")

    previous_files = sorted(RESULTS.glob("*.json")) if RESULTS.is_dir() else []
    if previous_files:
        prev = json.loads(previous_files[-1].read_text(encoding="utf-8"))
        changed = compare(prev, results)
        print(f"직전 결과({previous_files[-1].stem})와 비교: 순위 바뀐 질문 {len(changed)}개")
        for qid, a, b in changed:
            print(f"  {qid}: {a or '없음'} → {b or '없음'}")
    if not args.no_save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        out = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}.json"
        out.write_text(json.dumps({"summary": summary, "keyword_summary": keyword_summary,
                                   "margin": margin, "results": results},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print("결과 저장:", out.relative_to(ROOT))
    print("안전: 색인·문서를 바꾸지 않았고 문서 본문·파일명은 출력하지 않았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
