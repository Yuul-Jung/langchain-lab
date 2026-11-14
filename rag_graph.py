"""LangGraph 문답 흐름.

  START → parts_lookup ─(핀 질문)→ END
              └→ retrieve → grade ─(충분)────────────────→ generate ─→ verify ─→ [regenerate] ─→ cite → END
                     ↑          ├─(부족, 넓힐 낱말 있음)→ broaden ┐
                     └──────────┘                                  (verify·cite 는 켜고 끌 수 있음)
                                └─(근거 0건)→ no_evidence → END

- 의존성(검색·모델·부품 조회·온톨로지)은 모두 인자로 받아 서버·모델 없이 시험할 수 있다.
- app.py 와 아직 연결하지 않았다. 각 단계는 trace 에 남는다.
- broaden: 최대 max_retries 번, 온톨로지에서 더할 낱말이 없으면 돌지 않는다.
- verify: grounding.check 로 답의 숫자·영문 용어가 근거에 있는지 본다. 못 찾은 것이 있으면
  regenerate 가 모델에게 그 값을 알려 주며 **한 번만** 다시 쓰게 하고, 못 찾은 개수가 **줄어든 경우에만** 새 답을 쓴다.
- cite: 모델이 [자료 N] 을 빼먹으면 answer_cite 가 겹치는 근거를 찾아 '근거:' 줄을 붙인다.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

import answer_cite
import chat_search
import grounding
import ontology_graph as og

NO_EVIDENCE_ANSWER = "올려 둔 문서에서 이 질문에 답할 근거를 찾지 못했습니다. 질문을 바꾸거나 관련 문서를 올려 주세요."

FEEDBACK_TEMPLATE = (
    "앞선 답변에서 다음 값이 참고 문서에서 확인되지 않았습니다: {items}. "
    "참고 문서에 있는 내용만으로 다시 답하세요. 계산한 값이면 참고 문서의 어떤 값으로 계산했는지 함께 쓰고, "
    "근거가 없는 값은 쓰지 마세요."
)


class RagState(TypedDict, total=False):
    question: str
    query: str
    attempt: int
    sources: list[dict]
    extra_terms: list[str]
    low_confidence: bool
    answer: str
    answered_by: str                # kicad-library | llm | none
    ungrounded: list[str]           # verify 가 근거에서 못 찾은 값
    regenerated: str                # "" | accepted | rejected
    cite_info: dict
    trace: Annotated[list[str], operator.add]


@dataclass
class RagDeps:
    search: Callable[[str], list[dict]]
    generate: Callable[[str, str, str], str]         # (질문, 참고 문서 문자열, 재작성 지시('' 이면 첫 생성)) → 답
    parts_answer: Optional[Callable[[str], Optional[str]]] = None
    ontology: Optional[object] = None
    min_score: float = 0.0
    max_retries: int = 1
    verify: bool = False
    cite: bool = False


def _best(sources: list[dict]) -> float:
    return max((s.get("score") or 0 for s in sources), default=0.0)


def _insufficient(state: RagState, deps: RagDeps) -> bool:
    s = state.get("sources", [])
    return not s or _best(s) < deps.min_score


def _expansion(state: RagState, deps: RagDeps) -> list[str]:
    if deps.ontology is None:
        return []
    terms = og.expand_query(deps.ontology, state["question"])
    have = set(og.split_keywords(state["query"]))
    return [t for t in terms if t not in have]


def find_ungrounded(answer: str, sources: list[dict], question: str) -> list[str]:
    g = grounding.check(answer, grounding.source_texts(sources), question)
    return g["numbers"] + g["words"]


def build_rag_graph(deps: RagDeps):
    def parts_lookup(state: RagState) -> RagState:
        ans = deps.parts_answer(state["question"]) if deps.parts_answer else None
        if ans is None:
            return {"trace": ["parts_lookup: 해당 없음"]}
        return {"answer": ans, "answered_by": "kicad-library", "trace": ["parts_lookup: 라이브러리 값으로 답함"]}

    def after_parts(state: RagState) -> str:
        return "done" if state.get("answer") else "retrieve"

    def retrieve(state: RagState) -> RagState:
        query = state.get("query") or state["question"]
        n = state.get("attempt", 0) + 1
        found = deps.search(query)
        return {"query": query, "attempt": n, "sources": found,
                "trace": [f"retrieve#{n}: '{query[:60]}' → {len(found)}건, 최고 {_best(found):.2f}"]}

    def grade(state: RagState) -> RagState:
        return {"trace": ["grade: " + ("부족" if _insufficient(state, deps) else "충분")]}

    def after_grade(state: RagState) -> str:
        if not _insufficient(state, deps):
            return "generate"
        if state.get("attempt", 1) <= deps.max_retries and _expansion(state, deps):
            return "broaden"
        return "generate" if state.get("sources") else "no_evidence"

    def broaden(state: RagState) -> RagState:
        extra = _expansion(state, deps)
        return {"query": f'{state["question"]} {" ".join(extra)}'.strip(), "extra_terms": extra,
                "trace": [f"broaden: 온톨로지로 {extra} 추가"]}

    def generate(state: RagState) -> RagState:
        sources = state.get("sources", [])
        low = _insufficient(state, deps)
        answer = deps.generate(state["question"], chat_search.format_context(sources), "")
        return {"answer": answer, "answered_by": "llm", "low_confidence": low,
                "trace": ["generate: 답변" + (" (근거 점수 낮음)" if low else "")]}

    def verify(state: RagState) -> RagState:
        bad = find_ungrounded(state["answer"], state.get("sources", []), state["question"])
        return {"ungrounded": bad, "trace": [f"verify: 근거에서 못 찾은 값 {len(bad)}개"]}

    def after_verify(state: RagState) -> str:
        return "regenerate" if state.get("ungrounded") else "cite"

    def regenerate(state: RagState) -> RagState:
        sources = state.get("sources", [])
        before = state["ungrounded"]
        feedback = FEEDBACK_TEMPLATE.format(items=", ".join(before))
        new = deps.generate(state["question"], chat_search.format_context(sources), feedback)
        after = find_ungrounded(new, sources, state["question"])
        if len(after) < len(before):
            return {"answer": new, "ungrounded": after, "regenerated": "accepted",
                    "trace": [f"regenerate: 채택 ({len(before)}개 → {len(after)}개)"]}
        return {"regenerated": "rejected", "trace": [f"regenerate: 버림 ({len(before)}개 → {len(after)}개, 줄지 않음)"]}

    def cite(state: RagState) -> RagState:
        if not deps.cite:
            return {}
        answer, info = answer_cite.add_citations(state["answer"], state.get("sources", []))
        return {"answer": answer, "cite_info": info,
                "trace": [f"cite: 유지 {info['kept']}, 추가 {info['added']}, 잘못된 번호 삭제 {info['removed_bad']}"]}

    def no_evidence(state: RagState) -> RagState:
        return {"answer": NO_EVIDENCE_ANSWER, "answered_by": "none", "trace": ["no_evidence: 근거 없음, 모델 호출 안 함"]}

    g = StateGraph(RagState)
    for name, fn in [("parts_lookup", parts_lookup), ("retrieve", retrieve), ("grade", grade),
                     ("broaden", broaden), ("generate", generate), ("verify", verify),
                     ("regenerate", regenerate), ("cite", cite), ("no_evidence", no_evidence)]:
        g.add_node(name, fn)
    g.add_edge(START, "parts_lookup")
    g.add_conditional_edges("parts_lookup", after_parts, {"done": END, "retrieve": "retrieve"})
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", after_grade, {"generate": "generate", "broaden": "broaden",
                                                   "no_evidence": "no_evidence"})
    g.add_edge("broaden", "retrieve")

    # generate 뒤: 켜진 단계만 거친다
    after_generate = "verify" if deps.verify else ("cite" if deps.cite else "end")
    g.add_conditional_edges("generate", lambda s: after_generate, {"verify": "verify", "cite": "cite", "end": END})
    g.add_conditional_edges("verify", after_verify if deps.verify else (lambda s: "cite"),
                            {"regenerate": "regenerate", "cite": "cite"})
    g.add_edge("regenerate", "cite")
    after_cite = (lambda s: "end")
    g.add_conditional_edges("cite", after_cite, {"end": END})
    g.add_edge("no_evidence", END)
    return g.compile()


def ask(graph, question: str) -> RagState:
    return graph.invoke({"question": question, "attempt": 0, "trace": []})
