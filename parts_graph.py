"""부품 종류·추천 질문용 LangGraph.  (핀 질문은 kicad_parts.parts_answer, 문서 질문은 rag_graph 가 맡는다)

  START → classify ─(부품 추천 질문 아님)→ END              (answered=False → 호출한 쪽이 기존 흐름으로 보낸다)
              └→ search ─(후보 0건)→ END                    (answered=False)
                    └→ answer → END                         (answered=True)

- classify: 규칙만 쓴다(모델 호출 없음). 질문에 '부품을 묻는 말'(INTENT)이 있고, 온톨로지가 아는 한국어 용어가 있을 때만 통과한다.
  온톨로지 개념은 기본적으로 승인된 것만 쓴다(include_proposed=False). 사람 승인 전 사전을 시험할 때만 True 로 둔다.
- search: deps.find(질문, 개수) → (부품 목록, 쓴 방식). 비면 온톨로지 영어 키워드·분류로 대체('ontology'). 방식은 trace 와 답에 남긴다.
- answer: 모델을 거치지 않고 검색된 부품 값으로 답을 만든다(깨진 한국어·지어낸 부품 방지). 이름·분류·설명·핀 수는 카탈로그 값 그대로.
- 의존성은 모두 인자로 받아 서버·모델 없이 시험할 수 있다. 각 단계는 trace 에 남는다.
"""
from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Annotated, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

import kicad_parts as kp
import ontology_graph as og

# 부품을 찾거나 추천해 달라는 말 (너무 넓지 않게: '문서에서' 같은 말이 있으면 통과시키지 않는다)
# 부품을 찾는 말. 맨 '알려줘'는 설명을 묻는 질문에도 흔해서 뺐다(dev 시험에서 'ADC 해상도가 뭔지 알려줘'를 잘못 처리)
INTENT = re.compile(r"부품|추천|후보|종류|모듈|칩|소자|골라|고르|뭐가\s*있|뭐\s*있|무엇이\s*있|있어|있나|있을까|찾아\s*줘|찾아\s*봐|"
                    r"쓸\s*만|뭐\s*쓰|어떤\s*(?:거|게|것)|구해|사야|좋은\s*거|괜찮은|(?<![a-z])ic(?![a-z])", re.I)
# 부품이 아니라 설명·방법을 묻는 말이 같이 있으면 통과시키지 않는다
EXPLAIN = re.compile(r"뭐야|뭔지|뭐\s*하는|하는\s*일|무엇|원리|차이|설명|방법|코드|계산|어떻게|왜\s|의미|역할|도와\s*줘|도와주", re.I)
# 부품이 아니라 소프트웨어·소비자 제품·구매·환경을 묻는 말 (부품 관련어가 같이 있어도 부품 추천이 아니다)
NONPART = re.compile(r"개발\s*환경|비밀번호|이어폰|헤드폰|헤드셋|스피커|노트북|스마트폰|(?<![가-힣])앱(?![가-힣])|프로그램|툴|도구|소프트웨어|"
                     r"강의|튜토리얼|예제|코드|펌웨어|라이브러리|키캐드|kicad|풋프린트|시뮬레이션|가격|구매|재고|후기|리뷰|공부|"
                     r"공유기|전기차|전기\s*자동차|설치|비용|무선\s*충전|핀|(?<![a-z])pin(?![a-z])|핀맵|단자|데이터\s*시트|datasheet|규격|스펙|사양", re.I)   # 핀·규격 질문은 핀 조회가 맡는다
# 의도어가 없어도 사전에 개념이 있는 짧은 명사구('디지털 가변저항', '트라이악')는 부품을 찾는 말로 본다
SHORT = 30

# '이 부품 말고 비슷한 것'을 찾는 말 (질문에 카탈로그에 있는 부품 이름이 있을 때)
SIMILAR = re.compile(r"같은\s*거|같은\s*것|비슷|유사|대체|대신|말고|다른\s*(?:거|것|부품)|호환|또\s*(?:뭐|있)|비교\s*대상|동급|급의", re.I)

DOC_WORDS = re.compile(r"문서|자료|pdf|올려|업로드|과제|본문|\d+\s*쪽|페이지", re.I)

BACKEND_LABEL = {"es-semantic": "의미 검색", "file": "낱말 검색", "ontology": "온톨로지 키워드 검색"}


class PartsState(TypedDict, total=False):
    question: str
    concepts: list[str]
    concept_ids: list[str]
    anchor: dict
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
    catalog: Optional[list] = None   # 부품 목록(영문 부품 이름으로 '비슷한 부품'을 찾을 때 씀)
    expand: bool = False          # 검색어에 개념의 영어 키워드·분류 이름을 덧붙인다(짧은 한국어 질문의 의미 검색 보강)
    semantic_concepts: Optional[Callable[[str], list[str]]] = None   # 문구가 사전과 다를 때 의미가 가까운 개념(문턱 넘는 것만)


def parts_concepts(question: str, ontology, include_proposed: bool = False, semantic=None) -> list[str]:
    """부품 추천 질문이면 이해한 개념 노드 id 목록, 아니면 빈 목록. 사전에 정확히 맞는 용어가 없으면 semantic(질문)을 시도한다."""
    if ontology is None or DOC_WORDS.search(question) or EXPLAIN.search(question) or NONPART.search(question):
        return []
    if INTENT.search(question):
        exact = og.translate_query(ontology, question, include_proposed)
        return exact or (semantic(question) if semantic else [])
    exact = og.translate_query(ontology, question, include_proposed, skip_risky=True)   # 의도어 없으면 위험 용어 제외
    # 의도어가 없으면 사전에 정확히 맞는 개념이 있고, 질문이 짧고, 문장형(물음표·'알려줘')이 아닐 때만
    q = question.strip()
    return exact if len(q) <= SHORT and not re.search(r"[?？]|알려|말해|가르쳐", q) else []


def find_anchor(question: str, catalog) -> dict | None:
    """'비슷한 부품' 질문이면 기준이 되는 카탈로그 부품(질문 속 부품 번호와 맞는 것 중 이름이 가장 짧은 것), 아니면 None."""
    if not catalog or DOC_WORDS.search(question) or EXPLAIN.search(question) or NONPART.search(question) \
            or not SIMILAR.search(question):
        return None
    for _token, group in kp._candidate_groups(question, catalog):
        return sorted(group, key=lambda p: (len(p["name"]), p["lib_id"]))[0]
    return None


def similar_query(anchor: dict) -> str:
    """기준 부품의 설명·분류 이름·키워드로 만든 검색어(부품 번호 자체는 넣지 않는다 — 번호가 같은 부품만 나오지 않게)."""
    return " ".join(x for x in (anchor.get("description", ""), og.readable_name(anchor.get("library", "")),
                                anchor.get("keywords", "")) if x).strip()


def is_parts_request(question: str, ontology, include_proposed: bool = False) -> list[str]:
    """부품 추천 질문이면 이해한 개념 이름 목록, 아니면 빈 목록."""
    return [ontology.nodes[c]["label"] for c in parts_concepts(question, ontology, include_proposed)]


def expansion_terms(ontology, concept_ids: list[str], limit: int = 6) -> list[str]:
    """개념이 가리키는 영어 키워드와 분류의 읽는 이름(예: Isolator Analog). 검색어 보강용."""
    out: list[str] = []
    for c in concept_ids:
        for n in ontology.neighbors(c):
            d = ontology.nodes[n]
            term = d.get("label") if d.get("kind") == "keyword" else (og.readable_name(d["label"]) if d.get("kind") == "library" else None)
            if term and term not in out:
                out.append(term)
    return out[:limit]


def ontology_search(ontology, concept_ids: list[str], limit: int) -> list[dict]:
    """ES·임베딩 없이 온톨로지로 찾기: 개념이 가리키는 영어 키워드·분류에 속한 카탈로그 부품 (개념마다 번갈아 가져온다)."""
    lists = [og.concept_parts(ontology, c, limit) for c in concept_ids]
    out, seen = [], set()
    for rank in range(limit):
        for rows in lists:
            if rank < len(rows) and rows[rank]["lib_id"] not in seen:
                r = rows[rank]
                seen.add(r["lib_id"])
                out.append({**r, "name": r["lib_id"].split(":", 1)[-1], "library": r["lib_id"].split(":", 1)[0]})
    return out[:limit]


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
        anchor = find_anchor(state["question"], deps.catalog)
        if anchor:
            return {"anchor": anchor, "concepts": [anchor["lib_id"]], "concept_ids": [],
                    "trace": [f"classify: 비슷한 부품 질문, 기준 부품 {anchor['lib_id']}"]}
        ids = parts_concepts(state["question"], deps.ontology, deps.include_proposed, deps.semantic_concepts)
        concepts = [deps.ontology.nodes[c]["label"] for c in ids]
        return {"concepts": concepts, "concept_ids": ids,
                "trace": ["classify: " + (f"부품 추천 질문, 개념 {concepts}" if concepts else "해당 없음 → 기존 흐름")]}

    def after_classify(state: PartsState) -> str:
        return "search" if (state.get("concepts") or state.get("anchor")) else "end"

    def search(state: PartsState) -> PartsState:
        anchor = state.get("anchor")
        if anchor:   # 기준 부품과 비슷한 부품: 기준 부품 자신(같은 이름 계열)은 뺀다
            base = anchor["name"].lower()
            rows, backend = deps.find(similar_query(anchor), deps.limit + 8)
            parts = [r for r in rows if r.get("lib_id") != anchor["lib_id"] and not r.get("name", "").lower().startswith(base)][:deps.limit]
            return {"parts": parts, "backend": backend, "trace": [f"search[{backend}]: 비슷한 부품 {len(parts)}건"]}
        query = state["question"]
        if deps.expand:
            extra = expansion_terms(deps.ontology, state.get("concept_ids", []))
            query = f"{query} {' '.join(extra)}".strip() if extra else query
        parts, backend = deps.find(query, deps.limit)
        if not parts:   # ES·임베딩이 안 되고 한국어 낱말 검색도 비면: 온톨로지의 영어 키워드·분류로 대체
            parts = ontology_search(deps.ontology, state.get("concept_ids", []), deps.limit)
            backend = "ontology" if parts else backend
        return {"parts": parts, "backend": backend, "trace": [f"search[{backend}]: {len(parts)}건"]}

    def after_search(state: PartsState) -> str:
        return "answer" if state.get("parts") else "end"

    def answer(state: PartsState) -> PartsState:
        anchor = state.get("anchor")
        text = format_answer(state["parts"], state["backend"], state["concepts"])
        if anchor:
            text = text.replace("찾은 후보입니다", f"찾은 후보입니다 — `{anchor['lib_id']}`와 설명이 비슷한 부품(성능·핀 호환은 보장하지 않음)", 1)
        return {"answer": text, "answered": True, "trace": ["answer: 검색된 부품 값으로 답함 (모델 호출 없음)"]}

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
