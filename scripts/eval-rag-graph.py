#!/usr/bin/env python3
"""LangGraph 문답 흐름(rag_graph.py)의 '재검색(온톨로지로 넓히기)'이 검색 품질을 바꾸는지 잰다.

- 읽기 전용: 문서·색인을 바꾸지 않고, 답변 모델도 부르지 않는다 (검색 단계만 채점).
- 기준선(넓히기 없음)과, min_score 값별로 그래프를 돌린 결과를 같은 질문·같은 채점(run-eval.py 의
  score_question/summarize)으로 비교한다. 검색 결과는 검색어별로 캐시해 같은 검색을 두 번 하지 않는다.
- 출력에는 문서 본문·파일명을 넣지 않는다.

사용: .venv/bin/python scripts/eval-rag-graph.py [--k 5] [--scores 0.5,0.6,0.7] [--only-approved]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_run_eval():
    spec = importlib.util.spec_from_file_location("run_eval", ROOT / "scripts" / "run-eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def evaluate(items, search, ontology, min_score, k, run_eval, rag_graph):
    """질문들을 그래프에 통과시켜 (채점 결과 목록, 재검색이 일어난 질문 id 목록)을 돌려준다."""
    deps = rag_graph.RagDeps(search=search, generate=lambda q, c: "", ontology=ontology,
                             min_score=min_score)
    graph = rag_graph.build_rag_graph(deps)
    results, broadened = [], []
    for item in items:
        out = rag_graph.ask(graph, item["question"])
        if out.get("extra_terms"):
            broadened.append(item["id"])
        results.append(run_eval.score_question(item, out.get("sources", []), k))
    return results, broadened


def main() -> int:
    ap = argparse.ArgumentParser(description="재검색(넓히기) 효과 측정 — 검색 단계만, 읽기 전용")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--scores", default="0.5,0.6,0.7", help="시험할 min_score 목록 (쉼표)")
    ap.add_argument("--only-approved", action="store_true")
    args = ap.parse_args()

    import ontology_graph as og
    import rag_graph
    import settings
    from document_pipeline import list_documents, search_uploaded, trim_by_margin

    run_eval = _load_run_eval()
    known = [d["document_id"] for d in list_documents()]
    items = run_eval.load_questions(run_eval.QUESTIONS, known)
    if args.only_approved:
        items = [i for i in items if i["status"] == "approved"]

    onto_path = ROOT / "data" / "ontology" / "graph.json"
    if not onto_path.is_file():
        print("온톨로지가 없습니다: scripts/build-ontology-graph.py 를 먼저 실행하세요.")
        return 2
    ontology = og.load_graph(onto_path)

    cache: dict[str, list] = {}

    def search(q):
        if q not in cache:
            cache[q] = trim_by_margin(search_uploaded(q, limit=args.k), settings.SEARCH_SCORE_MARGIN)
        return cache[q]

    top_scores = [max((h.get("score") or 0 for h in search(i["question"])), default=0) for i in items]
    srt = sorted(top_scores)
    print(f"질문 {len(items)}개 · 1차 검색 최고 점수 분포: 최소 {srt[0]:.2f} / 중앙 {srt[len(srt) // 2]:.2f} / 최대 {srt[-1]:.2f}")

    report = {}
    base, _ = evaluate(items, search, ontology, 0.0, args.k, run_eval, rag_graph)  # min_score 0 = 넓히지 않음
    report["baseline"] = run_eval.summarize(base, args.k)
    print("기준선(넓히기 없음):", json.dumps(report["baseline"], ensure_ascii=False))
    base_rank = {r["id"]: r["rank"] for r in base}

    for s in [float(x) for x in args.scores.split(",") if x.strip()]:
        res, broadened = evaluate(items, search, ontology, s, args.k, run_eval, rag_graph)
        summ = run_eval.summarize(res, args.k)
        changed = [(r["id"], base_rank[r["id"]], r["rank"]) for r in res if r["rank"] != base_rank[r["id"]]]
        report[f"min_score={s}"] = {**summ, "broadened": len(broadened), "rank_changed": changed}
        print(f"min_score={s}: 넓힌 질문 {len(broadened)}개, 순위 바뀐 질문 {len(changed)}개 "
              f"{[(i, a or '없음', b or '없음') for i, a, b in changed]}")
        print("   ", json.dumps(summ, ensure_ascii=False))

    out_dir = ROOT / "data" / "eval" / "graph-results"
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    path = out_dir / f"rag-graph-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
