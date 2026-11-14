"""부품 종류·추천 질문용 LangGraph.  (핀 질문은 kicad_parts.parts_answer, 문서 질문은 rag_graph 가 맡는다)

  START → classify ─(부품 추천 질문 아님)→ END              (answered=False → 호출한 쪽이 기존 흐름으로 보낸다)
              └→ search ─(후보 0건)→ END                    (answered=False)
                    └→ answer → END                         (answered=True)

- classify: 규칙만 쓴다(모델 호출 없음). 질문에 '부품을 묻는 말'(INTENT)이 있고, 온톨로지가 아는 한국어 용어가 있을 때만 통과한다.
  온톨로지 개념은 기본적으로 승인된 것만 쓴다(include_proposed=False). 사람 승인 전 사전을 시험할 때만 True 로 둔다.
- search: deps.find(질문, 개수) → (부품 목록, 쓴 방식). 방식('es-semantic' | 'file')은 trace 와 답에 남긴다.
- answer: 모델을 거치지 않고 검색된 부품 값으로 답을 만든다(깨진 한국어·지어낸 부품 방지). 이름·분류·설명·핀 수는 카탈로그 값 그대로.
- 의존성은 모두 인자로 받아 서버·모델 없이 시험할 수 있다. 각 단계는 trace 에 남는다.
"""
from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Annotated, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

import ontology_graph as og

# 부품을 찾거나 추천해 달라는 말 (너무 넓지 않게: '문서에서' 같은 말이 있으면 통과시키지 않는다)
INTENT = re.compile(r"부품|추천|후보|종류|모듈|칩|소자|골라|뭐가\s*있|무엇이\s*있|알려\s*줘|찾아\s*줘", re.I)
DOC_WORDS = re.compile(r"문서|자료|pdf|올려|업로드|과제|본문|\d+\s*쪽|페이지", re.I)

BACKEND_LABEL = {"es-semantic": "의미 검색", "file": "낱말 검색"}


class PartsState(TypedDict, total=False):
    question: str
    concepts: list[str]
    parts: list[dict]
    backend: str
    answered: bool
    answer: str
    trace: Annotated[list[str], operator.add]


@dataclass
class PartsDeps:
    find: Callable[[str, int], tuple[list[dict], str]]       # (질문, 개수) → (부품 목록, 방식)
    ontology: Optional[object] = None
    include_proposed: bool = False
    limit: int = 5


def is_parts_request(question: str, ontology, include_proposed: bool = False) -> list[str]:
    """부품 추천 질문이면 이해한 개념 이름 목록, 아니면 빈 목록."""
    if ontology is None or not INTENT.search(question) or DOC_WORDS.search(question):
        return []
    return [ontology.nodes[c]["label"] for c in og.translate_query(ontology, question, include_proposed)]


def format_answer(parts: list[dict], backend: str, concepts: list[str]) -> str:
    lines = [f"KiCad 부품 라이브러리에서 찾은 후보입니다 ({BACKEND_LABEL.get(backend, backend)}, 이해한 개념: {', '.join(concepts)}).", ""]
    for i, p in enumerate(parts, 1):
        desc = (p.get("description") or "").strip() or "설명 없음"
        pins = f", 핀 {p['pin_count']}개" if p.get("pin_count") else ""
        lines.append(f"{i}. **{p.get('name', p.get('lib_id', ''))}** (`{p.get('lib_id', '')}`{pins}) — {desc}")
    lines += ["", "라이브러리 설명 그대로이며, 설계에 쓰기 전에 데이터시트로 확인하세요. 특정 부품의 핀 배치는 부품 번호와 함께 물어보세요."]
    return "\n".join(lines)


def build_parts_graph(deps: PartsDeps):
    def classify(state: PartsState) -> PartsState:
        concepts = is_parts_request(state["question"], deps.ontology, deps.include_proposed)
        return {"concepts": concepts,
                "trace": ["classify: " + (f"부품 추천 질문, 개념 {concepts}" if concepts else "해당 없음 → 기존 흐름")]}

    def after_classify(state: PartsState) -> str:
        return "search" if state.get("concepts") else "end"

    def search(state: PartsState) -> PartsState:
        parts, backend = deps.find(state["question"], deps.limit)
        return {"parts": parts, "backend": backend, "trace": [f"search[{backend}]: {len(parts)}건"]}

    def after_search(state: PartsState) -> str:
        return "answer" if state.get("parts") else "end"

    def answer(state: PartsState) -> PartsState:
        return {"answer": format_answer(state["parts"], state["backend"], state["concepts"]), "answered": True,
                "trace": ["answer: 검색된 부품 값으로 답함 (모델 호출 없음)"]}

    g = StateGraph(PartsState)
    for name, fn in [("classify", classify), ("search", search), ("answer", answer)]:
        g.add_node(name, fn)
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", after_classify, {"search": "search", "end": END})
    g.add_conditional_edges("search", after_search, {"answer": "answer", "end": END})
    g.add_edge("answer", END)
    return g.compile()


def ask_parts(graph, question: str) -> PartsState:
    return graph.invoke({"question": question, "answered": False, "trace": []})
