"""웹 화면(/graph)이 쓰는 LangGraph 그림 데이터. 모델·ES 없이 구조(Mermaid)를 만들고, 부품 그래프는 질문 하나로 실행해
지나간 노드를 강조한다(답 생성 없음). 접근 제어는 app.py 의 공통 access_guard 가 맡는다."""
from __future__ import annotations

import re

import parts_chat
import parts_graph as pg
import rag_graph as rg


def _describe(compiled) -> dict:
    g = compiled.get_graph()
    return {"nodes": list(g.nodes),
            "edges": [{"source": e.source, "target": e.target, "conditional": bool(e.conditional)} for e in g.edges],
            "mermaid": g.draw_mermaid()}


def structure() -> list[dict]:
    """두 그래프의 구조: 노드 목록, 간선(조건부 여부), Mermaid 원문. 화면은 노드·간선으로 직접 SVG 를 그린다(외부 라이브러리 없음)."""
    rag = rg.build_rag_graph(rg.RagDeps(search=lambda q: [], generate=lambda q, c, f: "", verify=True, cite=True))
    parts = pg.build_parts_graph(pg.PartsDeps(find=lambda q, n: ([], "file")))
    return [
        {"key": "parts", "title": "부품 추천 그래프 (parts_graph.py) — 채팅에 연결됨", "runnable": True, **_describe(parts)},
        {"key": "rag", "title": "문서 RAG 그래프 (rag_graph.py) — 검증·인용을 켠 모양, 채팅에는 인용 노드만 연결됨",
         "runnable": False, **_describe(rag)},
    ]


def executed_nodes(trace: list[str]) -> list[str]:
    """trace 줄('classify: …', 'search[es-semantic]: …')에서 지나간 노드 이름을 순서대로."""
    out: list[str] = []
    for line in trace:
        m = re.match(r"[a-z_]+", line)
        if m and m.group() not in out:
            out.append(m.group())
    return out


def highlight(mermaid: str, nodes: list[str]) -> str:
    if not nodes:
        return mermaid
    return (mermaid.rstrip() + "\n\tclassDef ran fill:#ffe8a3,stroke:#b8860b,stroke-width:3px,color:#000\n"
            + f"\tclass {','.join(nodes)} ran\n")


def explain_parts(question: str) -> dict:
    """부품 그래프를 질문 하나로 실행해 {'enabled', 'answered', 'trace', 'nodes', 'mermaid', ...} 를 돌려준다."""
    base = next(g["mermaid"] for g in structure() if g["key"] == "parts")
    state = parts_chat.run(question)
    if state is None:
        return {"enabled": False, "answered": False, "trace": [], "nodes": [], "mermaid": base,
                "note": "부품 한국어 검색이 꺼져 있습니다(PARTS_SEMANTIC_SEARCH) 또는 사전 파일이 없습니다."}
    nodes = executed_nodes(state.get("trace", []))
    return {"enabled": True, "answered": bool(state.get("answered")), "trace": state.get("trace", []), "nodes": nodes,
            "backend": state.get("backend"), "concepts": state.get("concepts", []),
            "parts": [p.get("lib_id") for p in state.get("parts", [])],
            "mermaid": highlight(base, nodes)}
