#!/usr/bin/env python3
"""자동 모드의 처리 방식 판단(문서 · 부품 라이브러리 · 일반 대화)이 맞는지 확인한다 — 검색만 쓰고 답은 만들지 않는다.

질문: data/eval/questions.jsonl (정답 route = documents) + data/eval/routing-extra.jsonl (route 가 적혀 있음).
확인하는 것:
  - 실제 판단(app.decide_route)이 정답과 같은가, 틀린 질문의 번호
  - 문턱별 오류: 문서 질문을 놓친 비율 / 문서가 아닌 질문을 문서로 보낸 비율
이 질문들은 문턱을 정할 때도 쓴 것이라 오류율이 실제보다 좋게 나올 수 있다(같은 자료로 정하고 같은 자료로 잼).
새 질문을 추가해 문턱을 정하지 않은 자료로 다시 확인하는 것이 좋다.
출력에는 질문과 답 본문을 넣지 않는다(질문 번호만).

사용: .venv/bin/python scripts/run-route-eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
THRESHOLDS = (0.70, 0.74, 0.76, 0.78, 0.80, 0.82, 0.85)


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]


def sweep(rows: list[tuple[str, str, list]], thresholds, min_terms: int = 1) -> list[dict]:
    """rows: (정답 route, id, 검색 결과) → 문턱별 오류."""
    import routing
    out = []
    docs = [r for r in rows if r[0] == "documents"]
    others = [r for r in rows if r[0] != "documents"]
    for t in thresholds:
        missed = [r[1] for r in docs if not routing.has_document_evidence(r[2], t, min_terms)]
        wrong = [r[1] for r in others if routing.has_document_evidence(r[2], t, min_terms)]
        out.append({"threshold": t, "missed_documents": missed, "wrongly_documents": wrong,
                    "n_documents": len(docs), "n_others": len(others)})
    return out


FOLLOWUPS = ["그럼 그건 얼마야?", "좀 더 자세히 설명해줘", "그 다음은 뭐야?", "왜 그런 거야?", "예를 들어 보여줘", "그거 어디서 확인해?"]


def followup_cases(max_each: int = 6, heldout: bool = False) -> list[dict]:
    """대화 이력이 있는 후속 질문 세트를 만든다 (사전 등록: 만드는 규칙을 측정 전에 정해 둔다).
    이전 질문 = (혼자서도 문서로 판단되는 문서 질문 · 혼자서도 일반으로 판단되는 일반 질문) 각 max_each 개,
    후속 질문 = 위의 지시어 문장 6개. 정답: 문서 질문 뒤는 documents, 일반 질문 뒤는 general.
    이전 질문을 고르는 기준이 '혼자 판단이 맞는 것'이라 후속 질문 판단만 따로 볼 수 있다."""
    import app
    docs = [q for q in load(ROOT / "data/eval/questions.jsonl")]
    gens = [q for fn in ("routing-heldout.jsonl", "routing-heldout2.jsonl", "routing-heldout3.jsonl", "routing-extra.jsonl")
            for q in load(ROOT / "data/eval" / fn) if q.get("route") == "general"]
    cases = []
    if heldout:        # 단서 목록을 고정한 뒤 새로 쓴 문장 (data/eval/routing-followup-heldout.jsonl)
        doc_prev = [q for q in docs if app.decide_route(q["question"])["route"] == "documents"][:max_each]
        for q in doc_prev:
            for t in load(ROOT / "data/eval/routing-followup-heldout.jsonl"):
                cases.append({"id": f"{q['id']}+{t['id']}", "kind": t["kind"], "history": [q["question"]],
                              "question": t["text"], "route": "documents" if t["kind"] == "followup" else "general"})
        return cases
    for truth, pool in (("documents", docs), ("general", gens)):
        taken = 0
        for q in pool:
            if taken >= max_each:
                break
            if app.decide_route(q["question"])["route"] != truth:
                continue
            taken += 1
            for j, f in enumerate(FOLLOWUPS):
                cases.append({"id": f"{q['id']}+f{j + 1}", "history": [q["question"]], "question": f, "route": truth})
    # 주제 전환: 문서 질문 뒤에 이어지는 '짧은(20자 이하) 새 일반 질문'. 정답은 general (이력을 이어받으면 안 됨)
    short_general = [q for q in gens if len(q["question"]) <= 20 and app.decide_route(q["question"])["route"] == "general"][:6]
    doc_prev = [q for q in docs if app.decide_route(q["question"])["route"] == "documents"][:max_each]
    for q in doc_prev:
        for g in short_general:
            cases.append({"id": f"{q['id']}+switch-{g['id']}", "history": [q["question"]], "question": g["question"], "route": "general"})
    return cases


def main() -> int:
    import app
    import settings
    from chat_search import from_uploaded
    groups = [("문턱을 정할 때 쓴 질문", load(ROOT / "data/eval/questions.jsonl") + load(ROOT / "data/eval/routing-extra.jsonl")),
              ("새 질문 1차(문턱을 정하는 데 쓰지 않음)", load(ROOT / "data/eval/routing-heldout.jsonl")),
              ("새 질문 2차(규칙·약함 표시를 만든 뒤에 쓴 질문)", load(ROOT / "data/eval/routing-heldout2.jsonl")),
              ("새 질문 3차(부품 번호 규칙을 만든 뒤에 쓴 질문)", load(ROOT / "data/eval/routing-heldout3.jsonl")),
              ("후속 질문 1차(대화 이력 포함, 생성 규칙 사전 등록 · 단서 목록을 만들 때 본 문장)", followup_cases()),
              ("후속 질문 2차(단서 목록을 고정한 뒤 새로 쓴 문장)", followup_cases(heldout=True))]
    print(f"현재 설정: 문턱 {settings.ROUTE_DOC_MIN_SCORE} · 낱말 일치 {settings.ROUTE_DOC_MIN_TERMS}개 이상")
    status = 0
    for title, questions in groups:
        if questions:
            print(f"\n=== {title} ({len(questions)}개) ===")
            status = max(status, report(questions, app, settings, from_uploaded))
    print("안전: 문서·색인을 바꾸지 않았고 질문·답 본문은 출력하지 않았습니다.")
    return status


def report(questions, app, settings, from_uploaded) -> int:
    rows, wrong_route = [], []
    for q in questions:
        truth = q.get("route", "documents")
        try:
            hits = [from_uploaded(h) for h in app.search_uploaded(
                ((q["history"][-1] + " ") if q.get("history") else "")[:1000] + q["question"][:1000], limit=4)]
            actual = app.decide_route(q["question"], q["history"][-1] if q.get("history") else None)["route"]
        except Exception as exc:
            print(f"{q['id']} 검색 실패: {type(exc).__name__}")
            return 2
        rows.append((truth, q["id"], hits))
        if actual != truth:
            wrong_route.append((q["id"], truth, actual))
    print(f"판단이 정답과 다른 질문 {len(wrong_route)}/{len(rows)}: " + (", ".join(f"{i}({t}→{a})" for i, t, a in wrong_route) or "없음"))
    print("\n문턱별 오류 (같은 자료로 정한 문턱이라 낙관적일 수 있음):")
    for r in sweep(rows, THRESHOLDS, settings.ROUTE_DOC_MIN_TERMS):
        print(f"  {r['threshold']:.2f}: 문서 질문 놓침 {len(r['missed_documents'])}/{r['n_documents']} {r['missed_documents']}"
              f" | 문서 아닌 질문을 문서로 {len(r['wrongly_documents'])}/{r['n_others']} {r['wrongly_documents']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
